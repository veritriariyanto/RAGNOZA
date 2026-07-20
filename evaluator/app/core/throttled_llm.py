"""
evaluator/app/core/throttled_llm.py

Wrapper ChatGroq yang intercept di level _generate dan _agenerate —
layer yang benar-benar dipanggil oleh LangChain sebelum request ke Groq.

Kenapa file terpisah:
    ragas_service.py tidak boleh tahu detail implementasi throttle.
    llm_provider.py tidak boleh tahu detail RAGAS.
    File ini menjadi jembatan keduanya.
"""

import logging
import time
import threading
import json
import os
from pathlib import Path
from typing import Any, List, Optional
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_groq import ChatGroq
from app.core.config import settings

logger = logging.getLogger(__name__)

# Lokasi file persist — folder terpisah agar mudah di-gitignore, tidak tercampur source code.
_QUOTA_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "quota_state"
_QUOTA_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _quota_state_path(model_name: str) -> Path:
    safe_name = model_name.replace("/", "_").replace(":", "_")
    return _QUOTA_STATE_DIR / f"{safe_name}.json"

class DailyQuotaExceeded(Exception):
    """Dilempar saat perkiraan kuota harian (TPD/RPD) Groq untuk model tertentu hampir habis."""
    pass

class _SlidingWindowThrottle:
    """
    Sliding window rate limiter berbasis token DAN request count.

    FIX: sebelumnya hanya menghitung token/menit (TPM), tidak menghitung
    jumlah request/menit (RPM). Groq membatasi keduanya secara independen —
    TPM window bisa jauh dari penuh sementara RPM sudah terlampaui, yang
    memicu 429 meski token count aman (terbukti di log produksi: TPM baru
    8305/9000 saat 429 sudah terjadi 5x berturut-turut).

    RPM riil kedua model production kita SAMA (30 RPM untuk 8b-instant
    maupun 70b-versatile) — jadi satu default rpm_limit cukup, tidak perlu
    differensiasi per model seperti TPM.
    """

    def __init__(self, tpm_limit: int = 4500, min_gap_sec: float = 1.2, rpm_limit: int = 25,
                 tpd_limit: int = 90000, rpd_limit: int = 1000, model_name: str = "unknown"):
        self._tpm_limit = tpm_limit
        self._rpm_limit = rpm_limit
        self._tpd_limit = tpd_limit
        self._rpd_limit = rpd_limit
        self._min_gap = min_gap_sec
        self._model_name = model_name          # ← BARU
        self._window: list[tuple[float, int]] = []
        self._daily_window: list[tuple[float, int]] = []
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._load_daily_state(model_name)      # ← BARU: load saat instance dibuat

    def _evict_old(self, now: float):
        cutoff = now - 60.0
        self._window = [(t, tok) for t, tok in self._window if t > cutoff]

    def _evict_old_daily(self, now: float):
        cutoff = now - 86400.0
        self._daily_window = [(t, tok) for t, tok in self._daily_window if t > cutoff]

    def _load_daily_state(self, model_name: str):
        """Load window harian dari disk saat instance pertama kali dibuat (mis. setelah restart)."""
        path = _quota_state_path(model_name)
        if not path.exists():
            return
        try:
            with open(path, "r") as f:
                raw = json.load(f)
            now = time.monotonic()
            wall_now = time.time()
            # Konversi timestamp wall-clock (disimpan) ke monotonic relatif saat load.
            loaded = [
                (now - (wall_now - entry["wall_ts"]), entry["tokens"])
                for entry in raw.get("entries", [])
                if wall_now - entry["wall_ts"] < 86400.0  # buang yang sudah > 24 jam
            ]
            self._daily_window = loaded
            logger.info(
                "📂 State harian dimuat untuk '%s': %d entri, %d token (dari %s)",
                model_name, len(loaded), sum(t for _, t in loaded), path,
            )
        except Exception as exc:
            logger.warning("⚠️ Gagal load state harian '%s': %s — mulai dari kosong.", model_name, exc)

    def _save_daily_state(self, model_name: str):
        """Simpan window harian ke disk setiap kali ada entri baru — agar restart tidak reset counter."""
        path = _quota_state_path(model_name)
        try:
            wall_now = time.time()
            mono_now = time.monotonic()
            entries = [
                {"wall_ts": wall_now - (mono_now - ts), "tokens": tok}
                for ts, tok in self._daily_window
            ]
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump({"entries": entries}, f)
            os.replace(tmp_path, path)  # atomic write, hindari file korup jika crash di tengah
        except Exception as exc:
            logger.warning("⚠️ Gagal simpan state harian '%s': %s", model_name, exc)

    def _tokens_in_window(self) -> int:
        return sum(tok for _, tok in self._window)

    def wait_and_record(self, estimated_tokens: int):
        with self._lock:
            now = time.monotonic()

            # Cek kuota harian (RPD & TPD) SEBELUM throttle TPM/RPM — fail-fast, jangan sleep menunggu reset.
            self._evict_old_daily(now)
            daily_used_tokens = sum(tok for _, tok in self._daily_window)
            daily_used_requests = len(self._daily_window)

            if daily_used_requests + 1 > self._rpd_limit:
                logger.error(
                    "🚫 Perkiraan kuota RPD Groq habis (req=%d/%d). Evaluasi dihentikan.",
                    daily_used_requests, self._rpd_limit,
                )
                raise DailyQuotaExceeded(
                    f"Perkiraan kuota harian (RPD) Groq hampir habis "
                    f"(used={daily_used_requests}, limit={self._rpd_limit}). Coba lagi nanti."
                )

            if daily_used_tokens + estimated_tokens > self._tpd_limit:
                logger.error(
                    "🚫 Perkiraan kuota TPD Groq habis (tok=%d/%d). Evaluasi dihentikan.",
                    daily_used_tokens, self._tpd_limit,
                )
                raise DailyQuotaExceeded(
                    f"Perkiraan kuota harian (TPD) Groq hampir habis "
                    f"(used={daily_used_tokens}, limit={self._tpd_limit}). Coba lagi nanti."
                )

            gap = now - self._last_request

            if gap < self._min_gap:
                sleep_gap = self._min_gap - gap
                logger.debug("⏳ Gap floor: sleep %.2fs", sleep_gap)
                time.sleep(sleep_gap)

            while True:
                now = time.monotonic()
                self._evict_old(now)
                used_tokens = self._tokens_in_window()
                used_requests = len(self._window)  # ← BARU: jumlah entri = jumlah request dalam window

                tpm_ok = used_tokens + estimated_tokens <= self._tpm_limit
                rpm_ok = used_requests < self._rpm_limit

                if tpm_ok and rpm_ok:
                    break  # Aman untuk jalan

                oldest_ts = self._window[0][0]
                wait_until = oldest_ts + 60.0
                sleep_sec = max(0.1, wait_until - now)
                reason = "TPM" if not tpm_ok else "RPM"
                logger.info(
                    "⏳ %s window penuh (tok=%d/%d, req=%d/%d). Sleep %.1fs",
                    reason, used_tokens, self._tpm_limit, used_requests, self._rpm_limit, sleep_sec,
                )
                time.sleep(sleep_sec)

            now = time.monotonic()
            self._window.append((now, estimated_tokens))
            self._daily_window.append((now, estimated_tokens))
            self._last_request = now
            self._save_daily_state(self._model_name)
            logger.debug(
                "✅ Request diizinkan: +%d token, window=tok:%d/%d req:%d/%d",
                estimated_tokens, self._tokens_in_window(), self._tpm_limit,
                len(self._window), self._rpm_limit,
            )


