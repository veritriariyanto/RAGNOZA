"""
app/utils/text_utils.py
========================
Shared text processing helpers used by the cleaning and chunking pipelines.
"""

import re
import unicodedata


# ─────────────────────────────────────────────────────────
# UNICODE / ENCODING
# ─────────────────────────────────────────────────────────

def normalize_unicode(text: str) -> str:
    """Normalize Unicode to NFC form and remove control characters."""
    text = unicodedata.normalize("NFC", text)
    # Remove zero-width chars and other invisible control chars
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)
    return text


def fix_common_pdf_artifacts(text: str) -> str:
    """
    Fix common PDF extraction artifacts:
    - Ligatures (ﬁ → fi, ﬂ → fl, etc.)
    - Soft hyphens
    - Non-breaking spaces
    """
    replacements = {
        "\ufb01": "fi",   # ﬁ
        "\ufb02": "fl",   # ﬂ
        "\ufb03": "ffi",  # ﬃ
        "\ufb04": "ffl",  # ﬄ
        "\ufb00": "ff",   # ﬀ
        "\u00ad": "",     # soft hyphen
        "\u00a0": " ",    # non-breaking space
        "\u2019": "'",    # right single quotation mark
        "\u2018": "'",    # left single quotation mark
        "\u201c": '"',    # left double quotation mark
        "\u201d": '"',    # right double quotation mark
        "\u2013": "-",    # en dash
        "\u2014": "-",    # em dash
        "\u2026": "...",  # ellipsis
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


# ─────────────────────────────────────────────────────────
# WHITESPACE
# ─────────────────────────────────────────────────────────

def normalize_whitespace(text: str) -> str:
    """
    - Collapse multiple spaces/tabs into a single space on each line.
    - Collapse 3+ consecutive newlines into 2.
    - Strip leading/trailing whitespace.
    """
    # Normalize horizontal whitespace within lines
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    text = "\n".join(lines)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─────────────────────────────────────────────────────────
# PAGE NUMBER REMOVAL
# ─────────────────────────────────────────────────────────

_PAGE_NUMBER_PATTERNS = [
    re.compile(r"^\s*-\s*\d+\s*-\s*$"),       # - 1 -
    re.compile(r"^\s*\d+\s*$"),                # standalone number
    re.compile(r"^\s*Halaman\s+\d+\s*$", re.IGNORECASE),  # Halaman 5
    re.compile(r"^\s*Page\s+\d+\s*$", re.IGNORECASE),     # Page 5
]


def remove_page_numbers(text: str) -> str:
    """Remove standalone page number lines from text."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        if not any(p.match(line) for p in _PAGE_NUMBER_PATTERNS):
            cleaned.append(line)
    return "\n".join(cleaned)


# ─────────────────────────────────────────────────────────
# HEADER / FOOTER REMOVAL
# ─────────────────────────────────────────────────────────

def _is_valid_header_footer_candidate(line: str) -> bool:
    """
    Check if a line is a realistic candidate for a header or footer.
    Excludes regular legal clauses, sentence endings, list bullets, or standalone page numbers.
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Exclude lines ending with typical sentence/clause punctuation
    if re.search(r"[\.,;:]$", stripped):
        return False
    # Exclude standalone numbers or list bullets, e.g., "(1)", "1.", "a."
    if re.match(r"^\s*\(?\d+\)?\.?\s*$", stripped):
        return False
    if re.match(r"^\s*\(?[a-zA-Z]\)?\.?\s*$", stripped):
        return False
    # Exclude short lines that look like numbers or list items
    if len(stripped) < 4 and any(c.isdigit() for c in stripped):
        return False
    return True


def remove_header_footer_candidates(
    pages_or_lines: list,
    threshold: int = 3,
) -> list:
    """
    Remove repeating headers and footers.
    Supports two input formats:
    1. A list of pages, where each page is a list of lines (list[list[str]]).
       This is the recommended, safe page-aware mode.
    2. A flat list of lines (list[str]). This is the legacy mode.
    """
    if not pages_or_lines:
        return pages_or_lines

    # Check if we are dealing with list[list[str]] (page-aware)
    if isinstance(pages_or_lines[0], list):
        pages_lines = pages_or_lines
        from collections import Counter

        top_candidates = Counter()
        bottom_candidates = Counter()

        # Step 1: Collect candidates from top 2 and bottom 2 non-empty lines of each page
        for lines in pages_lines:
            cleaned_lines = [l.strip() for l in lines if l.strip()]
            if not cleaned_lines:
                continue
            
            # Top 2 lines
            for i in range(min(2, len(cleaned_lines))):
                candidate = cleaned_lines[i]
                if _is_valid_header_footer_candidate(candidate):
                    top_candidates[candidate] += 1
                
            # Bottom 2 lines
            for i in range(min(2, len(cleaned_lines))):
                idx = len(cleaned_lines) - 1 - i
                if idx >= 2:  # Don't overlap with top
                    candidate = cleaned_lines[idx]
                    if _is_valid_header_footer_candidate(candidate):
                        bottom_candidates[candidate] += 1

        # Step 2: Identify repeating headers/footers
        # A header/footer should repeat on at least `threshold` pages
        repeating_headers = {line for line, count in top_candidates.items() if count >= threshold}
        repeating_footers = {line for line, count in bottom_candidates.items() if count >= threshold}

        # Step 3: Remove candidates ONLY if they appear at the top/bottom positions of a page
        filtered_pages = []
        for lines in pages_lines:
            if not lines:
                filtered_pages.append([])
                continue
                
            n = len(lines)
            to_remove = set()
            
            # Top lines (first 2 non-empty lines)
            non_empty_top = []
            for idx, l in enumerate(lines):
                if l.strip():
                    non_empty_top.append((idx, l.strip()))
                    if len(non_empty_top) >= 2:
                        break
            for idx, stripped in non_empty_top:
                if stripped in repeating_headers:
                    to_remove.add(idx)

            # Bottom lines (last 2 non-empty lines)
            non_empty_bottom = []
            for idx in range(n - 1, -1, -1):
                l = lines[idx]
                if l.strip():
                    non_empty_bottom.append((idx, l.strip()))
                    if len(non_empty_bottom) >= 2:
                        break
            for idx, stripped in non_empty_bottom:
                if idx not in to_remove:
                    if stripped in repeating_footers:
                        to_remove.add(idx)

            filtered_lines = [l for idx, l in enumerate(lines) if idx not in to_remove]
            filtered_pages.append(filtered_lines)

        return filtered_pages

    else:
        # Legacy flat-list mode
        from collections import Counter
        lines = pages_or_lines
        stripped_lines = [l.strip() for l in lines]
        counts = Counter(s for s in stripped_lines if s)
        repeating = {line for line, count in counts.items() if count >= threshold}
        return [l for l in lines if l.strip() not in repeating]


# ─────────────────────────────────────────────────────────
# TEXT REPAIR
# ─────────────────────────────────────────────────────────

def repair_hyphenation(text: str) -> tuple[str, int]:
    """
    Gabungkan kata yang terpotong oleh tanda hubung di akhir baris.

    Contoh:
        "pem-\\nbangunan"  → "pembangunan"
        "undang-\\nundang" → "undang-undang"  (hyphen semantik dipertahankan)

    Strategi:
    - Jika suku kata sebelum '-\\n' adalah ≥ 2 karakter → join tanpa spasi.
    - Khusus bentuk reduplikasi (undang-undang, tindak-tindakan) biarkan.

    Returns:
        (repaired_text, count)  — count adalah jumlah perbaikan yang dilakukan.
    """
    count = 0

    # 1. Reduplikasi: kata-\nkata -> kata-kata (keep hyphen)
    def _reduplication_replacer(m: re.Match) -> str:
        nonlocal count
        count += 1
        return m.group(1) + "-" + m.group(2)
        
    text = re.sub(r"\b([A-Za-z]{2,})-\n(\1)\b", _reduplication_replacer, text, flags=re.IGNORECASE)

    # 2. Kata terpotong biasa: pem-\nbangunan -> pembangunan (delete hyphen)
    def _replacer(m: re.Match) -> str:
        nonlocal count
        count += 1
        return m.group(1) + m.group(2)

    text = re.sub(r"([A-Za-z]{2,})-\n([a-z])", _replacer, text)
    return text, count


def repair_spaced_characters(text: str) -> tuple[str, int]:
    """
    Perbaiki kata yang karakternya terpisah oleh spasi karena artefak PDF.

    Contoh:
        "u n d a n g - u n d a n g" → "undang-undang"
        "P a s a l"                  → "Pasal"

    Hanya memperbaiki blok yang seluruhnya terdiri dari huruf tunggal
    dipisah spasi (≥ 3 karakter), tidak menyentuh teks normal.

    Returns:
        (repaired_text, count)  — count adalah jumlah blok yang diperbaiki.
    """
    count = 0

    def _join_spaced(m: re.Match) -> str:
        nonlocal count
        count += 1
        return m.group(0).replace(" ", "")

    text = re.sub(r"\b(?:[A-Za-z] ){2,}[A-Za-z]\b", _join_spaced, text)
    return text, count


# Kamus koreksi karakter OCR umum untuk teks Latin/Indonesia
_OCR_CHAR_MAP: dict[str, str] = {
    # angka yang terbaca sebagai huruf
    "0": "O",   # tidak dipakai karena ambigu – gunakan konteks kata
    # huruf yang terbaca sebagai angka dalam kata
}

# Pola OCR noise spesifik dokumen hukum Indonesia
_OCR_NOISE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "l" (el) yang terbaca sebagai "1" (satu) di tengah kata huruf
    (re.compile(r"(?<=[A-Za-z])1(?=[A-Za-z])"), "l"),
    # "I" (i besar) yang terbaca sebagai "|" di tengah kata
    (re.compile(r"(?<=[A-Za-z])\|(?=[A-Za-z])"), "I"),
    # "rn" yang terbaca sebagai "m" (jarang, tapi terjadi)
    # Tidak diaktifkan default karena bisa menimbulkan false positive
    # Tanda baca ganda akibat scanner (mis: ".." → ".")
    (re.compile(r"\.{3,}"), "..."),   # normalkan ellipsis berlebih
    (re.compile(r",{2,}"), ","),
    (re.compile(r";{2,}"), ";"),
    # Karakter kotak / placeholder PDF yang gagal decode
    (re.compile(r"[\ufffd\u25a1\u25a0\u25cf]"), ""),
    # Strip karakter non-printable selain newline/tab
    (re.compile(r"[^\x09\x0A\x0D\x20-\x7E\x80-\xFF\u00C0-\u024F\u0100-\u017E]"), ""),
]


