"""Client for the PyPI Integrity API (PEP 740 provenance objects).

Only the two endpoints this tool needs are implemented:

* ``GET /integrity/<project>/<version>/<filename>/provenance``
* ``GET /pypi/<project>/<version>/json`` (to turn a hash-only pin into filenames)

The client never verifies signatures -- it reports whether PyPI holds an
attestation and which Trusted Publishing identity produced it.  See SECURITY.md.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote

from .model import Dosya, Durum, Kanit, depo_normallestir
from .onbellek import Onbellek, OnbellekKaydi
from .surum import SURUM

KABUL = "application/vnd.pypi.integrity.v1+json"
VARSAYILAN_TABAN = "https://pypi.org"
VARSAYILAN_BUTCE = 500
VARSAYILAN_DENEME = 3
_YENIDEN_DENE = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = (
    f"pypi-provenance-gate/{SURUM} (+https://github.com/YusufBeratZengin/pypi-provenance-gate)"
)


class AgHatasi(Exception):
    """Network-level failure (DNS, TLS, timeout, connection reset)."""


class ButceHatasi(Exception):
    """The configured request budget was exhausted."""


@dataclass(frozen=True)
class Yanit:
    kod: int
    govde: bytes
    basliklar: Mapping[str, str] = field(default_factory=dict)


class Tasima(Protocol):
    """Minimal HTTP GET interface so tests can inject recorded responses."""

    def get(self, url: str, kabul: str | None = None) -> Yanit: ...


class UrllibTasima:
    """stdlib ``urllib`` transport with a timeout and an identifying UA."""

    def __init__(self, zaman_asimi: float = 15.0, user_agent: str = _USER_AGENT) -> None:
        self.zaman_asimi = zaman_asimi
        self.user_agent = user_agent

    def get(self, url: str, kabul: str | None = None) -> Yanit:
        basliklar = {"User-Agent": self.user_agent}
        if kabul:
            basliklar["Accept"] = kabul
        istek = urllib.request.Request(url, headers=basliklar, method="GET")
        try:
            with urllib.request.urlopen(istek, timeout=self.zaman_asimi) as yanit:
                return Yanit(
                    kod=int(yanit.status), govde=yanit.read(), basliklar=dict(yanit.headers)
                )
        except urllib.error.HTTPError as exc:
            # HTTPError *is* a response: 404/403/406 carry meaning for us.
            try:
                govde = exc.read()
            except OSError:  # pragma: no cover - bozuk bağlantı
                govde = b""
            return Yanit(kod=int(exc.code), govde=govde, basliklar=dict(exc.headers or {}))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AgHatasi(f"{url}: {exc}") from exc


def _kanit_ayristir(govde: bytes, dosya: str | None) -> Kanit:
    try:
        veri = json.loads(govde.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Kanit(dosya=dosya, durum=Durum.BILINMIYOR, hata=f"geçersiz JSON yanıtı: {exc}")
    if not isinstance(veri, dict):
        return Kanit(dosya=dosya, durum=Durum.BILINMIYOR, hata="beklenen JSON nesnesi değil")
    paketler = veri.get("attestation_bundles")
    if not isinstance(paketler, list):
        return Kanit(dosya=dosya, durum=Durum.BILINMIYOR, hata="yanıtta 'attestation_bundles' yok")
    if not paketler:
        return Kanit(dosya=dosya, durum=Durum.KANITSIZ, hata="provenance nesnesi boş")

    depolar: list[str] = []
    tur: str | None = None
    is_akisi: str | None = None
    ortam: str | None = None
    sayi = 0
    for paket in paketler:
        if not isinstance(paket, dict):
            continue
        yayinci = paket.get("publisher")
        if isinstance(yayinci, dict):
            kind = yayinci.get("kind")
            kind_metin = kind if isinstance(kind, str) else None
            tur = tur or kind_metin
            ham_depo = yayinci.get("repository")
            if not ham_depo:
                sahip = yayinci.get("repository_owner")
                adi = yayinci.get("repository_name")
                if isinstance(sahip, str) and isinstance(adi, str):
                    ham_depo = f"{sahip}/{adi}"
            depo = depo_normallestir(
                ham_depo if isinstance(ham_depo, str) else None, kind_metin or tur
            )
            if depo and depo not in depolar:
                depolar.append(depo)
            akis = yayinci.get("workflow") or yayinci.get("workflow_filename")
            if is_akisi is None and isinstance(akis, str):
                is_akisi = akis
            env = yayinci.get("environment")
            if ortam is None and isinstance(env, str) and env:
                ortam = env
        atflar = paket.get("attestations")
        if isinstance(atflar, list):
            sayi += len(atflar)

    return Kanit(
        dosya=dosya,
        durum=Durum.KANITLI,
        depo=depolar[0] if depolar else None,
        depolar=tuple(depolar),
        yayinci_turu=tur,
        is_akisi=is_akisi,
        ortam=ortam,
        kanit_sayisi=sayi,
    )


class IntegrityIstemcisi:
    """Talks to PyPI, with caching, retries, a rate limit and a request budget."""

    def __init__(
        self,
        tasima: Tasima | None = None,
        taban: str = VARSAYILAN_TABAN,
        onbellek: Onbellek | None = None,
        butce: int | None = VARSAYILAN_BUTCE,
        gecikme: float = 0.0,
        deneme: int = VARSAYILAN_DENEME,
        cevrimdisi: bool = False,
        zaman_asimi: float = 15.0,
        uyku: Any = None,
        simdi: Any = None,
    ) -> None:
        self.tasima = tasima or UrllibTasima(zaman_asimi=zaman_asimi)
        self.taban = taban.rstrip("/")
        self.onbellek = onbellek
        self.butce = butce
        self.gecikme = max(0.0, gecikme)
        self.deneme = max(1, deneme)
        self.cevrimdisi = cevrimdisi
        self.istek_sayisi = 0
        self._uyku = uyku or time.sleep
        self._simdi = simdi or time.time
        self._son_istek: float | None = None

    # ---- HTTP ---------------------------------------------------------
    def _istek(self, url: str, kabul: str | None = None) -> Yanit | None:
        """Return the response, or ``None`` when offline with a cache miss."""
        if self.onbellek is not None:
            kayit: OnbellekKaydi | None = self.onbellek.al(url)
            if kayit is not None:
                return Yanit(kod=kayit.kod, govde=kayit.govde)
        if self.cevrimdisi:
            return None
        if self.butce is not None and self.istek_sayisi >= self.butce:
            raise ButceHatasi(f"istek bütçesi aşıldı ({self.butce})")

        son_hata: str | None = None
        for deneme in range(1, self.deneme + 1):
            if self.gecikme:
                simdi = self._simdi()
                if self._son_istek is not None:
                    kalan = self.gecikme - (simdi - self._son_istek)
                    if kalan > 0:
                        self._uyku(kalan)
                self._son_istek = self._simdi()
            self.istek_sayisi += 1
            try:
                yanit = self.tasima.get(url, kabul)
            except AgHatasi as exc:
                son_hata = str(exc)
                if deneme < self.deneme:
                    self._uyku(min(2.0 ** (deneme - 1), 8.0))
                    continue
                raise AgHatasi(son_hata) from exc
            if yanit.kod in _YENIDEN_DENE and deneme < self.deneme:
                bekleme = _retry_after(yanit.basliklar)
                self._uyku(bekleme if bekleme is not None else min(2.0 ** (deneme - 1), 8.0))
                continue
            if self.onbellek is not None and yanit.kod in (200, 404):
                self.onbellek.koy(url, yanit.kod, yanit.govde)
            return yanit
        # Buraya yalnızca döngü tuhaf biçimde biterse düşeriz.
        raise AgHatasi(son_hata or f"{url}: bilinmeyen ağ hatası")  # pragma: no cover

    # ---- Endpoints ----------------------------------------------------
    def dosyalar(self, ad: str, surum: str) -> tuple[list[Dosya], str | None]:
        """Release files for a version, used when the lockfile only has hashes."""
        url = f"{self.taban}/pypi/{quote(ad, safe='')}/{quote(surum, safe='')}/json"
        try:
            yanit = self._istek(url)
        except (AgHatasi, ButceHatasi) as exc:
            return [], f"PyPI JSON API: {exc}"
        if yanit is None:
            return [], "çevrimdışı: sürüm dosyaları önbellekte yok"
        if yanit.kod == 404:
            return [], f"{ad} {surum} PyPI'da bulunamadı"
        if yanit.kod != 200:
            return [], f"PyPI JSON API HTTP {yanit.kod}"
        try:
            veri = json.loads(yanit.govde.decode("utf-8"))
            girdiler = veri["urls"]
        except (ValueError, KeyError, TypeError) as exc:
            return [], f"PyPI JSON API yanıtı okunamadı: {exc}"
        if not isinstance(girdiler, list):
            return [], "PyPI JSON API yanıtı okunamadı: 'urls' listesi değil"
        dosyalar: list[Dosya] = []
        for girdi in girdiler:
            if not isinstance(girdi, dict):
                continue
            dosya_adi = girdi.get("filename")
            if not isinstance(dosya_adi, str) or not dosya_adi:
                continue
            digest = girdi.get("digests")
            sha = digest.get("sha256") if isinstance(digest, dict) else None
            dosyalar.append(
                Dosya(
                    ad=dosya_adi,
                    sha256=sha.lower() if isinstance(sha, str) else None,
                    url=girdi.get("url") if isinstance(girdi.get("url"), str) else None,
                )
            )
        if not dosyalar:
            return [], f"{ad} {surum}: dosya listesi boş"
        return dosyalar, None

    def kanit(self, ad: str, surum: str, dosya: str) -> Kanit:
        """Provenance for one release file."""
        url = (
            f"{self.taban}/integrity/{quote(ad, safe='')}/{quote(surum, safe='')}/"
            f"{quote(dosya, safe='')}/provenance"
        )
        try:
            yanit = self._istek(url, KABUL)
        except ButceHatasi as exc:
            return Kanit(dosya=dosya, durum=Durum.BILINMIYOR, hata=str(exc))
        except AgHatasi as exc:
            return Kanit(dosya=dosya, durum=Durum.BILINMIYOR, hata=f"ağ hatası: {exc}")
        if yanit is None:
            return Kanit(dosya=dosya, durum=Durum.BILINMIYOR, hata="çevrimdışı: önbellekte yok")
        if yanit.kod == 200:
            return _kanit_ayristir(yanit.govde, dosya)
        if yanit.kod == 404:
            return Kanit(dosya=dosya, durum=Durum.KANITSIZ, hata="provenance yok (HTTP 404)")
        if yanit.kod == 403:
            return Kanit(
                dosya=dosya,
                durum=Durum.BILINMIYOR,
                hata="PyPI Integrity API geçici olarak kapalı (HTTP 403)",
            )
        if yanit.kod == 406:
            return Kanit(
                dosya=dosya,
                durum=Durum.BILINMIYOR,
                hata="API sürümü kabul edilmedi (HTTP 406) — araç güncel olmayabilir",
            )
        return Kanit(dosya=dosya, durum=Durum.BILINMIYOR, hata=f"HTTP {yanit.kod}")


def _retry_after(basliklar: Mapping[str, str]) -> float | None:
    for anahtar, deger in basliklar.items():
        if anahtar.lower() == "retry-after":
            try:
                return min(max(float(deger), 0.0), 30.0)
            except (TypeError, ValueError):
                return None
    return None
