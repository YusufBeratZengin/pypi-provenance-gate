"""Git-based previous-lockfile comparison and the regression rules."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pypi_provenance_gate import fark
from pypi_provenance_gate.model import Durum, Gecis, OncekiDurum, Paket, PaketSonuc

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git gerekli")


def _sonuc(ad: str, durum: Durum, depolar: list[str] | None = None, surum: str = "1.0") -> PaketSonuc:
    return PaketSonuc(
        paket=Paket(ad=ad, surum=surum), durum=durum, depolar=list(depolar or [])
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


@pytest.fixture
def depo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def test_onceki_metin_okunur(depo: Path) -> None:
    kilit = depo / "uv.lock"
    kilit.write_text("eski = true\n", encoding="utf-8")
    _git(depo, "add", "uv.lock")
    _git(depo, "commit", "-m", "ilk")
    kilit.write_text("eski = false\n", encoding="utf-8")
    assert fark.onceki_metin("HEAD", kilit) == "eski = true\n"
    assert "eski" in fark.onceki_metin("HEAD", str(kilit))


def test_gecersiz_rev(depo: Path) -> None:
    kilit = depo / "uv.lock"
    kilit.write_text("x = 1\n", encoding="utf-8")
    _git(depo, "add", "uv.lock")
    _git(depo, "commit", "-m", "ilk")
    with pytest.raises(fark.GitHatasi, match="okunamadı"):
        fark.onceki_metin("yok-boyle-bir-rev", kilit)


def test_dosya_depoda_yok(depo: Path) -> None:
    kilit = depo / "uv.lock"
    kilit.write_text("x = 1\n", encoding="utf-8")
    _git(depo, "add", "uv.lock")
    _git(depo, "commit", "-m", "ilk")
    _git(depo, "rm", "-q", "uv.lock")
    _git(depo, "commit", "-m", "sil")
    with pytest.raises(fark.GitHatasi, match="okunamadı"):
        fark.onceki_metin("HEAD", kilit)


def test_depo_disi(tmp_path: Path) -> None:
    disari = tmp_path / "disari"
    disari.mkdir()
    (disari / "uv.lock").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(fark.GitHatasi, match="git deposu"):
        fark.repo_koku(disari / "uv.lock")


def test_git_yok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def patlat(*a: object, **k: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", patlat)
    with pytest.raises(fark.GitHatasi, match="git bulunamadı"):
        fark.repo_koku(tmp_path / "uv.lock")


def test_gerileme() -> None:
    mevcut = [_sonuc("foo", Durum.KANITSIZ)]
    onceki = [_sonuc("foo", Durum.KANITLI, ["github.com/example/foo"])]
    fark.karsilastir(mevcut, onceki)
    assert mevcut[0].gecis is Gecis.GERILEDI
    assert mevcut[0].onceki == OncekiDurum(
        surum="1.0", durum=Durum.KANITLI, depolar=("github.com/example/foo",)
    )
    assert any("kanıtlıydı" in n for n in mevcut[0].notlar)


def test_kismi_de_gerileme() -> None:
    mevcut = [_sonuc("foo", Durum.KISMI)]
    fark.karsilastir(mevcut, [_sonuc("foo", Durum.KANITLI)])
    assert mevcut[0].gecis is Gecis.GERILEDI


def test_bilinmiyor_gerileme_sayilmaz() -> None:
    mevcut = [_sonuc("foo", Durum.BILINMIYOR)]
    fark.karsilastir(mevcut, [_sonuc("foo", Durum.KANITLI)])
    assert mevcut[0].gecis is Gecis.YOK
    assert any("bilinmiyor" in n for n in mevcut[0].notlar)


def test_yayinci_degisir() -> None:
    mevcut = [_sonuc("foo", Durum.KANITLI, ["github.com/other/foo"])]
    fark.karsilastir(mevcut, [_sonuc("foo", Durum.KANITLI, ["github.com/example/foo"])])
    assert mevcut[0].gecis is Gecis.YAYINCI_DEGISTI
    assert any("yayıncı deposu değişti" in n for n in mevcut[0].notlar)


def test_degismedi_ve_iyilesme() -> None:
    ayni = [_sonuc("foo", Durum.KANITLI, ["github.com/example/foo"])]
    fark.karsilastir(ayni, [_sonuc("foo", Durum.KANITLI, ["github.com/example/foo"])])
    assert ayni[0].gecis is Gecis.DEGISMEDI

    iyilesen = [_sonuc("foo", Durum.KANITLI)]
    fark.karsilastir(iyilesen, [_sonuc("foo", Durum.KANITSIZ)])
    assert iyilesen[0].gecis is Gecis.IYILESME

    ayni_kotu = [_sonuc("foo", Durum.KANITSIZ)]
    fark.karsilastir(ayni_kotu, [_sonuc("foo", Durum.KANITSIZ)])
    assert ayni_kotu[0].gecis is Gecis.DEGISMEDI


def test_bilinmeyen_depo_karsilastirmasi() -> None:
    mevcut = [_sonuc("foo", Durum.KANITLI)]
    fark.karsilastir(mevcut, [_sonuc("foo", Durum.KANITLI)])
    assert mevcut[0].gecis is Gecis.DEGISMEDI


def test_yeni_paket_gecis_yok() -> None:
    mevcut = [_sonuc("yeni", Durum.KANITSIZ)]
    fark.karsilastir(mevcut, [_sonuc("eski", Durum.KANITLI)])
    assert mevcut[0].gecis is Gecis.YOK
    assert mevcut[0].onceki is None


def test_ad_normalizasyonu_eslesir() -> None:
    mevcut = [_sonuc("Foo_Bar", Durum.KANITSIZ)]
    fark.karsilastir(mevcut, [_sonuc("foo-bar", Durum.KANITLI)])
    assert mevcut[0].gecis is Gecis.GERILEDI