def repair_ocr_noise(text: str) -> tuple[str, int]:
    """
    Bersihkan noise OCR / PDF rendering:
    - Karakter pengganti (replacement characters)
    - Tanda baca ganda karena scan
    - Karakter kontrol non-printable

    Returns:
        (repaired_text, count)  — count adalah total substitusi karakter.
    """
    total = 0
    for pattern, replacement in _OCR_NOISE_PATTERNS:
        result, n = re.subn(pattern, replacement, text)
        text = result
        total += n
    return text, total


def repair_broken_sentences(text: str) -> tuple[str, int]:
    """
    Gabungkan kalimat yang terpecah oleh line break paksa (hard wrap) dari PDF.

    Logika:
    - Jika baris berakhir dengan huruf/koma/tanda buka kurung dan baris
      berikutnya diawali dengan huruf kecil/besar (selama bukan structural header) -> gabung.
    - Jangan gabung jika baris berikutnya adalah header struktur
      (BAB, Pasal, Menimbang, dll.) atau dimulai dengan '(' untuk ayat.
    - Jangan gabung jika baris saat ini berakhir titik/titik dua yang menutup kalimat/pasal,
      KECUALI baris berikutnya diawali huruf kecil (lanjutan/singkatan).

    Returns:
        (repaired_text, count)  — count adalah jumlah penggabungan baris.
    """
    _STRUCT_START = re.compile(
        r"^\s*(?:BAB\s|Pasal\s|\(\d+\)|[a-z]\.\s|[A-Z]\.\s|Menimbang|Mengingat|"
        r"MEMUTUSKAN|PENJELASAN|Bagian\s|Paragraf\s|\d+\.\s)",
        re.IGNORECASE,
    )

    lines = text.split("\n")
    result: list[str] = []
    count = 0
    i = 0
    while i < len(lines):
        current = lines[i]
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            cur_stripped = current.rstrip()
            nxt_stripped = nxt.lstrip()

            ends_with_sentence_end = re.search(r"[\.\?:!]$", cur_stripped)
            ends_with_continuation = re.search(r"[A-Za-z0-9,;\(\[-]$", cur_stripped)

            should_join = False
            if cur_stripped and nxt_stripped and not _STRUCT_START.match(nxt_stripped):
                if ends_with_continuation and not ends_with_sentence_end:
                    should_join = True
                elif ends_with_sentence_end and re.match(r"^[a-z0-9]", nxt_stripped):
                    should_join = True

            if should_join:
                lines[i + 1] = cur_stripped + " " + nxt_stripped
                count += 1
                i += 1
                continue

        result.append(current)
        i += 1

    return "\n".join(result), count