# FIX: sebelumnya SATU instance _throttle dipakai bersama oleh SEMUA model
# (llama-3.1-8b-instant TPM riil 6000, llama-3.3-70b-versatile TPM riil 12000).
# Akibatnya kedua model saling mengunci window yang sama meski kuota Groq
# keduanya independen — dan buffer 4500 yang aman untuk 8b terlalu konservatif
# untuk 70b, sekaligus tidak melindungi 8b dari 413 (request tunggal > limit)
# karena estimasi token per-request tetap sama untuk keduanya.
_throttles: dict[str, "_SlidingWindowThrottle"] = {}
_throttles_lock = threading.Lock()

# Buffer di bawah limit riil masing-masing model (lihat dashboard Groq).
_MODEL_TPM_LIMITS = {
    "llama-3.1-8b-instant": 4500,      # riil 6000
    "llama-3.3-70b-versatile": 10500,   # riil 12000
}
_MODEL_RPM_LIMITS = {
    "llama-3.1-8b-instant": 25,        # riil 30, sama untuk kedua model
    "llama-3.3-70b-versatile": 25,     # riil 30
}

# TODO: isi berdasarkan dashboard Groq Anda (Settings → Limits) per model.
# Nilai di bawah adalah estimasi awal dari log produksi (70b: TPD riil 100000).
_MODEL_TPD_LIMITS = {
    "llama-3.1-8b-instant": 450000,     # riil 500.000
    "llama-3.3-70b-versatile": 90000,   # riil 100.000
}
_MODEL_RPD_LIMITS = {
    "llama-3.1-8b-instant": 13000,      # riil 14.400
    "llama-3.3-70b-versatile": 900,     # riil 1.000
}

