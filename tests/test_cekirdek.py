"""Classification tests: attested / unattested / partial / unknown / skipped."""

from __future__ import annotations

from pypi_provenance_gate.cekirdek import kontrol
from pypi_provenance_gate.integrity import IntegrityIstemcisi, Yanit
from pypi_provenance_gate.model import Dosya, Durum, Paket

from conftest import A, SDIST, WHEEL, SahteTasima, json_url, kanit_govdesi, kanit_url, pypi_json_govdesi


def _istemci(tasima: SahteTasima) -> IntegrityIstemcisi:
    return IntegrityIstemcisi(tasima=tasima, onbellek=None, uyku=lambda _s: None)


def _paket(ad: str = "example-attested", surum: str = "1.0.0", **kw: object) -> Paket:
    return Paket(ad=ad, surum=surum, **kw)  # type: ignore[arg-type]


def test_tum_dosyalar_kanitli() -> None:
    tasima = SahteTasima(
        {
            kanit_url("example-attested", "1.0.0", SDIST): Yanit(200, kanit_govdesi()),
            kanit_url("example-attested", "1.0.0", WHEEL): Yanit(200, kanit_govdesi()),
        }
    )
    paket = _paket(dosyalar=(Dosya(SDIST), Dosya(WHEEL)))
    rapor = kontrol([paket], _istemci(tasima), kilit_dosyasi="uv.lock")
    assert rapor.paketler[0].durum is Durum.KANITLI
    assert rapor.paketler[0].depolar == ["github.com/example-org/example-project"]
    assert rapor.istek_sayisi == 2
    assert rapor.kilit_dosyasi == "uv.lock"


def test_kismi_kanit() -> None:
    tasima = SahteTasima(
        {kanit_url("p", "1", SDIST): Yanit(200, kanit_govdesi())}
    )
    rapor = kontrol([_paket("p", "1", dosyalar=(Dosya(SDIST), Dosya(WHEEL)))], _istemci(tasima))
    sonuc = rapor.paketler[0]
    assert sonuc.durum is Durum.KISMI
    assert any("kanıtsız dosya" in n for n in sonuc.notlar)


def test_hic_kanit_yok() -> None:
    rapor = kontrol([_paket("p", "1", dosyalar=(Dosya("p-1.whl"),))], _istemci(SahteTasima()))
    assert rapor.paketler[0].durum is Durum.KANITSIZ


def test_bir_dosya_bilinmiyor_kanitsiz_demez() -> None:
    tasima = SahteTasima({kanit_url("p", "1", WHEEL): Yanit(503, b"")})
    rapor = kontrol(
        [_paket("p", "1", dosyalar=(Dosya(SDIST), Dosya(WHEEL)))],
        IntegrityIstemcisi(tasima=tasima, onbellek=None, deneme=1),
    )
    assert rapor.paketler[0].durum is Durum.BILINMIYOR


def test_pypi_disi_indeks_atlanir() -> None:
    paket = _paket("p", "1", kaynak="https://packages.example.invalid/simple")
    rapor = kontrol([paket], _istemci(SahteTasima()))
    assert rapor.paketler[0].durum is Durum.ATLANDI
    assert any("PyPI dışı" in n for n in rapor.paketler[0].notlar)


def test_hash_ile_dosya_eslesir() -> None:
    tasima = SahteTasima(
        {
            json_url("p", "1"): Yanit(
                200, pypi_json_govdesi("p", "1", [(SDIST, A), (WHEEL, "b" * 64)])
            ),
            kanit_url("p", "1", SDIST): Yanit(200, kanit_govdesi()),
        }
    )
    paket = _paket("p", "1", dosyalar=(Dosya(None, sha256=A),))
    rapor = kontrol([paket], _istemci(tasima))
    assert rapor.paketler[0].durum is Durum.KANITLI
    assert [k.dosya for k in rapor.paketler[0].kanitlar] == [SDIST]