def repair_text(text: str) -> str:
    """
    Pipeline repair teks lengkap (versi tanpa stats — untuk backward compatibility).

    Urutan penting:
    1. repair_hyphenation       → gabung suku kata sebelum whitespace collapse
    2. repair_spaced_characters → gabung karakter terpisah
    3. repair_ocr_noise         → bersihkan noise karakter
    4. repair_broken_sentences  → gabung kalimat terpecah (setelah baris bersih)

    Returns:
        Teks yang telah diperbaiki dan siap untuk proses chunking.
    """
    text, _ = repair_hyphenation(text)
    text, _ = repair_spaced_characters(text)
    text, _ = repair_ocr_noise(text)
    text, _ = repair_broken_sentences(text)
    return text


def repair_text_with_stats(text: str) -> tuple[str, dict]:
    """
    Pipeline repair teks lengkap dengan statistik perbaikan.

    Returns:
        (repaired_text, stats) di mana stats adalah dict:
        {
            "hyphenation_fixes":       int,   # kata terpotong yang disambung
            "spaced_char_fixes":       int,   # blok karakter terpisah yang diperbaiki
            "ocr_noise_fixes":         int,   # karakter noise yang dihapus/diganti
            "broken_sentence_fixes":   int,   # baris yang digabung
            "total_fixes":             int,   # jumlah semua perbaikan
            "was_repaired":            bool,  # True jika ada setidaknya 1 perbaikan
        }
    """
    text, hyph  = repair_hyphenation(text)
    text, spced = repair_spaced_characters(text)
    text, ocr   = repair_ocr_noise(text)
    text, brkn  = repair_broken_sentences(text)

    total = hyph + spced + ocr + brkn
    stats = {
        "hyphenation_fixes":     hyph,
        "spaced_char_fixes":     spced,
        "ocr_noise_fixes":       ocr,
        "broken_sentence_fixes": brkn,
        "total_fixes":           total,
        "was_repaired":          total > 0,
    }
    return text, stats


# ─────────────────────────────────────────────────────────
# TOKEN COUNTING
# ─────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """
    Approximate token count using whitespace splitting.
    For a more accurate count, replace with tiktoken or a tokenizer.

    Rule of thumb: 1 token ≈ 0.75 words (English), ~1 word (Indonesian).
    We use a simple word-split here for speed and zero dependencies.
    """
    if not text:
        return 0
    words = text.split()
    # Approximate: 1 token per word for Indonesian legal text
    return len(words)
