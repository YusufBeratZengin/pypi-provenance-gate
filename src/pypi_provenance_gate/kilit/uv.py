"""Parser for ``uv.lock`` (uv's TOML lockfile, lock format v1)."""

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

_YEREL_KAYNAKLAR = frozenset({"editable", "virtual", "directory", "path"})


def _dosya_nesnesi(ham: object, baglam: str) -> Dosya | None:
    if not isinstance(ham, dict) or "url" not in ham:
        return None
    url = ham.get("url")
    if not isinstance(url, str) or not url:
        return None
    h = ham.get("hash")
    return Dosya(
        ad=dosya_adi_url_den(url),
        sha256=sha256_temizle(h, baglam) if h is not None else None,
        url=url,
    )


def ayristir(metin: str, ad: str = "uv.lock", yol: str = "uv.lock") -> KilitDosyasi:
    try:
        veri = tomllib.loads(metin)
    except tomllib.TOMLDecodeError as exc:
        raise KilitHatasi(f"{ad}: geçersiz TOML ({exc})") from exc
    if not isinstance(veri, dict):
        raise KilitHatasi(f"{ad}: beklenen TOML tablosu")
    girdiler = veri.get("package", [])
    if not isinstance(girdiler, list):
        raise KilitHatasi(f"{ad}: [[package]] listesi bekleniyordu")

    sonuc = KilitDosyasi(yol=yol, tur="uv")
    for girdi in girdiler:
        if not isinstance(girdi, dict):
            raise KilitHatasi(f"{ad}: [[package]] girişi tablo değil")
        isim = girdi.get("name")
        kaynak = girdi.get("source", {})
        if not isinstance(kaynak, dict):
            raise KilitHatasi(f"{ad}: package.source tablo değil")
        if "registry" in kaynak:
            indeks = str(kaynak["registry"])
        elif "git" in kaynak or "url" in kaynak:
            indeks = str(kaynak.get("git") or kaynak.get("url"))
        else:
            tur = next(iter(kaynak), "bilinmeyen")
            if tur in _YEREL_KAYNAKLAR:
                sonuc.uyarilar.append(
                    f"{isim or '?'}: yerel kaynak ({tur}) — PyPI paketi değil, atlandı"
                )
                continue
            raise KilitHatasi(f"{ad}: {isim or '?'} için bilinmeyen kaynak türü: {tur}")

        dosyalar: list[Dosya] = []
        tekerlekler = girdi.get("wheels", [])
        if not isinstance(tekerlekler, list):
            raise KilitHatasi(f"{ad}: {isim}.wheels listesi bekleniyordu")
        for ham in tekerlekler:
            d = _dosya_nesnesi(ham, f"{ad}: {isim}")
            if d is not None:
                dosyalar.append(d)
        sdist = _dosya_nesnesi(girdi.get("sdist"), f"{ad}: {isim}")
        if sdist is not None:
            dosyalar.append(sdist)

        sonuc.paketler.append(
            paket_olustur(
                ad=isim,
                surum=girdi.get("version"),
                dosyalar=dosyalar,
                kaynak=indeks,
                kilit_dosyasi=ad,
            )
        )
    if not sonuc.paketler and not sonuc.uyarilar:
        raise KilitHatasi(f"{ad}: hiç paket bulunamadı")
    return sonuc
