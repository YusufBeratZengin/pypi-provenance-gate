"""Policy file (``politika.toml``), expected publishers and the CI exit code."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .model import (
    Durum,
    Gecis,
    Ihlal,
    Rapor,
    Seviye,
    ad_normallestir,
    depo_normallestir,
)

_RENKLER = {
    "hata": Seviye.HATA,
    "error": Seviye.HATA,
    "uyari": Seviye.UYARI,
    "warning": Seviye.UYARI,
    "warn": Seviye.UYARI,
    "yoksay": Seviye.YOKSAY,
    "ignore": Seviye.YOKSAY,
    "off": Seviye.YOKSAY,
}

_KURALLAR = (
    "kanitsiz",
    "kismi",
    "bilinmiyor",
    "gerileme",
    "yayinci_degisimi",
    "yayinci_uyumsuz",
)

_DURUM_KURAL = {
    Durum.KANITLI: "kanitli",
    Durum.KANITSIZ: "kanitsiz",
    Durum.KISMI: "kismi",
    Durum.BILINMIYOR: "bilinmiyor",
    Durum.ATLANDI: "atlandi",
}


class PolitikaHatasi(ValueError):
    """Invalid policy file."""


@dataclass(frozen=True)
class Politika:
    seviyeler: dict[str, Seviye] = field(
        default_factory=lambda: {
            "kanitsiz": Seviye.UYARI,
            "kismi": Seviye.UYARI,
            "bilinmiyor": Seviye.UYARI,
            "gerileme": Seviye.HATA,
            "yayinci_degisimi": Seviye.HATA,
            "yayinci_uyumsuz": Seviye.HATA,
        }
    )
    kanitsiz_izin: frozenset[str] = frozenset()
    beklenen: dict[str, str] = field(default_factory=dict)
    kaynak: str | None = None

    def seviye(self, kural: str) -> Seviye:
        return self.seviyeler.get(kural, Seviye.UYARI)

    def izinli(self, ad: str, surum: str) -> bool:
        n = ad_normallestir(ad)
        return n in self.kanitsiz_izin or f"{n}=={surum}".lower() in self.kanitsiz_izin


def _seviye(deger: object, anahtar: str) -> Seviye:
    if not isinstance(deger, str) or deger.strip().lower() not in _RENKLER:
        raise PolitikaHatasi(
            f"politika: '{anahtar}' için geçersiz seviye ({deger!r}); hata/uyari/yoksay bekleniyor"
        )
    return _RENKLER[deger.strip().lower()]


def izin_normallestir(deger: str) -> str:
    """Normalise one allowlist entry the same way for CLI and policy file."""
    parca = deger.strip().lower()
    if "==" in parca:
        ad, surum = parca.split("==", 1)
        return f"{ad_normallestir(ad)}=={surum.strip()}"
    return ad_normallestir(parca)


def _metin_listesi(deger: object, anahtar: str) -> list[str]:
    if deger is None:
        return []
    if not isinstance(deger, list):
        raise PolitikaHatasi(f"politika: '{anahtar}' bir liste olmalı")
    sonuc: list[str] = []
    for oge in deger:
        if not isinstance(oge, str) or not oge.strip():
            raise PolitikaHatasi(f"politika: '{anahtar}' içinde metin olmayan öğe")
        sonuc.append(izin_normallestir(oge))
    return sonuc


def _beklenen_tablosu(deger: object) -> dict[str, str]:
    if deger is None:
        return {}
    if not isinstance(deger, dict):
        raise PolitikaHatasi("politika: 'beklenen' bir tablo olmalı")
    sonuc: dict[str, str] = {}
    for ad, depo in deger.items():
        if not isinstance(ad, str) or not isinstance(depo, str) or not depo.strip():
            raise PolitikaHatasi(f"politika: beklenen yayıncı '{ad}' için metin depo bekleniyor")
        norm = depo_normallestir(depo)
        if norm is None:
            raise PolitikaHatasi(f"politika: '{ad}' için geçersiz depo ({depo!r})")
        sonuc[ad_normallestir(ad)] = norm
    return sonuc


def yukle(yol: str | Path, temel: Politika | None = None) -> Politika:
    """Read ``politika.toml``. Unknown keys are rejected to catch typos."""
    p = Path(yol)
    try:
        metin = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolitikaHatasi(f"politika okunamadı: {p} ({exc.strerror or exc})") from exc
    try:
        veri = tomllib.loads(metin)
    except tomllib.TOMLDecodeError as exc:
        raise PolitikaHatasi(f"politika: geçersiz TOML ({exc})") from exc
    if not isinstance(veri, dict):
        raise PolitikaHatasi("politika: beklenen TOML tablosu")
    bilinmeyen = set(veri) - {"genel", "beklenen"}
    if bilinmeyen:
        raise PolitikaHatasi(f"politika: bilinmeyen bölüm(ler): {', '.join(sorted(bilinmeyen))}")

    taban = temel or Politika()
    seviyeler = dict(taban.seviyeler)
    izin = set(taban.kanitsiz_izin)
    genel = veri.get("genel", {})
    if not isinstance(genel, dict):
        raise PolitikaHatasi("politika: [genel] bir tablo olmalı")
    for anahtar, deger in genel.items():
        if anahtar == "kanitsiz_izin":
            izin.update(_metin_listesi(deger, anahtar))
        elif anahtar in _KURALLAR:
            seviyeler[anahtar] = _seviye(deger, anahtar)
        else:
            raise PolitikaHatasi(f"politika: [genel] içinde bilinmeyen anahtar: {anahtar}")

    beklenen = dict(taban.beklenen)
    beklenen.update(_beklenen_tablosu(veri.get("beklenen")))
    return replace(
        taban,
        seviyeler=seviyeler,
        kanitsiz_izin=frozenset(izin),
        beklenen=beklenen,
        kaynak=str(p),
    )


def beklenen_yukle(yol: str | Path) -> dict[str, str]:
    """Read ``beklenen.toml`` which only holds ``[depolar]`` name = repo."""
    p = Path(yol)
    try:
        metin = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolitikaHatasi(f"beklenen dosya okunamadı: {p} ({exc.strerror or exc})") from exc
    try:
        veri = tomllib.loads(metin)
    except tomllib.TOMLDecodeError as exc:
        raise PolitikaHatasi(f"beklenen: geçersiz TOML ({exc})") from exc
    if not isinstance(veri, dict):
        raise PolitikaHatasi("beklenen: beklenen TOML tablosu")
    izinli = {"depolar", "beklenen"}
    fazla = set(veri) - izinli
    if fazla:
        raise PolitikaHatasi(f"beklenen: bilinmeyen bölüm(ler): {', '.join(sorted(fazla))}")
    tablo = veri.get("depolar", veri.get("beklenen", {}))
    return _beklenen_tablosu(tablo)


def varsayilan_ci() -> Politika:
    """Strict policy used by ``--ci`` when no policy file is given."""
    return Politika(
        seviyeler=dict.fromkeys(_KURALLAR, Seviye.HATA),
        kanitsiz_izin=frozenset(),
        beklenen={},
        kaynak=None,
    )


def birlestir(temel: Politika, ek: Politika) -> Politika:
    seviyeler = dict(temel.seviyeler)
    seviyeler.update({k: v for k, v in ek.seviyeler.items() if k in _KURALLAR})
    beklenen = dict(temel.beklenen)
    beklenen.update(ek.beklenen)
    return Politika(
        seviyeler=seviyeler,
        kanitsiz_izin=temel.kanitsiz_izin | ek.kanitsiz_izin,
        beklenen=beklenen,
        kaynak=ek.kaynak or temel.kaynak,
    )


def degerlendir(rapor: Rapor, politika: Politika) -> list[Ihlal]:
    """Fill ``rapor.ihlaller`` and return them."""
    ihlaller: list[Ihlal] = []
    for sonuc in rapor.paketler:
        if sonuc.durum is Durum.ATLANDI:
            continue
        if sonuc.durum is Durum.KANITLI:
            pass
        elif not (sonuc.durum is Durum.KANITSIZ and politika.izinli(sonuc.ad, sonuc.surum)):
            seviye = politika.seviye(_DURUM_KURAL.get(sonuc.durum, sonuc.durum.value))
            if seviye is not Seviye.YOKSAY:
                ihlaller.append(
                    Ihlal(
                        kural=_DURUM_KURAL.get(sonuc.durum, sonuc.durum.value),
                        paket=sonuc.ad,
                        mesaj=f"{sonuc.ad} {sonuc.surum}: {_durum_metni(sonuc.durum)}",
                        seviye=seviye,
                    )
                )
        for kural, gecis, mesaj in (
            ("gerileme", Gecis.GERILEDI, "kanıt geriledi"),
            ("yayinci_degisimi", Gecis.YAYINCI_DEGISTI, "yayıncı deposu değişti"),
        ):
            if sonuc.gecis is gecis:
                seviye = politika.seviye(kural)
                if seviye is not Seviye.YOKSAY:
                    onceki = sonuc.onceki.surum if sonuc.onceki else "?"
                    ihlaller.append(
                        Ihlal(
                            kural=kural,
                            paket=sonuc.ad,
                            mesaj=f"{sonuc.ad}: {mesaj} ({onceki} → {sonuc.surum})",
                            seviye=seviye,
                        )
                    )
        beklenen = politika.beklenen.get(ad_normallestir(sonuc.ad))
        if (
            beklenen
            and sonuc.durum in (Durum.KANITLI, Durum.KISMI)
            and (not sonuc.depolar or any(depo != beklenen for depo in sonuc.depolar))
        ):
            seviye = politika.seviye("yayinci_uyumsuz")
            if seviye is not Seviye.YOKSAY:
                bulunan = ", ".join(sonuc.depolar) or "bilinmiyor"
                ihlaller.append(
                    Ihlal(
                        kural="yayinci_uyumsuz",
                        paket=sonuc.ad,
                        mesaj=f"{sonuc.ad}: beklenen yayıncı {beklenen}, bulunan {bulunan}",
                        seviye=seviye,
                    )
                )
    rapor.ihlaller = ihlaller
    return ihlaller


def cikis_kodu(ihlaller: list[Ihlal]) -> int:
    return 1 if any(i.seviye is Seviye.HATA for i in ihlaller) else 0


def _durum_metni(durum: Durum) -> str:
    return {
        Durum.KANITLI: "kanıtlı",
        Durum.KANITSIZ: "kanıtsız",
        Durum.KISMI: "kısmi kanıt",
        Durum.BILINMIYOR: "bilinmiyor",
        Durum.ATLANDI: "atlandı",
    }.get(durum, durum.value)
