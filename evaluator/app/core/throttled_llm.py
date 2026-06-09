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
from typing import Any, List, Optional
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)


class _SlidingWindowThrottle:
    """
    Sliding window rate limiter berbasis token.

    Groq llama-3.1-8b-instant limit: 6000 TPM.
    Kita target 4500 TPM (buffer 25%) = aman untuk burst kecil.

    Cara kerja:
        Simpan timestamp setiap request dalam window 60 detik terakhir.
        Jika total token dalam window >= limit → sleep sampai window geser.
        Tambah hard floor 1.2 detik antar request untuk cegah burst.
    """

    def __init__(self, tpm_limit: int = 4500, min_gap_sec: float = 1.2):
        self._tpm_limit = tpm_limit
        self._min_gap = min_gap_sec
        self._window: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._lock = threading.Lock()
        self._last_request = 0.0

    def _evict_old(self, now: float):
        """Buang entri yang lebih dari 60 detik lalu."""
        cutoff = now - 60.0
        self._window = [(t, tok) for t, tok in self._window if t > cutoff]

    def _tokens_in_window(self) -> int:
        return sum(tok for _, tok in self._window)

    def wait_and_record(self, estimated_tokens: int):
        """
        Blokir sampai aman untuk kirim request dengan estimasi token ini.
        Lalu catat request ke window.
        """
        with self._lock:
            # --- Hard floor gap antar request ---
            now = time.monotonic()
            gap = now - self._last_request
            if gap < self._min_gap:
                sleep_gap = self._min_gap - gap
                logger.debug("⏳ Gap floor: sleep %.2fs", sleep_gap)
                time.sleep(sleep_gap)

            # --- Sliding window check ---
            while True:
                now = time.monotonic()
                self._evict_old(now)
                used = self._tokens_in_window()

                if used + estimated_tokens <= self._tpm_limit:
                    break  # Aman untuk jalan

                # Hitung kapan token tertua keluar dari window
                oldest_ts = self._window[0][0]
                wait_until = oldest_ts + 60.0
                sleep_sec = max(0.1, wait_until - now)
                logger.info(
                    "⏳ TPM window penuh (%d/%d token). Sleep %.1fs",
                    used, self._tpm_limit, sleep_sec
                )
                time.sleep(sleep_sec)

            # --- Catat request ini ---
            now = time.monotonic()
            self._window.append((now, estimated_tokens))
            self._last_request = now
            logger.debug(
                "✅ Request diizinkan: +%d token, total window=%d/%d",
                estimated_tokens,
                self._tokens_in_window(),
                self._tpm_limit,
            )


_throttle = _SlidingWindowThrottle(tpm_limit=4500, min_gap_sec=1.2)


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
        _throttle.wait_and_record(estimated)
        kwargs["n"] = 1
        logger.debug("🔄 _generate: ~%d token", estimated)
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
        # _throttle pakai threading.Lock — aman dipanggil dari thread sync
        # tapi dari async context kita perlu run di executor agar tidak block event loop
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _throttle.wait_and_record, estimated)
        kwargs["n"] = 1
        logger.debug("🔄 _agenerate: ~%d token", estimated)
        return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)