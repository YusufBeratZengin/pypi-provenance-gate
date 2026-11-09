"""Integrity API client: success, error paths, retries, budget, cache, offline."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from pypi_provenance_gate.integrity import (
    KABUL,
    AgHatasi,
    ButceHatasi,
    IntegrityIstemcisi,
    UrllibTasima,
    Yanit,
    _kanit_ayristir,
    _retry_after,
)
from pypi_provenance_gate.model import Durum
from pypi_provenance_gate.onbellek import Onbellek

from conftest import (
    A,
    PLAIN_WHEEL,
    SDIST,
    WHEEL,
    SahteTasima,
    json_url,
    kanit_govdesi,
    kanit_url,
    pypi_json_govdesi,
)


def test_kanitli_yanit_ayristirilir() -> None:
    kanit = _kanit_ayristir(kanit_govdesi(), SDIST)
    assert kanit.durum is Durum.KANITLI
    assert kanit.depo == "github.com/example-org/example-project"
    assert kanit.depolar == ("github.com/example-org/example-project",)
    assert kanit.yayinci_turu == "GitHub"
    assert kanit.is_akisi == "release.yml"
    assert kanit.kanit_sayisi == 1
    assert kanit.hata is None


def test_kanit_coklu_bundle_ve_sayim() -> None:
    govde = json.dumps(
        {
            "attestation_bundles": [
                {
                    "attestations": [{"version": 1}, {"version": 1}],
                    "publisher": {"kind": "GitLab", "repository": "example/repo"},
                },
                {
                    "attestations": [{"version": 1}],
                    "publisher": {
                        "kind": "GitHub",
                        "repository_owner": "example-org",
                        "repository_name": "example-project",
                        "environment": "release",
                    },
                },
            ],
            "version": 1,
        }
    ).encode()
    kanit = _kanit_ayristir(govde, WHEEL)
    assert kanit.kanit_sayisi == 3
    assert kanit.depolar == ("gitlab.com/example/repo", "github.com/example-org/example-project")
    assert kanit.depo == "gitlab.com/example/repo"
    assert kanit.ortam == "release"


def test_kanit_bos_bundle() -> None:
    kanit = _kanit_ayristir(b'{"attestation_bundles": []}', WHEEL)
    assert kanit.durum is Durum.KANITSIZ
    assert "boş" in (kanit.hata or "")


@pytest.mark.parametrize(
    ("govde", "parca"),
    [
        (b"not json", "geçersiz JSON"),
        (b"[]", "JSON nesnesi"),
        (b'{"version": 1}', "attestation_bundles"),
    ],
)
def test_kanit_bozuk_yanit(govde: bytes, parca: str) -> None:
    kanit = _kanit_ayristir(govde, WHEEL)
    assert kanit.durum is Durum.BILINMIYOR
    assert parca in (kanit.hata or "")


def test_kanit_200(tasima: SahteTasima) -> None:
    tasima.harita[kanit_url("example-attested", "1.0.0", SDIST)] = Yanit(200, kanit_govdesi())
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None)
    kanit = istemci.kanit("example-attested", "1.0.0", SDIST)
    assert kanit.durum is Durum.KANITLI
    assert tasima.cagrilar[0][1] == KABUL
    # URL kaçışı ve uç nokta biçimi
    assert tasima.cagrilar[0][0] == (
        "https://pypi.org/integrity/example-attested/1.0.0/" + SDIST + "/provenance"
    )


def test_kanit_404_kanitsiz(tasima: SahteTasima) -> None:
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None)
    kanit = istemci.kanit("example-plain", "2.1.0", PLAIN_WHEEL)
    assert kanit.durum is Durum.KANITSIZ
    assert "404" in (kanit.hata or "")


@pytest.mark.parametrize(
    ("kod", "parca"),
    [(403, "403"), (406, "406"), (500, "500"), (418, "418")],
)
def test_kanit_http_hatalari_bilinmiyor(tasima: SahteTasima, kod: int, parca: str) -> None:
    tasima.harita[kanit_url("x", "1", "x-1.whl")] = Yanit(kod, b"")
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, deneme=1)
    kanit = istemci.kanit("x", "1", "x-1.whl")
    assert kanit.durum is Durum.BILINMIYOR
    assert parca in (kanit.hata or "")


def test_ag_hatasi_bilinmiyor_ve_yeniden_denenir() -> None:
    uyku: list[float] = []
    tasima = SahteTasima({kanit_url("x", "1", "x-1.whl"): AgHatasi("boom")})
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, deneme=2, uyku=uyku.append)
    kanit = istemci.kanit("x", "1", "x-1.whl")
    assert kanit.durum is Durum.BILINMIYOR
    assert "ağ hatası" in (kanit.hata or "")
    assert istemci.istek_sayisi == 2
    assert uyku  # geri çekilme uygulandı


def test_503_sonra_basari() -> None:
    yanitlar = [Yanit(503, b""), Yanit(200, kanit_govdesi())]

    class SiraylaTasima(SahteTasima):
        def get(self, url: str, kabul: str | None = None) -> Yanit:
            return yanitlar.pop(0)

    uyku: list[float] = []
    istemci = IntegrityIstemcisi(tasima=SiraylaTasima(), onbellek=None, uyku=uyku.append)
    kanit = istemci.kanit("x", "1", SDIST)
    assert kanit.durum is Durum.KANITLI
    assert istemci.istek_sayisi == 2
    assert uyku == [1.0]


def test_retry_after_basligi() -> None:
    yanitlar = [Yanit(429, b"", {"Retry-After": "7"}), Yanit(404, b"")]

    class SiraylaTasima(SahteTasima):
        def get(self, url: str, kabul: str | None = None) -> Yanit:
            return yanitlar.pop(0)

    uyku: list[float] = []
    istemci = IntegrityIstemcisi(tasima=SiraylaTasima(), onbellek=None, uyku=uyku.append)
    istemci.kanit("x", "1", "x-1.whl")
    assert uyku == [7.0]


@pytest.mark.parametrize(
    ("basliklar", "beklenen"),
    [({}, None), ({"retry-after": "3"}, 3.0), ({"Retry-After": "yok"}, None)],
)
def test_retry_after(basliklar: dict[str, str], beklenen: float | None) -> None:
    assert _retry_after(basliklar) == beklenen


def test_butce_asilir(tasima: SahteTasima) -> None:
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, butce=1)
    assert istemci.kanit("a", "1", "a-1.whl").durum is Durum.KANITSIZ
    kanit = istemci.kanit("b", "1", "b-1.whl")
    assert kanit.durum is Durum.BILINMIYOR
    assert "bütçe" in (kanit.hata or "")
    with pytest.raises(ButceHatasi):
        istemci._istek("https://pypi.org/integrity/c/1/c-1.whl/provenance")


def test_gecikme_uygulanir() -> None:
    saat = {"t": 0.0}
    uyku: list[float] = []

    def simdi() -> float:
        return saat["t"]

    def uyu(s: float) -> None:
        uyku.append(s)
        saat["t"] += s

    tasima = SahteTasima()
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, gecikme=1.0, uyku=uyu, simdi=simdi)
    istemci.kanit("a", "1", "a-1.whl")
    istemci.kanit("b", "1", "b-1.whl")
    assert uyku and uyku[0] == pytest.approx(1.0)


def test_dosyalar_200() -> None:
    tasima = SahteTasima(
        {
            json_url("example-attested", "1.0.0"): Yanit(
                200, pypi_json_govdesi("example-attested", "1.0.0", [(SDIST, A), (WHEEL, "B" * 64)])
            )
        }
    )
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None)
    dosyalar, hata = istemci.dosyalar("example-attested", "1.0.0")
    assert hata is None
    assert [d.ad for d in dosyalar] == [SDIST, WHEEL]
    assert dosyalar[0].sha256 == A
    assert dosyalar[0].url is not None


def test_dosyalar_404() -> None:
    istemci = IntegrityIstemcisi(tasima=SahteTasima(), onbellek=None)
    dosyalar, hata = istemci.dosyalar("yok", "9.9")
    assert dosyalar == []
    assert "bulunamadı" in (hata or "")


@pytest.mark.parametrize(
    ("govde", "parca"),
    [(b"not json", "okunamadı"), (b'{"urls": 3}', "okunamadı"), (b'{"urls": []}', "boş")],
)
def test_dosyalar_bozuk(govde: bytes, parca: str) -> None:
    tasima = SahteTasima({json_url("x", "1"): Yanit(200, govde)})
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None)
    _, hata = istemci.dosyalar("x", "1")
    assert parca in (hata or "")


def test_dosyalar_500() -> None:
    tasima = SahteTasima({json_url("x", "1"): Yanit(500, b"")})
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, deneme=1)
    _, hata = istemci.dosyalar("x", "1")
    assert "HTTP 500" in (hata or "")


def test_dosyalar_ag_hatasi() -> None:
    tasima = SahteTasima({json_url("x", "1"): AgHatasi("offline")})
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, deneme=1)
    _, hata = istemci.dosyalar("x", "1")
    assert "JSON API" in (hata or "")


def test_onbellek_200_ve_404_saklanir(tasima: SahteTasima, tmp_path: Path) -> None:
    tasima.harita[kanit_url("x", "1", SDIST)] = Yanit(200, kanit_govdesi())
    onbellek = Onbellek(tmp_path)
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=onbellek)
    assert istemci.kanit("x", "1", SDIST).durum is Durum.KANITLI
    istemci.kanit("y", "1", "y-1.whl")
    onbellek.kaydet()

    yeni = Onbellek(tmp_path)
    yeni_istemci = IntegrityIstemcisi(tasima=SahteTasima(), onbellek=yeni)
    assert yeni_istemci.kanit("x", "1", SDIST).durum is Durum.KANITLI
    assert yeni_istemci.kanit("y", "1", "y-1.whl").durum is Durum.KANITSIZ
    assert yeni_istemci.istek_sayisi == 0


def test_cevrimdisi_onbellek_yok(tasima: SahteTasima) -> None:
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, cevrimdisi=True)
    kanit = istemci.kanit("x", "1", "x-1.whl")
    assert kanit.durum is Durum.BILINMIYOR
    assert "çevrimdışı" in (kanit.hata or "")
    assert tasima.cagrilar == []


def test_cevrimdisi_dosyalar_onbellek_yok(tasima: SahteTasima) -> None:
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, cevrimdisi=True)
    dosyalar, hata = istemci.dosyalar("x", "1")
    assert dosyalar == []
    assert "çevrimdışı" in (hata or "")


def test_url_kacisi(tasima: SahteTasima) -> None:
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None)
    istemci.kanit("Foo Bar", "1.0+build", "foo bar-1.0.whl")
    assert "%20" in tasima.cagrilar[0][0]
    assert "+" not in tasima.cagrilar[0][0]


# ------------------------------------------------------------- UrllibTasima


class _SahteYanit(io.BytesIO):
    status = 200
    headers = {"Content-Type": "application/json"}

    def __enter__(self) -> _SahteYanit:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def test_urllib_tasima_basari(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(istek: Any, timeout: float | None = None) -> _SahteYanit:
        assert istek.get_header("Accept") == KABUL
        assert "pypi-provenance-gate" in istek.get_header("User-agent")
        return _SahteYanit(b"govde")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    yanit = UrllibTasima().get("https://pypi.org/x", KABUL)
    assert yanit.kod == 200
    assert yanit.govde == b"govde"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_urllib_tasima_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(istek: Any, timeout: float | None = None) -> None:
        raise urllib.error.HTTPError(
            "https://pypi.org/x", 404, "Not Found", {"X": "1"}, io.BytesIO(b"yok")
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    yanit = UrllibTasima().get("https://pypi.org/x")
    assert yanit.kod == 404
    assert yanit.govde == b"yok"


def test_urllib_tasima_ag_hatasi(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(istek: Any, timeout: float | None = None) -> None:
        raise urllib.error.URLError("dns")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(AgHatasi, match="dns"):
        UrllibTasima().get("https://pypi.org/x")
