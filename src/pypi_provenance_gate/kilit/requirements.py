"""Parser for hash-pinned ``requirements.txt`` files.

Only lines that pin an exact version (``name==1.2.3``) are used. Lines with a
hash carry no filename, so the release files are resolved through the PyPI JSON
API later and matched by SHA-256.
"""

from __future__ import annotations

import re
from typing import Any

from ..model import Dosya
from .ortak import KilitDosyasi, KilitHatasi, paket_olustur, sha256_temizle

# name[extras]==version ; rest --hash=sha256:... --hash=sha256:...
_PIN = re.compile(
    r"^(?P<ad>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"\s*(?:\[[^\]]*\])?\s*"
    r"(?P<op>===|==)\s*"
    r"(?P<surum>[^\s;#]+)"
)
_HASH = re.compile(r"--hash[=\s]+(?P<algo>[A-Za-z0-9]+):(?P<deger>\S+)")


def _mantiksal_satirlar(metin: str) -> list[tuple[int, str]]:
    """Join backslash continuations, keeping the first physical line number."""
    satirlar: list[tuple[int, str]] = []
    tampon = ""
    baslangic = 0
    for i, ham in enumerate(metin.splitlines(), start=1):
        if not tampon:
            baslangic = i
        if ham.rstrip().endswith("\\"):
            tampon += ham.rstrip()[:-1] + " "
            continue
        tampon += ham
        satirlar.append((baslangic, tampon))
        tampon = ""
    if tampon:
        satirlar.append((baslangic, tampon))
    return satirlar


def ayristir(
    metin: str, ad: str = "requirements.txt", yol: str = "requirements.txt"
) -> KilitDosyasi:
    sonuc = KilitDosyasi(yol=yol, tur="requirements")
    indeks = "https://pypi.org/simple"
    for no, ham in _mantiksal_satirlar(metin):
        satir = ham.split(" #", 1)[0].strip()
        if not satir or satir.startswith("#"):
            continue
        if satir.startswith("-"):
            if satir.startswith(("--index-url", "-i ")):
                parcalar = satir.replace("=", " ").split()
                if len(parcalar) >= 2:
                    indeks = parcalar[1]
                continue
            if satir.startswith(("--extra-index-url", "-r", "--requirement", "-c")):
                sonuc.uyarilar.append(f"satır {no}: içe aktarma/seçenek satırı desteklenmiyor")
                continue
            if satir.startswith("--hash"):
                continue
            sonuc.uyarilar.append(f"satır {no}: bilinmeyen seçenek yok sayıldı")
            continue
        satir = satir.split(";", 1)[0].strip()  # ortam işaretleri yok sayılır
        eslesme = _PIN.match(satir)
        if eslesme is None:
            sonuc.uyarilar.append(f"satır {no}: tam sürüm sabitlenmemiş ({satir[:40]!r}) — atlandı")
            continue
        surum = eslesme.group("surum")
        if eslesme.group("op") == "===":
            sonuc.uyarilar.append(f"satır {no}: '===' keyfi eşitlik — PyPI sürümü olarak arandı")
        kuyruk = satir[eslesme.end() :]
        hashlar: list[str] = []
        for h in _HASH.finditer(kuyruk):
            if h.group("algo").lower() != "sha256":
                sonuc.uyarilar.append(f"satır {no}: sha256 dışı hash yok sayıldı")
                continue
            hashlar.append(sha256_temizle(h.group("deger"), f"{ad}: satır {no}"))
        if not hashlar:
            sonuc.uyarilar.append(f"satır {no}: hash yok — dosya adı PyPI'dan çözülecek")
        dosyalar: list[Dosya] = [Dosya(ad=None, sha256=h) for h in hashlar] or [Dosya(ad=None)]
        sonuc.paketler.append(
            paket_olustur(
                ad=eslesme.group("ad"),
                surum=surum,
                dosyalar=dosyalar,
                kaynak=indeks,
                kilit_dosyasi=ad,
            )
        )
    if not sonuc.paketler:
        raise KilitHatasi(f"{ad}: tam sürümlenmiş hiç gereksinim bulunamadı")
    return sonuc


def _kullanilmayan(_: Any) -> None:  # pragma: no cover - typing yardımcısı
    return None
