"""CLI end-to-end: exit codes, version, allowlist normalisation, policy wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

from pypi_provenance_gate import cli
from pypi_provenance_gate.model import Durum, Kanit, Seviye
from pypi_provenance_gate.surum import SURUM

WHEEL = "foo-1.0-py3-none-any.whl"
SDIST = "foo-1.0.tar.gz"
HASH = "a" * 64


def _uv_lock(
    ad: str = "foo",
    surum: str = "1.0",
    dosyalar: tuple[str, ...] = (WHEEL,),
) -> str:
    satirlar = [
        "version = 1",
        "[[package]]",
        f'name = "{ad}"',
        f'version = "{surum}"',
        'source = { registry = "https://pypi.org/simple" }',
    ]
    tekerlekler = [d for d in dosyalar if d.endswith(".whl")]
    if tekerlekler:
        satirlar.append("wheels = [")
        for dosya in tekerlekler:
            satirlar.append(
                f'  {{ url = "https://files.pythonhosted.org/packages/aa/bb/{dosya}", '
                f'hash = "sha256:{HASH}" }},'
            )
        satirlar.append("]")
    sdistler = [d for d in dosyalar if not d.endswith(".whl")]
    if sdistler:
        satirlar.append(
            f'sdist = {{ url = "https://files.pythonhosted.org/packages/aa/bb/{sdistler[0]}", '
            f'hash = "sha256:{HASH}" }}'
        )
    return "\n".join(satirlar) + "\n"


def _yaz(tmp_path: Path, ad: str, metin: str) -> Path:
    p = tmp_path / ad
    p.write_text(metin, encoding="utf-8")
    return p


class SahteIstemci:
    """No network: answers from ``harita`` keyed by (package, version) or filename."""

    harita: ClassVar[dict[Any, tuple[Durum, str | None]]] = {}
    cagrilar: ClassVar[list[tuple[str, str, str]]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.istek_sayisi = 0

    def kanit(self, ad: str, surum: str, dosya: str) -> Kanit:
        type(self).cagrilar.append((ad, surum, dosya))
        self.istek_sayisi += 1
        durum, depo = type(self).harita.get(
            (ad, surum, dosya),
            type(self).harita.get((ad, surum), (Durum.KANITSIZ, None)),
        )
        return Kanit(dosya=dosya, durum=durum, depo=depo, depolar=(depo,) if depo else ())

    def dosyalar(self, ad: str, surum: str) -> tuple[list[Any], str | None]:
        return [], None


@pytest.fixture
def sahte(monkeypatch: pytest.MonkeyPatch) -> type[SahteIstemci]:
    SahteIstemci.harita = {}
    SahteIstemci.cagrilar = []
    monkeypatch.setattr(cli, "IntegrityIstemcisi", SahteIstemci)
    return SahteIstemci


def _calistir(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> tuple[int, str, str]:
    kod = cli.main(argv)
    yakalanan = capsys.readouterr()
    return kod, yakalanan.out, yakalanan.err


def test_version_lockfile_olmadan(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str]
) -> None:
    kod, out, err = _calistir(capsys, ["--version"])
    assert kod == 0
    assert SURUM in out
    assert err == ""
    kod, out, _ = _calistir(capsys, ["--surum"])
    assert kod == 0
    assert SURUM in out
    # Ağ/kilit dosyası hiç açılmamalı.
    assert sahte.cagrilar == []


def test_sys_argv_ile_version(
    sahte: type[SahteIstemci], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["provenance-gate", "--version"])
    assert cli.main() == 0
    assert SURUM in capsys.readouterr().out


def test_lockfile_yoksa_exit_2(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    kod, _, err = _calistir(capsys, [str(tmp_path / "yok.lock")])
    assert kod == 2
    assert "error:" in err


def test_argparse_eksik_lockfile_exit_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_varsayilan_kanitsiz_exit_0(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    kod, out, _ = _calistir(capsys, [str(kilit), "--onbellek-yok"])
    assert kod == 0
    assert "unattested" in out
    assert "Policy:" not in out


def test_ci_kanitsiz_exit_1(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    kod, out, _ = _calistir(capsys, [str(kilit), "--ci", "--onbellek-yok"])
    assert kod == 1
    assert "[error] kanitsiz" in out


@pytest.mark.parametrize("yazim", ["Foo_Bar", "foo.bar", "FOO-BAR", " foo_bar "])
def test_izin_normalizasyonu_politika_ile_ayni(
    sahte: type[SahteIstemci],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    yazim: str,
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock(ad="Foo_Bar"))
    politika = _yaz(
        tmp_path,
        "politika.toml",
        '[genel]\nkanitsiz = "hata"\nkanitsiz_izin = ["Foo_Bar"]\n',
    )

    cli_kodu, _, _ = _calistir(
        capsys, [str(kilit), "--ci", "--izin", yazim, "--onbellek-yok"]
    )
    dosya_kodu, _, _ = _calistir(
        capsys, [str(kilit), "--politika", str(politika), "--onbellek-yok"]
    )
    assert cli_kodu == 0
    assert dosya_kodu == cli_kodu


def test_izin_surum_pini_normalize(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock(ad="Foo_Bar"))
    kod, _, _ = _calistir(
        capsys, [str(kilit), "--ci", "--izin", "Foo_Bar==1.0", "--onbellek-yok"]
    )
    assert kod == 0
    kod, _, _ = _calistir(
        capsys, [str(kilit), "--ci", "--izin", "Foo_Bar==2.0", "--onbellek-yok"]
    )
    assert kod == 1


def test_yalniz_beklenen_diger_kurallari_etkinlestirmez(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    beklenen = _yaz(tmp_path, "beklenen.toml", '[depolar]\nbaska = "example-org/baska"\n')
    kod, out, _ = _calistir(
        capsys, [str(kilit), "--beklenen", str(beklenen), "--onbellek-yok"]
    )
    assert kod == 0
    assert "Policy:" not in out


def test_beklenen_yayinci_ihlali_exit_1(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    sahte.harita = {("foo", "1.0"): (Durum.KANITLI, "github.com/attacker/foo")}
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    beklenen = _yaz(
        tmp_path, "beklenen.toml", '[depolar]\nfoo = "github.com/example-org/foo"\n'
    )
    kod, out, _ = _calistir(
        capsys, [str(kilit), "--beklenen", str(beklenen), "--onbellek-yok"]
    )
    assert kod == 1
    assert "[error] yayinci_uyumsuz" in out
    assert "github.com/attacker/foo" in out


def test_kismi_durumda_beklenen_yayinci_ihlali(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    sahte.harita = {
        ("foo", "1.0", WHEEL): (Durum.KANITLI, "github.com/attacker/foo"),
        ("foo", "1.0", SDIST): (Durum.KANITSIZ, None),
    }
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock(dosyalar=(WHEEL, SDIST)))
    beklenen = _yaz(
        tmp_path, "beklenen.toml", '[depolar]\nfoo = "github.com/example-org/foo"\n'
    )
    kod, out, _ = _calistir(
        capsys, [str(kilit), "--beklenen", str(beklenen), "--onbellek-yok"]
    )
    assert kod == 1
    assert "partial" in out
    assert "yayinci_uyumsuz" in out


def test_kismi_karisik_yayincilar_bekleneni_gizleyemez(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    diger_wheel = "foo-1.0-py2-none-any.whl"
    sahte.harita = {
        ("foo", "1.0", WHEEL): (Durum.KANITLI, "github.com/example-org/foo"),
        ("foo", "1.0", diger_wheel): (Durum.KANITLI, "github.com/attacker/foo"),
        ("foo", "1.0", SDIST): (Durum.KANITSIZ, None),
    }
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock(dosyalar=(WHEEL, diger_wheel, SDIST)))
    beklenen = _yaz(
        tmp_path, "beklenen.toml", '[depolar]\nfoo = "example-org/foo"\n'
    )
    kod, out, err = _calistir(
        capsys, [str(kilit), "--beklenen", str(beklenen), "--onbellek-yok"]
    )
    assert kod == 1
    assert "partial" in out
    assert "[error] yayinci_uyumsuz" in out
    assert "github.com/attacker/foo" in out
    assert err == ""
    assert {dosya for _, _, dosya in sahte.cagrilar} == {WHEEL, diger_wheel, SDIST}


@pytest.mark.parametrize("mod", ["politikasiz", "beklenen", "ci", "politika"])
def test_onceki_beklenen_gerilemeyi_yalniz_acik_politikayla_etkinlestirir(
    sahte: type[SahteIstemci],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mod: str,
) -> None:
    sahte.harita = {
        ("foo", "0.9"): (Durum.KANITLI, "github.com/example-org/foo"),
        ("foo", "1.0"): (Durum.KANITSIZ, None),
    }
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    beklenen = _yaz(tmp_path, "beklenen.toml", '[depolar]\nfoo = "example-org/foo"\n')
    monkeypatch.setattr(cli.fark, "onceki_metin", lambda rev, yol: _uv_lock(surum="0.9"))
    argv = [str(kilit), "--onceki", "HEAD~1", "--onbellek-yok"]
    if mod != "politikasiz":
        argv.extend(["--beklenen", str(beklenen)])
    if mod == "ci":
        argv.append("--ci")
    elif mod == "politika":
        politika = _yaz(tmp_path, "politika.toml", '[genel]\ngerileme = "hata"\n')
        argv.extend(["--politika", str(politika)])
    kod, out, err = _calistir(capsys, argv)
    assert "regression" in out
    assert err == ""
    if mod in ("ci", "politika"):
        assert kod == 1
        assert "[error] gerileme" in out
    else:
        assert kod == 0
        assert "Policy:" not in out


def test_politika_hatasi_exit_2(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    politika = _yaz(tmp_path, "politika.toml", "[genel]\nkanitsiz = 3\n")
    kod, _, err = _calistir(
        capsys, [str(kilit), "--politika", str(politika), "--onbellek-yok"]
    )
    assert kod == 2
    assert "geçersiz seviye" in err


def test_onceki_gerileme_exit_1(
    sahte: type[SahteIstemci],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sahte.harita = {
        ("foo", "0.9"): (Durum.KANITLI, "github.com/example-org/foo"),
        ("foo", "1.0"): (Durum.KANITSIZ, None),
    }
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock(surum="1.0"))
    monkeypatch.setattr(cli.fark, "onceki_metin", lambda rev, yol: _uv_lock(surum="0.9"))

    kod, out, _ = _calistir(
        capsys, [str(kilit), "--onceki", "HEAD~1", "--ci", "--onbellek-yok"]
    )
    assert kod == 1
    assert "regression" in out
    assert "[error] gerileme" in out


def test_onceki_ayni_surum_degismedi(
    sahte: type[SahteIstemci],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sahte.harita = {("foo", "1.0"): (Durum.KANITLI, "github.com/example-org/foo")}
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    monkeypatch.setattr(cli.fark, "onceki_metin", lambda rev, yol: _uv_lock())
    kod, out, _ = _calistir(
        capsys, [str(kilit), "--onceki", "HEAD~1", "--ci", "--onbellek-yok"]
    )
    assert kod == 0
    assert "unchanged" in out


def test_onceki_git_hatasi_exit_2(
    sahte: type[SahteIstemci],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())

    def patlat(rev: str, yol: str) -> str:
        raise cli.fark.GitHatasi("git bulunamadı")

    monkeypatch.setattr(cli.fark, "onceki_metin", patlat)
    kod, _, err = _calistir(
        capsys, [str(kilit), "--onceki", "HEAD~1", "--onbellek-yok"]
    )
    assert kod == 2
    assert "git bulunamadı" in err


def test_json_ciktisi(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    sahte.harita = {("foo", "1.0"): (Durum.KANITLI, "github.com/example-org/foo")}
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    kod, out, _ = _calistir(capsys, [str(kilit), "--json", "--onbellek-yok"])
    veri = json.loads(out)
    assert kod == 0
    assert veri["summary"]["total"] == 1
    assert veri["packages"][0]["status"] == "attested"
    assert veri["packages"][0]["publisher_repositories"] == ["github.com/example-org/foo"]


def test_renk_secenekleri(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    kod, out, _ = _calistir(capsys, [str(kilit), "--renk", "always", "--onbellek-yok"])
    assert kod == 0
    assert "\x1b[" in out
    kod, out, _ = _calistir(capsys, [str(kilit), "--renk", "never", "--onbellek-yok"])
    assert kod == 0
    assert "\x1b[" not in out


def test_onbellek_dizini_kullanilir(
    sahte: type[SahteIstemci], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    kilit = _yaz(tmp_path, "uv.lock", _uv_lock())
    onbellek = tmp_path / "onbellek"
    kod, _, _ = _calistir(
        capsys, [str(kilit), "--onbellek", str(onbellek), "--onbellek-ttl", "60"]
    )
    assert kod == 0


def test_politika_olustur_dallari(tmp_path: Path) -> None:
    parser = cli._argparse()
    beklenen = _yaz(tmp_path, "beklenen.toml", '[depolar]\nfoo = "example-org/foo"\n')
    politika_yolu = _yaz(
        tmp_path, "politika.toml", '[genel]\nkanitsiz = "uyari"\nkanitsiz_izin = ["bar"]\n'
    )

    assert cli._politika_olustur(parser.parse_args(["x.lock"])) is None

    ci = cli._politika_olustur(parser.parse_args(["x.lock", "--ci"]))
    assert ci is not None
    assert ci.seviye("kanitsiz") is Seviye.HATA

    yalniz = cli._politika_olustur(
        parser.parse_args(["x.lock", "--beklenen", str(beklenen)])
    )
    assert yalniz is not None
    assert yalniz.seviye("kanitsiz") is Seviye.YOKSAY
    assert yalniz.seviye("gerileme") is Seviye.YOKSAY
    assert yalniz.seviye("yayinci_degisimi") is Seviye.YOKSAY
    assert yalniz.seviye("yayinci_uyumsuz") is Seviye.HATA
    assert yalniz.beklenen == {"foo": "github.com/example-org/foo"}

    ci_beklenen = cli._politika_olustur(
        parser.parse_args(["x.lock", "--ci", "--beklenen", str(beklenen)])
    )
    assert ci_beklenen is not None
    assert ci_beklenen.seviye("kanitsiz") is Seviye.HATA

    dosya = cli._politika_olustur(
        parser.parse_args(["x.lock", "--politika", str(politika_yolu), "--ci"])
    )
    assert dosya is not None
    assert dosya.izinli("bar", "1")
    assert dosya.seviye("kanitsiz") is Seviye.UYARI  # dosya --ci'yi geçersiz kılar

    izinli = cli._politika_olustur(
        parser.parse_args(["x.lock", "--izin", "Foo_Bar", "--izin", "  "])
    )
    assert izinli is not None
    assert izinli.izinli("foo-bar", "1")
    assert izinli.seviye("kanitsiz") is Seviye.UYARI
