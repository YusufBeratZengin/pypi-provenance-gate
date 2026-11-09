"""Human-readable and JSON rendering of a report."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from .model import Durum, Gecis, Rapor
from .surum import SURUM

SEMAVER = "1.0"

_DURUM_ETIKET = {
    Durum.KANITLI: "attested",
    Durum.KANITSIZ: "unattested",
    Durum.KISMI: "partial",
    Durum.BILINMIYOR: "unknown",
    Durum.ATLANDI: "skipped",
}

_GECIS_ETIKET = {
    Gecis.YOK: "-",
    Gecis.DEGISMEDI: "unchanged",
    Gecis.GERILEDI: "regression",
    Gecis.YAYINCI_DEGISTI: "publisher changed",
    Gecis.IYILESME: "improved",
}

_RENK = {
    Durum.KANITLI: "32",
    Durum.KANITSIZ: "33",
    Durum.KISMI: "33",
    Durum.BILINMIYOR: "35",
    Durum.ATLANDI: "2",
    Gecis.GERILEDI: "31",
    Gecis.YAYINCI_DEGISTI: "31",
    Gecis.IYILESME: "32",
}

_KISA = {
    Durum.KANITLI: "attested",
    Durum.KANITSIZ: "unattested",
    Durum.KISMI: "partial",
    Durum.BILINMIYOR: "unknown",
    Durum.ATLANDI: "skipped",
}


def _renk_etkin(renk: bool | None) -> bool:
    if renk is not None:
        return renk
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _boya(metin: str, kod: str | None, etkin: bool) -> str:
    if not etkin or not kod:
        return metin
    return f"\x1b[{kod}m{metin}\x1b[0m"


def _kirp(metin: str, genislik: int) -> str:
    return metin if len(metin) <= genislik else metin[: genislik - 1] + "…"


def satirlar(rapor: Rapor) -> list[tuple[str, str, str, str, str]]:
    """(package, version, status, change, publisher) rows for the table."""
    gorunum: list[tuple[str, str, str, str, str]] = []
    for s in rapor.paketler:
        yayinci = ", ".join(s.depolar) if s.depolar else "-"
        if len(s.depolar) > 1:
            yayinci = f"{s.depolar[0]} (+{len(s.depolar) - 1})"
        gorunum.append(
            (
                _kirp(s.ad, 29),
                _kirp(s.surum, 13),
                _DURUM_ETIKET[s.durum],
                _GECIS_ETIKET[s.gecis],
                _kirp(yayinci, 36),
            )
        )
    return gorunum


def metin(rapor: Rapor, renk: bool | None = None) -> str:
    etkin = _renk_etkin(renk)
    cizgi = "-" * 100
    basliklar = ("PACKAGE", "VERSION", "STATUS", "CHANGE", "PUBLISHER")
    genislikler = (29, 13, 10, 17, 36)

    def bicim(degerler: tuple[str, ...]) -> str:
        return "  ".join(d.ljust(g) for d, g in zip(degerler, genislikler, strict=True)).rstrip()

    satir_listesi = [f"Lockfile: {rapor.kilit_dosyasi}"]
    if rapor.onceki_rev:
        satir_listesi.append(f"Compared with: {rapor.onceki_rev}")
    satir_listesi.append("")
    satir_listesi.append(bicim(basliklar))
    satir_listesi.append(cizgi)
    for (ad, surum, durum, gecis, yayinci), sonuc in zip(
        satirlar(rapor), rapor.paketler, strict=True
    ):
        satir_listesi.append(
            "  ".join(
                [
                    ad.ljust(genislikler[0]),
                    surum.ljust(genislikler[1]),
                    _boya(durum.ljust(genislikler[2]), _RENK.get(sonuc.durum), etkin),
                    _boya(gecis.ljust(genislikler[3]), _RENK.get(sonuc.gecis), etkin),
                    yayinci,
                ]
            ).rstrip()
        )
    satir_listesi.append(cizgi)

    sayac = rapor.sayaclar
    toplam = len(rapor.paketler)
    satir_listesi.append(
        f"{toplam} package(s): {sayac[Durum.KANITLI.value]} attested, "
        f"{sayac[Durum.KANITSIZ.value]} unattested, {sayac[Durum.KISMI.value]} partial, "
        f"{sayac[Durum.BILINMIYOR.value]} unknown, {sayac[Durum.ATLANDI.value]} skipped"
    )
    degisim = rapor.gecis_sayaclari
    if any(degisim[g.value] for g in (Gecis.GERILEDI, Gecis.YAYINCI_DEGISTI, Gecis.IYILESME)):
        satir_listesi.append(
            f"Changes: {degisim[Gecis.GERILEDI.value]} regression(s), "
            f"{degisim[Gecis.YAYINCI_DEGISTI.value]} publisher change(s), "
            f"{degisim[Gecis.IYILESME.value]} improvement(s)"
        )
    satir_listesi.append(f"HTTP requests: {rapor.istek_sayisi}")

    notlu = [s for s in rapor.paketler if s.notlar]
    if notlu:
        satir_listesi.append("")
        satir_listesi.append("Notes:")
        for s in notlu:
            for n in s.notlar:
                satir_listesi.append(f"  {s.ad} {s.surum}: {n}")

    if rapor.uyarilar:
        satir_listesi.append("")
        for u in rapor.uyarilar:
            satir_listesi.append(f"warning: {u}")

    if rapor.ihlaller:
        satir_listesi.append("")
        satir_listesi.append("Policy:")
        for i in rapor.ihlaller:
            satir_listesi.append(f"  [{i.seviye.value}] {i.kural}: {i.mesaj}")

    satir_listesi.append("")
    satir_listesi.append(
        "Note: provenance means the file was published by that identity. It does not "
        "prove the package is safe or free of malware."
    )
    return "\n".join(satir_listesi)


def json_verisi(rapor: Rapor, uretim: str) -> dict[str, Any]:
    paketler: list[dict[str, Any]] = []
    for s in rapor.paketler:
        paketler.append(
            {
                "name": s.ad,
                "version": s.surum,
                "status": s.durum.value,
                "publisher_repositories": s.depolar,
                "change": s.gecis.value,
                "previous_version": s.onceki.surum if s.onceki else None,
                "previous_status": s.onceki.durum.value if s.onceki else None,
                "notes": s.notlar,
                "violations": [
                    {"rule": i.kural, "level": i.seviye.value, "message": i.mesaj}
                    for i in rapor.ihlaller
                    if i.paket == s.ad
                ],
                "files": [
                    {
                        "filename": k.dosya,
                        "status": k.durum.value,
                        "publisher": k.depo,
                        "publisher_kind": k.yayinci_turu,
                        "workflow": k.is_akisi,
                        "environment": k.ortam,
                        "attestation_count": k.kanit_sayisi,
                        "error": k.hata,
                    }
                    for k in s.kanitlar
                ],
            }
        )
    return {
        "schema_version": SEMAVER,
        "tool": "pypi-provenance-gate",
        "tool_version": SURUM,
        "generated_at": uretim,
        "lockfile": rapor.kilit_dosyasi,
        "previous": rapor.onceki_rev,
        "summary": {
            "total": len(rapor.paketler),
            "by_status": rapor.sayaclar,
            "by_change": rapor.gecis_sayaclari,
            "http_requests": rapor.istek_sayisi,
            "violations": len(rapor.ihlaller),
            "errors": sum(1 for i in rapor.ihlaller if i.seviye.value == "error"),
        },
        "packages": paketler,
        "violations": [
            {"rule": i.kural, "package": i.paket, "level": i.seviye.value, "message": i.mesaj}
            for i in rapor.ihlaller
        ],
        "warnings": rapor.uyarilar,
    }


def json_metni(rapor: Rapor, uretim: str) -> str:
    return json.dumps(json_verisi(rapor, uretim), ensure_ascii=False, indent=2)
