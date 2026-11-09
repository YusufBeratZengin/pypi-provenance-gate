"""Data model shared by the parsers, the API client, the policy layer and the report."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

PYPI_HOSTS = frozenset({"pypi.org", "pypi.python.org", "files.pythonhosted.org"})


class Durum(StrEnum):
    """Per-file or per-package attestation state."""

    KANITLI = "attested"
    KANITSIZ = "unattested"
    KISMI = "partial"
    BILINMIYOR = "unknown"
    ATLANDI = "skipped"


class Gecis(StrEnum):
    """Change between the previous lockfile state and the current one."""

    YOK = "none"
    DEGISMEDI = "unchanged"
    GERILEDI = "regression"
    YAYINCI_DEGISTI = "publisher_changed"
    IYILESME = "improved"


class Seviye(StrEnum):
    HATA = "error"
    UYARI = "warning"
    YOKSAY = "ignore"


@dataclass(frozen=True)
class Dosya:
    """A release file (wheel or sdist). ``ad`` is the filename on the index."""

    ad: str | None
    sha256: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class Paket:
    ad: str
    surum: str
    dosyalar: tuple[Dosya, ...] = ()
    kaynak: str = "https://pypi.org/simple"
    kilit_dosyasi: str = ""
    notlar: tuple[str, ...] = ()

    @property
    def pypi_mi(self) -> bool:
        return kaynak_pypi_mi(self.kaynak)


@dataclass(frozen=True)
class Kanit:
    """The result of one Integrity API lookup for one file."""

    dosya: str | None
    durum: Durum
    depo: str | None = None
    depolar: tuple[str, ...] = ()
    yayinci_turu: str | None = None
    is_akisi: str | None = None
    ortam: str | None = None
    kanit_sayisi: int = 0
    hata: str | None = None


@dataclass(frozen=True)
class OncekiDurum:
    surum: str
    durum: Durum
    depolar: tuple[str, ...] = ()


@dataclass
class PaketSonuc:
    paket: Paket
    durum: Durum
    kanitlar: list[Kanit] = field(default_factory=list)
    depolar: list[str] = field(default_factory=list)
    notlar: list[str] = field(default_factory=list)
    onceki: OncekiDurum | None = None
    gecis: Gecis = Gecis.YOK
    ihlaller: list[str] = field(default_factory=list)

    @property
    def ad(self) -> str:
        return self.paket.ad

    @property
    def surum(self) -> str:
        return self.paket.surum


@dataclass(frozen=True)
class Ihlal:
    kural: str
    paket: str
    mesaj: str
    seviye: Seviye


@dataclass
class Rapor:
    kilit_dosyasi: str
    paketler: list[PaketSonuc] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)
    onceki_rev: str | None = None
    ihlaller: list[Ihlal] = field(default_factory=list)
    istek_sayisi: int = 0

    @property
    def sayaclar(self) -> dict[str, int]:
        sayac = {d.value: 0 for d in Durum}
        for sonuc in self.paketler:
            sayac[sonuc.durum.value] += 1
        return sayac

    @property
    def gecis_sayaclari(self) -> dict[str, int]:
        sayac = {g.value: 0 for g in Gecis}
        for sonuc in self.paketler:
            sayac[sonuc.gecis.value] += 1
        return sayac


def kaynak_pypi_mi(kaynak: str) -> bool:
    """True when the index URL points at PyPI itself."""
    from urllib.parse import urlparse

    if not kaynak:
        return True
    if "://" not in kaynak:
        kaynak = "https://" + kaynak
    try:
        host = (urlparse(kaynak).hostname or "").lower()
    except ValueError:  # pragma: no cover - urlparse rarely raises
        return False
    return host in PYPI_HOSTS


def ad_normallestir(ad: str) -> str:
    """PEP 503 normalisation: ``Foo_Bar.baz`` -> ``foo-bar-baz``."""
    return ad.strip().lower().replace("_", "-").replace(".", "-")


def depo_normallestir(deger: str | None, tur: str | None = None) -> str | None:
    """Normalise a publisher repository to ``host/owner/repo``.

    PyPI returns ``pypa/sampleproject`` for GitHub Trusted Publishing while a
    policy file is easier to read as ``github.com/pypa/sampleproject``. Both
    spellings normalise to the same value here.
    """
    if not deger:
        return None
    d = deger.strip().lower()
    for onek in ("https://", "http://"):
        if d.startswith(onek):
            d = d[len(onek) :]
    d = d.rstrip("/")
    if d.endswith(".git"):
        d = d[:-4]
    if not d:
        return None
    ilk = d.split("/")[0]
    if "." not in ilk:
        ana = (tur or "github").strip().lower()
        host = {"github": "github.com", "gitlab": "gitlab.com"}.get(ana, ana)
        if not host:
            return d
        d = f"{host}/{d}"
    return d