def test_hash_eslesmezse_bilinmiyor() -> None:
    tasima = SahteTasima(
        {json_url("p", "1"): Yanit(200, pypi_json_govdesi("p", "1", [(SDIST, A)]))}
    )
    rapor = kontrol([_paket("p", "1", dosyalar=(Dosya(None, sha256="f" * 64),))], _istemci(tasima))
    sonuc = rapor.paketler[0]
    assert sonuc.durum is Durum.BILINMIYOR
    assert any("eşleşmedi" in n for n in sonuc.notlar)


def test_hashsiz_adsiz_tum_dosyalar_sorgulanir() -> None:
    tasima = SahteTasima(
        {
            json_url("p", "1"): Yanit(200, pypi_json_govdesi("p", "1", [(SDIST, A), (WHEEL, "b" * 64)])),
            kanit_url("p", "1", SDIST): Yanit(200, kanit_govdesi()),
            kanit_url("p", "1", WHEEL): Yanit(200, kanit_govdesi()),
        }
    )
    rapor = kontrol([_paket("p", "1", dosyalar=(Dosya(None),))], _istemci(tasima))
    assert rapor.paketler[0].durum is Durum.KANITLI


def test_dosya_cozulemezse_bilinmiyor() -> None:
    rapor = kontrol([_paket("p", "1", dosyalar=(Dosya(None, sha256=A),))], _istemci(SahteTasima()))
    sonuc = rapor.paketler[0]
    assert sonuc.durum is Durum.BILINMIYOR
    assert any("bulunamadı" in n for n in sonuc.notlar)


def test_dosya_limiti_kismi_yapar() -> None:
    tasima = SahteTasima()
    for ad in ("a.whl", "b.whl", "c.whl"):
        tasima.harita[kanit_url("p", "1", ad)] = Yanit(200, kanit_govdesi())
    paket = _paket("p", "1", dosyalar=(Dosya("a.whl"), Dosya("b.whl"), Dosya("c.whl")))
    rapor = kontrol([paket], _istemci(tasima), dosya_limiti=2)
    sonuc = rapor.paketler[0]
    assert sonuc.durum is Durum.KISMI
    assert any("kontrol edilmedi" in n for n in sonuc.notlar)
    assert len(tasima.integrity_cagrilari) == 2


def test_ayni_dosya_iki_kez_sorgulanmaz() -> None:
    tasima = SahteTasima({kanit_url("p", "1", SDIST): Yanit(200, kanit_govdesi())})
    rapor = kontrol([_paket("p", "1", dosyalar=(Dosya(SDIST), Dosya(SDIST)))], _istemci(tasima))
    assert len(tasima.cagrilar) == 1
    assert rapor.paketler[0].durum is Durum.KANITLI


def test_coklu_yayinci_notu() -> None:
    tasima = SahteTasima(
        {
            kanit_url("p", "1", SDIST): Yanit(200, kanit_govdesi("example-org/one")),
            kanit_url("p", "1", WHEEL): Yanit(200, kanit_govdesi("example-org/two")),
        }
    )
    rapor = kontrol([_paket("p", "1", dosyalar=(Dosya(SDIST), Dosya(WHEEL)))], _istemci(tasima))
    sonuc = rapor.paketler[0]
    assert sonuc.durum is Durum.KANITLI
    assert len(sonuc.depolar) == 2
    assert any("birden fazla yayıncı" in n for n in sonuc.notlar)


def test_butce_asilinca_bilinmiyor() -> None:
    tasima = SahteTasima({kanit_url("p", "1", SDIST): Yanit(200, kanit_govdesi())})
    istemci = IntegrityIstemcisi(tasima=tasima, onbellek=None, butce=0)
    rapor = kontrol([_paket("p", "1", dosyalar=(Dosya(SDIST),))], istemci)
    assert rapor.paketler[0].durum is Durum.BILINMIYOR
