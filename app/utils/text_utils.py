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

def remove_header_footer_candidates(
    lines: list[str],
    threshold: int = 3,
) -> list[str]:
    """
    Remove lines that appear *threshold* or more times across the document
    (likely repeating headers or footers).

    Args:
        lines: All lines from all pages.
        threshold: Minimum occurrences to be considered a header/footer.

    Returns:
        Filtered list with header/footer lines removed.
    """
    from collections import Counter

    stripped_lines = [l.strip() for l in lines]
    counts = Counter(s for s in stripped_lines if s)

    repeating = {line for line, count in counts.items() if count >= threshold}

    return [l for l in lines if l.strip() not in repeating]


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
