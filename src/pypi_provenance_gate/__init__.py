"""Library entry points.

from pypi_provenance_gate import kilit, IntegrityIstemcisi, kontrol

kilit_dosyasi = kilit.yukle("uv.lock")
rapor = kontrol(kilit_dosyasi.paketler, IntegrityIstemcisi())
"""

from __future__ import annotations

from .cekirdek import kontrol
from .integrity import AgHatasi, IntegrityIstemcisi, UrllibTasima
from .model import Dosya, Durum, Kanit, Paket, PaketSonuc, Rapor
from .surum import SURUM as __version__

__all__ = [
    "AgHatasi",
    "Dosya",
    "Durum",
    "IntegrityIstemcisi",
    "Kanit",
    "Paket",
    "PaketSonuc",
    "Rapor",
    "UrllibTasima",
    "__version__",
    "kontrol",
]
