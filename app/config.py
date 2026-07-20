"""
app/config.py
=============
Backwards-compatibility shim.
Import dari app.core.config agar semua modul yang masih
menggunakan `from app.config import settings` tetap berfungsi.
"""
from app.core.config import settings, get_settings  # noqa: F401
