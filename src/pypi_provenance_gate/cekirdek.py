"""Classification: turn lockfile packages into one :class:`Rapor`.

``kontrol(paketler, istemci)`` is the library entry point.  It performs one
Integrity API lookup per release file, never more, and degrades to
``unknown`` (never to a silent pass) when the network or the API misbehaves.
"""

from __future__ import annotations

from collections.abc import Iterable

from .integrity import IntegrityIstemcisi
from .model import Dosya, Durum, Kanit, Paket, PaketSonuc, Rapor


def kontrol(
    paketler: Iterable[Paket],
    istemci: IntegrityIstemcisi,
    kilit_dosyasi: str = "",
    dosya_limiti: int = 10,
) -> Rapor:
    """Check every package and return a report.

    ``istemci`` must provide ``kanit(name, version, filename)`` and
    ``dosyalar(name, version)``; see :class:`IntegrityIstemcisi`.
    """
    rapor = Rapor(kilit_dosyasi=kilit_dosyasi)
    for paket in paketler:
        rapor.paketler.append(_paket_kontrol(paket, istemci, dosya_limiti))
    rapor.istek_sayisi = getattr(istemci, "istek_sayisi", 0)
    return rapor


def _paket_kontrol(paket: Paket, istemci: IntegrityIstemcisi, dosya_limiti: int) -> PaketSonuc:
    notlar = list(paket.notlar)
    if not paket.pypi_mi:
        notlar.append(f"PyPI dışı indeks ({paket.kaynak}); kaynak kanıtı sorgulanamaz")
        return PaketSonuc(paket=paket, durum=Durum.ATLANDI, notlar=notlar)

    dosyalar, hata, kesildi = _dosyalari_coz(paket, istemci, dosya_limiti, notlar)
    if hata is not None:
        notlar.append(hata)
    if not dosyalar:
        return PaketSonuc(paket=paket, durum=Durum.BILINMIYOR, notlar=notlar)

    kanitlar: list[Kanit] = []
    for dosya in dosyalar:
        if dosya.ad is None:  # pragma: no cover - _dosyalari_coz bunu eler
            continue
        kanitlar.append(istemci.kanit(paket.ad, paket.surum, dosya.ad))

    durum = _sinifla(kanitlar, kesildi)
    depolar: list[str] = []
    for k in kanitlar:
        for d in k.depolar or ((k.depo,) if k.depo else ()):
            if d not in depolar:
                depolar.append(d)

    hatalar = [k.hata for k in kanitlar if k.durum is Durum.BILINMIYOR and k.hata]
    if durum is Durum.BILINMIYOR and hatalar:
        notlar.append(hatalar[0])
    if durum is Durum.KISMI:
        eksik = [k.dosya or "?" for k in kanitlar if k.durum is not Durum.KANITLI]
        if eksik:
            liste = ", ".join(eksik[:3])
            son = "…" if len(eksik) > 3 else ""
            notlar.append(f"kanıtsız dosya(lar): {liste}{son}")
    if len(depolar) > 1:
        notlar.append(f"birden fazla yayıncı deposu: {', '.join(depolar)}")

    return PaketSonuc(paket=paket, durum=durum, kanitlar=kanitlar, depolar=depolar, notlar=notlar)


def _dosyalari_coz(
    paket: Paket,
    istemci: IntegrityIstemcisi,
    dosya_limiti: int,
    notlar: list[str],
) -> tuple[list[Dosya], str | None, bool]:
    """Resolve filenames, match hashes, apply the per-package file cap."""
    dosyalar = list(paket.dosyalar)
    hata: str | None = None
    adli = [d for d in dosyalar if d.ad]
    adsiz = [d for d in dosyalar if not d.ad]

    if adsiz:
        cozulen, hata = istemci.dosyalar(paket.ad, paket.surum)
        if cozulen:
            cozulen_adlar = {d.ad for d in cozulen}
            secilen: list[Dosya] = list(adli)
            for d in adsiz:
                if d.sha256 is None:
                    continue
                eslesen = next((c for c in cozulen if c.sha256 == d.sha256), None)
                if eslesen is None:
                    hata = (
                        f"kilit hash'i PyPI'daki hiçbir {paket.ad} {paket.surum} "
                        "dosyasıyla eşleşmedi"
                    )
                    continue
                if eslesen.ad not in cozulen_adlar:  # pragma: no cover - savunma
                    continue
                secilen.append(eslesen)
            # Kilitte hash yoksa (adsız ve hashsiz) tüm dosyalar aday olur.
            if not any(d.sha256 for d in adsiz):
                secilen.extend(c for c in cozulen if c.ad not in {d.ad for d in secilen})
            dosyalar = secilen
        elif not adli:
            return [], hata or "dosya adları çözülemedi", False

    benzersiz: list[Dosya] = []
    gorulen: set[str] = set()
    for d in dosyalar:
        if d.ad is None:
            continue
        if d.ad in gorulen:
            continue
        gorulen.add(d.ad)
        benzersiz.append(d)

    kesildi = False
    if dosya_limiti > 0 and len(benzersiz) > dosya_limiti:
        atlanan = len(benzersiz) - dosya_limiti
        notlar.append(
            f"{atlanan} dosya kontrol edilmedi (--dosya-limiti {dosya_limiti}); "
            "sonuç bu dosyalar için eksik"
        )
        benzersiz = benzersiz[:dosya_limiti]
        kesildi = True
    return benzersiz, hata, kesildi


def _sinifla(kanitlar: list[Kanit], kesildi: bool) -> Durum:
    if not kanitlar:
        return Durum.BILINMIYOR
    durumlar = [k.durum for k in kanitlar]
    if all(d is Durum.KANITLI for d in durumlar):
        return Durum.KISMI if kesildi else Durum.KANITLI
    if any(d is Durum.KANITLI for d in durumlar):
        return Durum.KISMI
    if all(d is Durum.KANITSIZ for d in durumlar):
        return Durum.KANITSIZ
    # Hiç kanıtlı yok ama en az bir dosya bilinmiyor: sessizce "kanıtsız" deme.
    return Durum.BILINMIYOR
