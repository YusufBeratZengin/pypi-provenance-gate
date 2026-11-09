"""Parser for ``pylock.toml`` (PEP 751, lock format 1.0)."""

from __future__ import annotations

import tomllib

from ..model import Dosya
from .ortak import (
    KilitDosyasi,
    KilitHatasi,
    dosya_adi_url_den,
    paket_olustur,
    sha256_temizle,
)


def _hash_sha256(ham: object, baglam: str) -> str | None:
    if isinstance(ham, dict):
        deger = ham.get("sha256")
        return sha256_temizle(deger, baglam) if deger is not None else None
    if isinstance(ham, list):
        for satir in ham:
            if isinstance(satir, str) and satir.lower().startswith("sha256:"):
                return sha256_temizle(satir, baglam)
    return None


def ayristir(metin: str, ad: str = "pylock.toml", yol: str = "pylock.toml") -> KilitDosyasi:
    try:
        veri = tomllib.loads(metin)
    except tomllib.TOMLDecodeError as exc:
        raise KilitHatasi(f"{ad}: geçersiz TOML ({exc})") from exc
    if not isinstance(veri, dict):
        raise KilitHatasi(f"{ad}: beklenen TOML tablosu")
    girdiler = veri.get("packages", [])
    if not isinstance(girdiler, list):
        raise KilitHatasi(f"{ad}: [[packages]] listesi bekleniyordu")

    sonuc = KilitDosyasi(yol=yol, tur="pylock")
    for girdi in girdiler:
        if not isinstance(girdi, dict):
            raise KilitHatasi(f"{ad}: [[packages]] girişi tablo değil")
        isim = girdi.get("name")
        dosyalar: list[Dosya] = []
        for anahtar in ("wheels", "sdist"):
            ham = girdi.get(anahtar, [])
            if isinstance(ham, dict):
                ham = [ham]
            if not isinstance(ham, list):
                raise KilitHatasi(f"{ad}: {isim}.{anahtar} listesi bekleniyordu")
            for d in ham:
                if not isinstance(d, dict):
                    continue
                url = d.get("url")
                dosya_adi = d.get("name")
                if not isinstance(dosya_adi, str) or not dosya_adi:
                    dosya_adi = dosya_adi_url_den(url if isinstance(url, str) else None)
                if not dosya_adi:
                    continue
                dosyalar.append(
                    Dosya(
                        ad=dosya_adi,
                        sha256=_hash_sha256(d.get("hashes"), f"{ad}: {isim}"),
                        url=url if isinstance(url, str) else None,
                    )
                )
        sonuc.paketler.append(
            paket_olustur(
                ad=isim,
                surum=girdi.get("version"),
                dosyalar=dosyalar,
                kaynak="https://pypi.org/simple",
                kilit_dosyasi=ad,
            )
        )
    if not sonuc.paketler:
        raise KilitHatasi(f"{ad}: hiç paket bulunamadı")
    return sonuc
