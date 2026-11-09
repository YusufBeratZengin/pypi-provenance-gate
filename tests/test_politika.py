"""Policy parsing, allowlists, expected publishers and exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest

from pypi_provenance_gate.model import Durum, Gecis, OncekiDurum, Paket, PaketSonuc, Rapor, Seviye
from pypi_provenance_gate.politika import (
    PolitikaHatasi,
    beklenen_yukle,
    birlestir,
    cikis_kodu,
    degerlendir,
    varsayilan_ci,
    yukle,
)


def _yaz(tmp_path: Path, ad: str, metin: str) -> Path:
    p = tmp_path / ad
    p.write_text(metin, encoding="utf-8")
    return p


def _sonuc(
    ad: str = "foo",
    durum: Durum = Durum.KANITSIZ,
    depolar: list[str] | None = None,
    gecis: Gecis = Gecis.YOK,
    surum: str = "1.0",
) -> PaketSonuc:
    s = PaketSonuc(paket=Paket(ad=ad, surum=surum), durum=durum, depolar=list(depolar or []))
    s.gecis = gecis
    if gecis is not Gecis.YOK:
        s.onceki = OncekiDurum(surum="0.9", durum=Durum.KANITLI, depolar=("github.com/old/foo",))
    return s


def test_varsayilan_degerler() -> None:
    p = varsayilan_ci()
    assert p.seviye("kanitsiz") is Seviye.HATA
    assert p.seviye("bilinmeyen-kural") is Seviye.UYARI
    assert cikis_kodu([]) == 0


def test_politika_yukle(tmp_path: Path) -> None:
    yol = _yaz(
        tmp_path,
        "politika.toml",
        """
[genel]
kanitsiz = "hata"
kismi = "uyari"
bilinmiyor = "yoksay"
kanitsiz_izin = ["Foo_Bar", "baz==1.2.3"]

