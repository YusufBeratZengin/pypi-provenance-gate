"""Shared helpers for the lockfile parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..model import Dosya, Paket

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class KilitHatasi(ValueError):
    """Raised when a lockfile cannot be read or parsed."""


@dataclass
class KilitDosyasi:
    yol: str
    tur: str
    paketler: list[Paket] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)


def sha256_temizle(deger: object, baglam: str = "hash") -> str:
    """Accept ``sha256:ABC…`` / bare hex, return lowercase hex, validate length."""
    if not isinstance(deger, str):
        raise KilitHatasi(f"{baglam}: hash bir metin olmalı, bulunan: {type(deger).__name__}")
    d = deger.strip().lower()
    if d.startswith("sha256:"):
        d = d[len("sha256:") :]
    if not _SHA256.match(d):
        raise KilitHatasi(f"{baglam}: geçersiz sha256 değeri ({deger!r})")
    return d


def dosya_adi_url_den(url: str | None) -> str | None:
    """Extract the release filename from a file URL (query string stripped)."""
    if not url:
        return None
    from urllib.parse import unquote, urlparse

    yol = urlparse(url).path
    ad = unquote(yol.rsplit("/", 1)[-1])
    return ad or None


def _metinden(deger: object, alan: str, baglam: str) -> str:
    if not isinstance(deger, str) or not deger.strip():
        raise KilitHatasi(f"{baglam}: '{alan}' alanı eksik veya boş")
    return deger.strip()


def paket_olustur(
    *,
    ad: object,
    surum: object,
    dosyalar: list[Dosya],
    kaynak: object = "https://pypi.org/simple",
    kilit_dosyasi: str,
    notlar: list[str] | None = None,
) -> Paket:
    baglam = f"{kilit_dosyasi}: paket"
    isim = _metinden(ad, "name", baglam)
    s = _metinden(surum, "version", f"{baglam} {isim}")
    if not isinstance(kaynak, str) or not kaynak.strip():
        kaynak = "https://pypi.org/simple"
    return Paket(
        ad=isim,
        surum=s,
        dosyalar=tuple(dosyalar),
        kaynak=kaynak.strip(),
        kilit_dosyasi=kilit_dosyasi,
        notlar=tuple(notlar or ()),
    )


def yukle(yol: str | Path) -> KilitDosyasi:
    """Read a lockfile from disk. Thin wrapper over :func:`ayristir`."""
    from . import ayristir

    p = Path(yol)
    try:
        metin = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise KilitHatasi(f"{p}: dosya okunamadı ({exc.strerror or exc})") from exc
    return ayristir(metin, p.name, yol=str(p))
