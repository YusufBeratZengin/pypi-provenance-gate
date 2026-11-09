"""Cache behaviour: persistence, TTL, corruption, unwritable directory."""

from __future__ import annotations

from pathlib import Path

from pypi_provenance_gate import onbellek as onbellek_mod
from pypi_provenance_gate.onbellek import Onbellek, varsayilan_dizin


def test_koy_al_kaydet(tmp_path: Path) -> None:
    o = Onbellek(tmp_path)
    o.koy("https://x/1", 200, b"govde")
    o.kaydet()
    assert (tmp_path / "onbellek.json").exists()

    yeni = Onbellek(tmp_path)
    kayit = yeni.al("https://x/1")
    assert kayit is not None
    assert kayit.kod == 200
    assert kayit.govde == b"govde"


def test_kaydet_kirli_degilse_yazmaz(tmp_path: Path) -> None:
    o = Onbellek(tmp_path)
    o.kaydet()
    assert not (tmp_path / "onbellek.json").exists()


def test_ttl_suresi_dolar(tmp_path: Path) -> None:
    saat = {"t": 1000.0}
    o = Onbellek(tmp_path, ttl=10, simdi=lambda: saat["t"])
    o.koy("k", 200, b"v")
    assert o.al("k") is not None
    saat["t"] = 1011.0
    assert o.al("k") is None


def test_ttl_negatif_sinirsiz(tmp_path: Path) -> None:
    saat = {"t": 0.0}
    o = Onbellek(tmp_path, ttl=-1, simdi=lambda: saat["t"])
    o.koy("k", 200, b"v")
    saat["t"] = 10**9
    assert o.al("k") is not None


def test_bozuk_dosya_yok_sayilir(tmp_path: Path) -> None:
    (tmp_path / "onbellek.json").write_text("{bozuk", encoding="utf-8")
    o = Onbellek(tmp_path)
    assert o.al("k") is None
    o.koy("k", 404, b"")
    o.kaydet()
    assert Onbellek(tmp_path).al("k") is not None


def test_bozuk_kayit_tipleri(tmp_path: Path) -> None:
    (tmp_path / "onbellek.json").write_text('{"kayitlar": {"k": {"kod": "x"}}}', encoding="utf-8")
    assert Onbellek(tmp_path).al("k") is None
    (tmp_path / "onbellek.json").write_text('{"kayitlar": 3}', encoding="utf-8")
    assert Onbellek(tmp_path)._kayitlar == {}


def test_yazilamayan_dizin(tmp_path: Path) -> None:
    engel = tmp_path / "engel"
    engel.write_text("dosya", encoding="utf-8")
    o = Onbellek(engel)
    o.koy("k", 200, b"v")
    o.kaydet()  # sessizce yutmalı
    assert o.yol.exists() is False


def test_varsayilan_dizin_env(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PYPI_PROVENANCE_GATE_CACHE", str(tmp_path / "ozel"))
    assert varsayilan_dizin() == tmp_path / "ozel"
    monkeypatch.delenv("PYPI_PROVENANCE_GATE_CACHE")
    yol = varsayilan_dizin()
    assert yol.name == "pypi-provenance-gate" or "pypi-provenance-gate" in str(yol)


def test_bayt_olmayan_govde(tmp_path: Path) -> None:
    o = Onbellek(tmp_path)
    o.koy("k", 200, b"\x00\xff binary")
    o.kaydet()
    kayit = Onbellek(tmp_path).al("k")
    assert kayit is not None
    assert kayit.govde == b"\x00\xff binary"


def test_surum_alani(tmp_path: Path) -> None:
    o = Onbellek(tmp_path)
    o.koy("k", 200, b"")
    o.kaydet()
    metin = (tmp_path / "onbellek.json").read_text(encoding="utf-8")
    assert '"surum": 1' in metin
    assert onbellek_mod._SURUM == 1