[beklenen]
requests = "psf/requests"
"GitHub-Only" = "https://github.com/example-org/example-project.git"
""",
    )
    p = yukle(yol)
    assert p.seviye("kanitsiz") is Seviye.HATA
    assert p.seviye("kismi") is Seviye.UYARI
    assert p.seviye("bilinmiyor") is Seviye.YOKSAY
    assert p.izinli("foo-bar", "9.9")
    assert p.izinli("baz", "1.2.3")
    assert not p.izinli("baz", "9.9")
    assert p.beklenen["requests"] == "github.com/psf/requests"
    assert p.beklenen["github-only"] == "github.com/example-org/example-project"
    assert p.kaynak == str(yol)


def test_politika_temel_uzerine_yukle(tmp_path: Path) -> None:
    yol = _yaz(tmp_path, "p.toml", '[genel]\nkanitsiz = "uyari"\n')
    p = yukle(yol, temel=varsayilan_ci())
    assert p.seviye("kanitsiz") is Seviye.UYARI
    assert p.seviye("gerileme") is Seviye.HATA


@pytest.mark.parametrize(
    ("metin", "parca"),
    [
        ("[genel]\nkanitsiz = 'belki'\n", "geçersiz seviye"),
        ("[genel]\ntypo = 'hata'\n", "bilinmeyen anahtar"),
        ("[baska]\nx = 1\n", "bilinmeyen bölüm"),
        ("[genel]\nkanitsiz_izin = 'tek'\n", "liste"),
        ("[genel]\nkanitsiz_izin = [1]\n", "metin olmayan"),
        ("[genel]\nbeklenen = [1]\n", "bilinmeyen anahtar"),
        ("genel = 3\n", "tablo"),
        ("[[", "geçersiz TOML"),
    ],
)
def test_politika_hatalari(tmp_path: Path, metin: str, parca: str) -> None:
    with pytest.raises(PolitikaHatasi, match=parca):
        yukle(_yaz(tmp_path, "p.toml", metin))


def test_politika_beklenen_hatasi(tmp_path: Path) -> None:
    with pytest.raises(PolitikaHatasi, match="beklenen yayıncı"):
        yukle(_yaz(tmp_path, "p.toml", "[beklenen]\nfoo = 3\n"))
    with pytest.raises(PolitikaHatasi, match="geçersiz depo"):
        yukle(_yaz(tmp_path, "p.toml", '[beklenen]\nfoo = "http://"\n'))


def test_politika_dosya_yok() -> None:
    with pytest.raises(PolitikaHatasi, match="okunamadı"):
        yukle("/definitely/not/here/politika.toml")


def test_beklenen_yukle(tmp_path: Path) -> None:
    yol = _yaz(tmp_path, "beklenen.toml", '[depolar]\nfoo = "example-org/foo"\n')
    assert beklenen_yukle(yol) == {"foo": "github.com/example-org/foo"}


@pytest.mark.parametrize(
    ("metin", "parca"),
    [
        ("[[", "geçersiz TOML"),
        ("[x]\na = 1\n", "bilinmeyen bölüm"),
        ('depolar = "x"\n', "tablo"),
    ],
)
def test_beklenen_hatalari(tmp_path: Path, metin: str, parca: str) -> None:
    with pytest.raises(PolitikaHatasi, match=parca):
        beklenen_yukle(_yaz(tmp_path, "b.toml", metin))


def test_birlestir() -> None:
    a = varsayilan_ci()
    b = yukle_stub()
    c = birlestir(a, b)
    assert c.seviye("kanitsiz") is Seviye.UYARI
    assert c.seviye("gerileme") is Seviye.HATA
    assert c.izinli("izinli", "1")
    assert c.beklenen["foo"] == "github.com/example/foo"


def yukle_stub() -> object:
    from pypi_provenance_gate.politika import Politika

    return Politika(
        seviyeler={"kanitsiz": Seviye.UYARI},
        kanitsiz_izin=frozenset({"izinli"}),
        beklenen={"foo": "github.com/example/foo"},
    )


def test_degerlendir_kanitsiz_ve_izin() -> None:
    from pypi_provenance_gate.politika import Politika

    rapor = Rapor(kilit_dosyasi="uv.lock", paketler=[_sonuc("foo"), _sonuc("bar")])
    politika = Politika(kanitsiz_izin=frozenset({"bar"}))
    degerlendir(rapor, politika)
    assert [i.paket for i in rapor.ihlaller] == ["foo"]
    assert rapor.ihlaller[0].seviye is Seviye.UYARI
    assert cikis_kodu(rapor.ihlaller) == 0


def test_degerlendir_hata_seviyesi() -> None:
    rapor = Rapor(kilit_dosyasi="uv.lock", paketler=[_sonuc()])
    degerlendir(rapor, varsayilan_ci())
    assert cikis_kodu(rapor.ihlaller) == 1


def test_degerlendir_gerileme_ve_yayinci() -> None:
    rapor = Rapor(
        kilit_dosyasi="uv.lock",
        paketler=[
            _sonuc("a", Durum.KANITLI, ["github.com/x/a"], Gecis.GERILEDI),
            _sonuc("b", Durum.KANITLI, ["github.com/x/b"], Gecis.YAYINCI_DEGISTI),
        ],
    )
    degerlendir(rapor, varsayilan_ci())
    kurallar = {i.kural for i in rapor.ihlaller}
    assert {"gerileme", "yayinci_degisimi"} <= kurallar
    assert all(i.seviye is Seviye.HATA for i in rapor.ihlaller)


def test_degerlendir_yoksay_ve_atlandi() -> None:
    from pypi_provenance_gate.politika import Politika

    p = Politika(seviyeler={"kanitsiz": Seviye.YOKSAY})
    rapor = Rapor(
        kilit_dosyasi="x",
        paketler=[_sonuc("a", Durum.KANITSIZ), _sonuc("b", Durum.ATLANDI)],
    )
    degerlendir(rapor, p)
    assert rapor.ihlaller == []


def test_beklenen_yayinci_uyumsuz() -> None:
    from pypi_provenance_gate.politika import Politika

    p = Politika(beklenen={"foo": "github.com/example-org/foo"})
    rapor = Rapor(
        kilit_dosyasi="x",
        paketler=[
            _sonuc("foo", Durum.KANITLI, ["github.com/attacker/foo"]),
            _sonuc("bar", Durum.KANITLI, ["github.com/example-org/bar"]),
            _sonuc("baz", Durum.KANITSIZ),
        ],
    )
    degerlendir(rapor, p)
    assert len(rapor.ihlaller) == 2
    assert rapor.ihlaller[0].kural == "yayinci_uyumsuz"
    assert "github.com/attacker/foo" in rapor.ihlaller[0].mesaj
    assert rapor.ihlaller[1].kural == "kanitsiz"


def test_beklenen_eslesir() -> None:
    from pypi_provenance_gate.politika import Politika

    p = Politika(beklenen={"foo": "github.com/example-org/foo"})
    rapor = Rapor(kilit_dosyasi="x", paketler=[_sonuc("foo", Durum.KANITLI, ["github.com/example-org/foo"])])
    degerlendir(rapor, p)
    assert rapor.ihlaller == []


def test_beklenen_yayinci_kismi_durumda_da_denetlenir() -> None:
    from pypi_provenance_gate.politika import Politika

    p = Politika(beklenen={"foo": "github.com/example-org/foo"})
    rapor = Rapor(
        kilit_dosyasi="x",
        paketler=[_sonuc("foo", Durum.KISMI, ["github.com/attacker/foo"])],
    )
    degerlendir(rapor, p)
    kurallar = [i.kural for i in rapor.ihlaller]
    assert "yayinci_uyumsuz" in kurallar
    uyumsuz = next(i for i in rapor.ihlaller if i.kural == "yayinci_uyumsuz")
    assert "github.com/attacker/foo" in uyumsuz.mesaj
    assert cikis_kodu(rapor.ihlaller) == 1


def test_beklenen_yayinci_kismi_eslesirse_ihlal_yok() -> None:
    from pypi_provenance_gate.politika import Politika

    p = Politika(beklenen={"foo": "github.com/example-org/foo"})
    rapor = Rapor(
        kilit_dosyasi="x",
        paketler=[_sonuc("foo", Durum.KISMI, ["github.com/example-org/foo"])],
    )
    degerlendir(rapor, p)
    assert [i.kural for i in rapor.ihlaller] == ["kismi"]


def test_izin_normallestir_tek_kural() -> None:
    from pypi_provenance_gate.politika import izin_normallestir

    assert izin_normallestir("Foo_Bar") == "foo-bar"
    assert izin_normallestir(" Foo.Bar ") == "foo-bar"
    assert izin_normallestir("Foo_Bar==1.0") == "foo-bar==1.0"
