"""Parser for ``poetry.lock`` (Poetry 1.x and 2.x)."""

from __future__ import annotations

import tomllib

from ..model import Dosya
from .ortak import KilitDosyasi, KilitHatasi, paket_olustur, sha256_temizle


def ayristir(metin: str, ad: str = "poetry.lock", yol: str = "poetry.lock") -> KilitDosyasi:
    try:
        veri = tomllib.loads(metin)
    except tomllib.TOMLDecodeError as exc:
        raise KilitHatasi(f"{ad}: geçersiz TOML ({exc})") from exc
    if not isinstance(veri, dict):
        raise KilitHatasi(f"{ad}: beklenen TOML tablosu")
    girdiler = veri.get("package", [])
    if not isinstance(girdiler, list):
        raise KilitHatasi(f"{ad}: [[package]] listesi bekleniyordu")

    sonuc = KilitDosyasi(yol=yol, tur="poetry")
    for girdi in girdiler:
        if not isinstance(girdi, dict):
            raise KilitHatasi(f"{ad}: [[package]] girişi tablo değil")
        isim = girdi.get("name")
        kaynak = girdi.get("source")
        indeks = "https://pypi.org/simple"
        if isinstance(kaynak, dict):
            tur = kaynak.get("type")
            url = kaynak.get("url")
            if tur == "legacy" and isinstance(url, str) and url:
                indeks = url
            elif tur in {"git", "directory", "file", "url"}:
                sonuc.uyarilar.append(
                    f"{isim or '?'}: PyPI dışı kaynak ({tur}) — kaynak kanıtı sorgulanamaz"
                )
                indeks = str(url or tur)

        dosyalar: list[Dosya] = []
        ham_dosyalar = girdi.get("files", [])
        if not isinstance(ham_dosyalar, list):
            raise KilitHatasi(f"{ad}: {isim}.files listesi bekleniyordu")
        for d in ham_dosyalar:
            if not isinstance(d, dict):
                continue
            dosya_adi = d.get("file")
            h = d.get("hash")
            if not isinstance(dosya_adi, str) or not dosya_adi:
                continue
            dosyalar.append(
                Dosya(
                    ad=dosya_adi,
                    sha256=sha256_temizle(h, f"{ad}: {isim}") if h is not None else None,
                )
            )
        sonuc.paketler.append(
            paket_olustur(
                ad=isim,
                surum=girdi.get("version"),
                dosyalar=dosyalar,
                kaynak=indeks,
                kilit_dosyasi=ad,
            )
        )
    if not sonuc.paketler:
        raise KilitHatasi(f"{ad}: hiç paket bulunamadı")
    return sonuc
