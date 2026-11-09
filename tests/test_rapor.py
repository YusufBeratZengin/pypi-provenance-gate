"""Report rendering: text table, colours, JSON schema."""

from __future__ import annotations

import json

from pypi_provenance_gate.model import (
    Durum,
    Gecis,
    Ihlal,
    Kanit,
    OncekiDurum,
    Paket,
    PaketSonuc,
    Rapor,
    Seviye,
)
from pypi_provenance_gate import rapor as rapor_mod


def _kanit(dosya: str = "foo-1.0.whl", depo: str | None = "github.com/example-org/foo") -> Kanit:
    return Kanit(
        dosya=dosya,
        durum=Durum.KANITLI,
        depo=depo,
        depolar=(depo,) if depo else (),
        yayinci_turu="GitHub",
        is_akisi="release.yml",
        kanit_sayisi=1,
    )


def _rapor() -> Rapor:
    iyi = PaketSonuc(
        paket=Paket("requests", "2.32.3"),
        durum=Durum.KANITLI,
        depolar=["github.com/psf/requests"],
        kanitlar=[_kanit("requests-2.32.3-py3-none-any.whl", "github.com/psf/requests")],
    )
    kotu = PaketSonuc(
        paket=Paket("example-unattested", "1.2.0"),
        durum=Durum.KANITSIZ,
        gecis=Gecis.GERILEDI,
        onceki=OncekiDurum("1.1.0", Durum.KANITLI, ("github.com/example-org/x",)),
        notlar=["önceki sürüm 1.1.0 kanıtlıydı, şimdi kanıtsız"],
        kanitlar=[
            Kanit("example_unattested-1.2.0.tar.gz", Durum.KANITSIZ, hata="provenance yok (HTTP 404)")
        ],
    )
    bilinmeyen = PaketSonuc(
        paket=Paket("example-unknown", "0.1"),
        durum=Durum.BILINMIYOR,
        notlar=["ağ hatası: timeout"],
    )
    degisen = PaketSonuc(
        paket=Paket("example-moved", "3.0"),
        durum=Durum.KANITLI,
        depolar=["github.com/new/owner", "github.com/old/owner"],
        gecis=Gecis.YAYINCI_DEGISTI,
        onceki=OncekiDurum("2.0", Durum.KANITLI, ("github.com/old/owner",)),
    )
    atlanan = PaketSonuc(
        paket=Paket("example-local", "0.0.0", kaynak="https://example.invalid/simple"),
        durum=Durum.ATLANDI,
    )
    r = Rapor(
        kilit_dosyasi="uv.lock",
        paketler=[iyi, kotu, bilinmeyen, degisen, atlanan],
        uyarilar=["örnek uyarı"],
        onceki_rev="HEAD~1",
        istek_sayisi=8,
    )
    r.ihlaller = [
        Ihlal("kanitsiz", "example-unattested", "example-unattested 1.2.0: kanıtsız", Seviye.HATA),
        Ihlal("gerileme", "example-unattested", "geriledi", Seviye.UYARI),
    ]
    return r


def test_metin_tablosu() -> None:
    metin = rapor_mod.metin(_rapor(), renk=False)
    assert "Lockfile: uv.lock" in metin
    assert "Compared with: HEAD~1" in metin
    assert "requests" in metin and "github.com/psf/requests" in metin
    assert "attested" in metin and "unattested" in metin
    assert "regression" in metin and "publisher changed" in metin
    assert "5 package(s): 2 attested, 1 unattested, 0 partial, 1 unknown, 1 skipped" in metin
    assert "Changes: 1 regression(s), 1 publisher change(s), 0 improvement(s)" in metin
    assert "HTTP requests: 8" in metin
    assert "Notes:" in metin
    assert "warning: örnek uyarı" in metin
    assert "Policy:" in metin
    assert "[error] kanitsiz" in metin
    assert "does not prove the package is safe" in metin


def test_metin_renkli_ve_renksiz() -> None:
    renkli = rapor_mod.metin(_rapor(), renk=True)
    assert "\x1b[32m" in renkli
    assert "\x1b[0m" in renkli
    renksiz = rapor_mod.metin(_rapor(), renk=False)
    assert "\x1b[" not in renksiz


def test_no_color_ortam_degiskeni(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("NO_COLOR", "1")
    assert "\x1b[" not in rapor_mod.metin(_rapor())


def test_otomatik_renk_tty_degil(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert "\x1b[" not in rapor_mod.metin(_rapor())
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert "\x1b[" in rapor_mod.metin(_rapor())


def test_satirlar_kirpma_ve_coklu_yayinci() -> None:
    uzun = PaketSonuc(
        paket=Paket("cok-uzun-paket-adi-" + "x" * 30, "1.0.0"),
        durum=Durum.KANITLI,
        depolar=["github.com/a/one", "github.com/b/two"],
    )
    satirlar = rapor_mod.satirlar(Rapor(kilit_dosyasi="x", paketler=[uzun]))
    ad, surum, durum, gecis, yayinci = satirlar[0]
    assert ad.endswith("…")
    assert yayinci.endswith("(+1)")
    assert gecis == "-"
    assert durum == "attested"


def test_json_semasi() -> None:
    veri = json.loads(rapor_mod.json_metni(_rapor(), "2026-01-01T00:00:00Z"))
    assert veri["schema_version"] == "1.0"
    assert veri["tool"] == "pypi-provenance-gate"
    assert veri["tool_version"] == "0.1.0"
    assert veri["generated_at"] == "2026-01-01T00:00:00Z"
    assert veri["lockfile"] == "uv.lock"
    assert veri["previous"] == "HEAD~1"
    assert veri["summary"]["total"] == 5
    assert veri["summary"]["by_status"]["attested"] == 2
    assert veri["summary"]["by_change"]["regression"] == 1
    assert veri["summary"]["http_requests"] == 8
    assert veri["summary"]["violations"] == 2
    assert veri["summary"]["errors"] == 1
    paket = {p["name"]: p for p in veri["packages"]}
    assert paket["requests"]["publisher_repositories"] == ["github.com/psf/requests"]
    assert paket["requests"]["files"][0]["workflow"] == "release.yml"
    assert paket["requests"]["files"][0]["attestation_count"] == 1
    assert paket["example-unattested"]["change"] == "regression"
    assert paket["example-unattested"]["previous_version"] == "1.1.0"
    assert paket["example-unattested"]["previous_status"] == "attested"
    assert paket["example-unattested"]["violations"][0]["rule"] == "kanitsiz"
    assert paket["example-unknown"]["files"] == []
    assert veri["violations"][0]["level"] == "error"
    assert veri["warnings"] == ["örnek uyarı"]


def test_json_uretimi_tekrarlanabilir() -> None:
    a = rapor_mod.json_metni(_rapor(), "2026-01-01T00:00:00Z")
    b = rapor_mod.json_metni(_rapor(), "2026-01-01T00:00:00Z")
    assert a == b
    assert json.loads(a)["packages"][0]["name"] == "requests"
