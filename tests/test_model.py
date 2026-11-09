"""Model helpers: normalisation and index detection."""

from __future__ import annotations

import pytest

from pypi_provenance_gate.model import (
    Dosya,
    Durum,
    Paket,
    Rapor,
    PaketSonuc,
    ad_normallestir,
    depo_normallestir,
    kaynak_pypi_mi,
)


@pytest.mark.parametrize(
    ("girdi", "beklenen"),
    [
        ("Foo_Bar.baz", "foo-bar-baz"),
        ("  Requests ", "requests"),
        ("a__b..c", "a--b--c"),
    ],
)
def test_ad_normallestir(girdi: str, beklenen: str) -> None:
    assert ad_normallestir(girdi) == beklenen


@pytest.mark.parametrize(
    ("deger", "tur", "beklenen"),
    [
        ("pypa/sampleproject", "GitHub", "github.com/pypa/sampleproject"),
        ("https://github.com/PSF/Requests.git", "GitHub", "github.com/psf/requests"),
        ("gitlab.com/example/repo/", "GitLab", "gitlab.com/example/repo"),
        ("example/repo", "GitLab", "gitlab.com/example/repo"),
        ("example/repo", None, "github.com/example/repo"),
        ("", "GitHub", None),
        (None, "GitHub", None),
        ("https://", "GitHub", None),
    ],
)
def test_depo_normallestir(deger: str | None, tur: str | None, beklenen: str | None) -> None:
    assert depo_normallestir(deger, tur) == beklenen


@pytest.mark.parametrize(
    ("kaynak", "beklenen"),
    [
        ("https://pypi.org/simple", True),
        ("pypi.org/simple", True),
        ("https://files.pythonhosted.org/packages", True),
        ("https://packages.example.invalid/simple", False),
        ("git+https://example.invalid/x.git", False),
        ("", True),
    ],
)
def test_kaynak_pypi_mi(kaynak: str, beklenen: bool) -> None:
    assert kaynak_pypi_mi(kaynak) is beklenen


def test_paket_pypi_mi() -> None:
    assert Paket("x", "1", dosyalar=(Dosya("x-1.whl"),)).pypi_mi
    assert not Paket("x", "1", kaynak="https://example.invalid/simple").pypi_mi


def test_rapor_sayaclari() -> None:
    p = Paket("x", "1")
    rapor = Rapor(
        kilit_dosyasi="uv.lock",
        paketler=[
            PaketSonuc(paket=p, durum=Durum.KANITLI),
            PaketSonuc(paket=p, durum=Durum.KANITSIZ),
            PaketSonuc(paket=p, durum=Durum.KANITSIZ),
        ],
    )
    assert rapor.sayaclar[Durum.KANITLI.value] == 1
    assert rapor.sayaclar[Durum.KANITSIZ.value] == 2
    assert rapor.sayaclar[Durum.BILINMIYOR.value] == 0
    assert set(rapor.gecis_sayaclari) == {"none", "unchanged", "regression", "publisher_changed", "improved"}