def _get_throttle(model_name: str) -> "_SlidingWindowThrottle":
    with _throttles_lock:
        if model_name not in _throttles:
            tpm = _MODEL_TPM_LIMITS.get(model_name, settings.GROQ_TPM_LIMIT)
            rpm = _MODEL_RPM_LIMITS.get(model_name, 25)
            tpd = _MODEL_TPD_LIMITS.get(model_name, settings.GROQ_TPD_LIMIT)
            rpd = _MODEL_RPD_LIMITS.get(model_name, settings.GROQ_RPD_LIMIT)
            _throttles[model_name] = _SlidingWindowThrottle(
                tpm_limit=tpm,
                min_gap_sec=settings.GROQ_MIN_GAP_SEC,
                rpm_limit=rpm,
                tpd_limit=tpd,
                rpd_limit=rpd,
                model_name=model_name,
            )
            logger.info(
                "🆕 Throttle baru dibuat untuk model='%s' | tpm_limit=%d | rpm_limit=%d | tpd_limit=%d | rpd_limit=%d",
                model_name, tpm, rpm, tpd, rpd,
            )
        return _throttles[model_name]

def _estimate_tokens(messages: List[BaseMessage]) -> int:
    """
    Estimasi kasar jumlah token dari list messages.
    Rule of thumb: 1 token ≈ 4 karakter untuk teks Latin/Indonesia.
    Tambah 20% overhead untuk formatting dan system prompt RAGAS.
    """
    total_chars = sum(len(str(m.content)) for m in messages)
    estimated = int(total_chars / 4 * 1.2)
    return max(estimated, 150)  # minimum 150 token per call


class ThrottledChatGroq(ChatGroq):
    """
    ChatGroq dengan sliding window rate limiter built-in.

    Override _generate dan _agenerate — dua method yang SELALU
    dipanggil LangChain sebelum request ke API, apapun cara RAGAS
    memanggilnya (invoke, ainvoke, batch, stream, dll).

    Cara pakai:
        from app.core.throttled_llm import ThrottledChatGroq
        llm = ThrottledChatGroq(groq_api_key=..., model_name=...)
    """

    # Pydantic v2: field tambahan harus didefinisikan atau pakai model_config
    model_config = {"arbitrary_types_allowed": True}

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Sync path — dipanggil oleh RAGAS saat run di thread."""
        estimated = _estimate_tokens(messages)
        _get_throttle(self.model_name).wait_and_record(estimated)
        kwargs["n"] = 1
        logger.debug("🔄 _generate [%s]: ~%d token", self.model_name, estimated)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async path — dipanggil jika RAGAS pakai await."""
        estimated = _estimate_tokens(messages)
        throttle = _get_throttle(self.model_name)
        # throttle pakai threading.Lock — aman dipanggil dari thread sync
        # tapi dari async context kita perlu run di executor agar tidak block event loop
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, throttle.wait_and_record, estimated)
        kwargs["n"] = 1
        logger.debug("🔄 _agenerate [%s]: ~%d token", self.model_name, estimated)
        return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)