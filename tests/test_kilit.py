"""Tests for the four lockfile parsers and the format dispatcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from pypi_provenance_gate import kilit
from pypi_provenance_gate.kilit import KilitHatasi

FIKSTUR = Path(__file__).parent / "fiksturler"


def _oku(ad: str) -> str:
    return (FIKSTUR / ad).read_text(encoding="utf-8")


# ---------------------------------------------------------------- uv.lock


def test_uv_ayristirir() -> None:
    kd = kilit.ayristir(_oku("uv.lock"), "uv.lock")
    assert kd.tur == "uv"
    adlar = [p.ad for p in kd.paketler]
    assert adlar == ["example-attested", "example-plain", "example-gitdep"]
    attested = kd.paketler[0]
    assert attested.surum == "1.0.0"
    assert [d.ad for d in attested.dosyalar] == [
        "example_attested-1.0.0-py3-none-any.whl",
        "example_attested-1.0.0.tar.gz",
    ]
    assert attested.dosyalar[0].sha256 == "b" * 64
    assert len(kd.uyarilar) == 1
    assert "editable" in kd.uyarilar[0]
    assert kd.paketler[2].kaynak.startswith("https://example.invalid/example-org")
    assert kd.paketler[1].dosyalar[0].sha256 == "c" * 64


def test_uv_yerel_kaynak_atlanir_ama_git_paketi_kalir() -> None:
    kd = kilit.ayristir(_oku("uv.lock"), "uv.lock")
    assert all(p.ad != "example-internal" for p in kd.paketler)


@pytest.mark.parametrize(
    "metin",
    [
        "version = [",
        "version = 1\n[[package]]\nname = 'x'\n",
        "version = 1\npackage = 'x'\n",
        "version = 1\n[[package]]\nname = 'x'\nversion = '1'\nsource = { registry = 'https://pypi.org/simple' }\nwheels = 3\n",
    ],
)
def test_uv_gecersiz(metin: str) -> None:
    with pytest.raises(KilitHatasi):
        kilit.ayristir(metin, "uv.lock")


def test_uv_bilinmeyen_kaynak_hatasi() -> None:
    metin = (
        "version = 1\n[[package]]\nname = 'x'\nversion = '1'\nsource = { spooky = 'x' }\n"
    )
    with pytest.raises(KilitHatasi, match="bilinmeyen kaynak"):
        kilit.ayristir(metin, "uv.lock")


def test_uv_gecersiz_hash() -> None:
    metin = (
        "version = 1\n[[package]]\nname = 'x'\nversion = '1'\n"
        "source = { registry = 'https://pypi.org/simple' }\n"
        "wheels = [{ url = 'https://files.pythonhosted.org/x.whl', hash = 'sha256:zz' }]\n"
    )
    with pytest.raises(KilitHatasi, match="sha256"):
        kilit.ayristir(metin, "uv.lock")


def test_uv_bos_kilit() -> None:
    with pytest.raises(KilitHatasi, match="hiç paket"):
        kilit.ayristir("version = 1\n", "uv.lock")


# ---------------------------------------------------------- requirements


def test_requirements_ayristirir() -> None:
    kd = kilit.ayristir(_oku("requirements.txt"), "requirements.txt")
    assert kd.tur == "requirements"
    assert [p.ad for p in kd.paketler] == ["example-attested", "example-plain"]
    assert kd.paketler[0].dosyalar[0].sha256 == "a" * 64
    assert kd.paketler[0].dosyalar[0].ad is None
    assert any("tam sürüm" in u for u in kd.uyarilar)


def test_requirements_ekstra_marker_ve_yorum() -> None:
    metin = (
        "# yorum\n"
        "Foo[bar,baz]==1.2.3 ; python_version >= '3.11'  # satır sonu\n"
        "bar===2.0\n"
    )
    kd = kilit.ayristir(metin, "requirements.txt")
    assert [p.ad for p in kd.paketler] == ["Foo", "bar"]
    assert kd.paketler[0].surum == "1.2.3"
    assert any("===" in u for u in kd.uyarilar)


def test_requirements_coklu_hash_ve_bilinmeyen_secenek() -> None:
    metin = (
        "-e .\n"
        "--extra-index-url https://example.invalid/simple\n"
        "foo==1.0 --hash=sha256:" + "a" * 64 + " --hash=sha256:" + "b" * 64 + "\n"
        "bar==2.0 --hash=md5:abcd\n"
    )
    kd = kilit.ayristir(metin, "requirements.txt")
    assert len(kd.paketler[0].dosyalar) == 2
    assert any("sha256 dışı" in u for u in kd.uyarilar)
    assert any("desteklenmiyor" in u for u in kd.uyarilar)


def test_requirements_bos_ve_gecersiz() -> None:
    with pytest.raises(KilitHatasi, match="hiç gereksinim"):
        kilit.ayristir("# sadece yorum\nfoo>=1\n", "requirements.txt")
    with pytest.raises(KilitHatasi, match="sha256"):
        kilit.ayristir("foo==1.0 --hash=sha256:zz\n", "requirements.txt")


def test_requirements_index_url_degisir() -> None:
    kd = kilit.ayristir(
        "--index-url https://packages.example.invalid/simple\nfoo==1.0\n", "requirements.txt"
    )
    assert kd.paketler[0].kaynak == "https://packages.example.invalid/simple"


def test_requirements_satir_devami() -> None:
    metin = "foo==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n"
    kd = kilit.ayristir(metin, "requirements.txt")
    assert kd.paketler[0].dosyalar[0].sha256 == "a" * 64


# ------------------------------------------------------------- poetry.lock


def test_poetry_ayristirir() -> None:
    kd = kilit.ayristir(_oku("poetry.lock"), "poetry.lock")
    assert kd.tur == "poetry"
    assert [p.ad for p in kd.paketler] == ["example-attested", "example-legacy"]
    assert kd.paketler[0].dosyalar[0].ad == "example_attested-1.0.0-py3-none-any.whl"
    assert kd.paketler[1].kaynak == "https://packages.example.invalid/simple"
    assert not kd.paketler[1].pypi_mi


def test_poetry_git_kaynagi_uyari() -> None:
    metin = (
        "[[package]]\nname = 'x'\nversion = '1'\nfiles = []\n"
        "[package.source]\ntype = 'git'\nurl = 'https://example.invalid/x.git'\n"
    )
    kd = kilit.ayristir(metin, "poetry.lock")
    assert kd.paketler[0].kaynak == "https://example.invalid/x.git"
    assert any("PyPI dışı" in u for u in kd.uyarilar)


def test_poetry_gecersiz() -> None:
    with pytest.raises(KilitHatasi, match="geçersiz TOML"):
        kilit.ayristir("[[package]\n", "poetry.lock")
    with pytest.raises(KilitHatasi, match="hiç paket"):
        kilit.ayristir("package = []\n", "poetry.lock")


# ------------------------------------------------------------- pylock.toml


def test_pylock_ayristirir() -> None:
    kd = kilit.ayristir(_oku("pylock.toml"), "pylock.toml")
    assert kd.tur == "pylock"
    assert [p.ad for p in kd.paketler] == ["example-attested", "example-plain"]
    assert kd.paketler[0].dosyalar[0].sha256 == "b" * 64
    assert kd.paketler[1].dosyalar[0].ad == "example_plain-2.1.0.tar.gz"


def test_pylock_gecersiz() -> None:
    with pytest.raises(KilitHatasi, match="geçersiz TOML"):
        kilit.ayristir("lock-version = [", "pylock.toml")
    with pytest.raises(KilitHatasi, match="hiç paket"):
        kilit.ayristir('lock-version = "1.0"\n', "pylock.toml")


# --------------------------------------------------------------- dispatcher


@pytest.mark.parametrize(
    ("ad", "metin", "beklenen"),
    [
        ("uv.lock", "", "uv"),
        ("poetry.lock", "", "poetry"),
        ("somelock.lock", "", "poetry"),
        ("pylock.toml", "", "pylock"),
        ("proj.pylock.toml", "", "pylock"),
        ("requirements-dev.txt", "foo==1.0", "requirements"),
        ("reqs.in", "foo==1.0", "requirements"),
        ("deps.txt", "[[packages]]\n", "pylock"),
        ("deps.txt", "[[package]]\nname='x'\nversion='1'\n", "poetry"),
        ("custom.dat", "[[package]]\nname='x'\nversion='1'\nwheels=[]\n", "uv"),
        ("custom.dat", "foo==1.0\n", "requirements"),
    ],
)
def test_tur_belirle(ad: str, metin: str, beklenen: str) -> None:
    assert kilit.tur_belirle(ad, metin) == beklenen


def test_tur_belirle_bilinmeyen() -> None:
    with pytest.raises(KilitHatasi, match="tanınmadı"):
        kilit.tur_belirle("data.bin", "\x00\x01")


def test_yukle_yok(tmp_path: Path) -> None:
    with pytest.raises(KilitHatasi, match="okunamadı"):
        kilit.yukle(str(tmp_path / "yok.lock"))


def test_yukle_gercek_dosya() -> None:
    kd = kilit.yukle(str(FIKSTUR / "uv.lock"))
    assert kd.yol.endswith("uv.lock")
    assert len(kd.paketler) == 3
