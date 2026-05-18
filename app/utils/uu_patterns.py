"""
app/utils/uu_patterns.py
==========================
Regex patterns and helpers for detecting the hierarchical structure
of Indonesian legal documents (Undang-Undang).

Detects:
- BAB  (chapter):  BAB I, BAB II, BAB X, ...
- Pasal (article): Pasal 1, Pasal 12, ...
- Ayat (clause):   (1), (2), (3), ...
- Bagian (section): Bagian Kesatu, Bagian Pertama, ...
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Tuple


# ─────────────────────────────────────────────────────────
# REGEX PATTERNS
# ─────────────────────────────────────────────────────────

_RE_BAB = re.compile(
    r"^\s*BAB\s+"
    r"(M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})|[IVXLCDM]+|\d+)"
    r"(?:\s+(.+))?$",
    re.IGNORECASE,
)

_RE_PASAL = re.compile(
    r"^\s*Pasal\s+(\d+[A-Za-z]?)\s*$",
    re.IGNORECASE,
)

_RE_AYAT = re.compile(
    r"^\s*\((\d+)\)\s+",
)

_RE_BAGIAN = re.compile(
    r"^\s*Bagian\s+(Kesatu|Kedua|Ketiga|Keempat|Kelima|Keenam|Ketujuh|Kedelapan|Kesembilan|Kesepuluh|Pertama|[IVXLCDM]+|\d+)\b",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────
# MATCH RESULT
# ─────────────────────────────────────────────────────────

@dataclass
class StructureMatch:
    """Result of a structure detection attempt."""
    level: str          # "bab", "pasal", "ayat", "bagian", "other"
    number: str = ""    # Roman/Arabic numeral extracted
    title: str = ""     # Inline title text, if any


# ─────────────────────────────────────────────────────────
# DETECTION FUNCTIONS
# ─────────────────────────────────────────────────────────

def is_bab_header(line: str) -> bool:
    """Return True if line is a BAB header."""
    return bool(_RE_BAB.match(line.strip()))


def is_pasal_header(line: str) -> bool:
    """Return True if line is a Pasal header."""
    return bool(_RE_PASAL.match(line.strip()))


def is_ayat(line: str) -> bool:
    """Return True if line starts with an ayat marker like (1)."""
    return bool(_RE_AYAT.match(line.strip()))


def is_bagian_header(line: str) -> bool:
    """Return True if line is a Bagian header."""
    return bool(_RE_BAGIAN.match(line.strip()))


def detect_structure_level(line: str) -> Tuple[str, Optional[StructureMatch]]:
    """
    Detect the hierarchy level of a single line.

    Returns:
        (level_name, StructureMatch | None)
        level_name ∈ {"bab", "pasal", "ayat", "bagian", "other"}
    """
    stripped = line.strip()

    m = _RE_BAB.match(stripped)
    if m:
        number = m.group(1) or ""
        title = m.group(2) or ""
        return "bab", StructureMatch(level="bab", number=number, title=title)

    m = _RE_PASAL.match(stripped)
    if m:
        number = m.group(1) or ""
        return "pasal", StructureMatch(level="pasal", number=number, title=f"Pasal {number}")

    m = _RE_AYAT.match(stripped)
    if m:
        number = m.group(1) or ""
        return "ayat", StructureMatch(level="ayat", number=number, title=f"({number})")

    m = _RE_BAGIAN.match(stripped)
    if m:
        number = m.group(1) or ""
        return "bagian", StructureMatch(level="bagian", number=number, title=stripped)

    return "other", None


def extract_uu_metadata(text: str) -> dict:
    """
    Extract basic metadata from the opening of a legal document text.

    Returns a dict with keys: jenis, nomor, tahun, tentang (all optional).
    """
    metadata: dict = {}

    # Match: "UNDANG-UNDANG REPUBLIK INDONESIA NOMOR 11 TAHUN 2008"
    m = re.search(
        r"(UNDANG-UNDANG|PERATURAN PEMERINTAH|PERATURAN PRESIDEN|PERATURAN MENTERI)"
        r"(?:\s+REPUBLIK INDONESIA)?"
        r"\s+NOMOR\s+(\d+)\s+TAHUN\s+(\d{4})",
        text[:3000],
        re.IGNORECASE,
    )
    if m:
        metadata["jenis"] = m.group(1).title()
        metadata["nomor"] = m.group(2)
        metadata["tahun"] = m.group(3)

    # Match: "TENTANG ..."
    m2 = re.search(r"TENTANG\s+(.+?)(?:\n|$)", text[:3000], re.IGNORECASE)
    if m2:
        metadata["tentang"] = m2.group(1).strip().title()

    return metadata
