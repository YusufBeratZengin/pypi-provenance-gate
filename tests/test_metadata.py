"""Packaging metadata stays consistent with the files present in the repo."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _veri() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_readme_ve_lisans_dosyalari_var() -> None:
    veri = _veri()
    proje = veri["project"]
    assert (ROOT / proje["readme"]).is_file()
    for desen in proje.get("license-files", []):
        assert (ROOT / desen).is_file(), f"license-files: {desen} yok"


def test_sdist_dahil_edilen_dosyalar_var() -> None:
    veri = _veri()
    dahil = veri["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    for oge in dahil:
        yol = ROOT / oge
        assert yol.exists(), f"sdist include: {oge} yok"


def test_surum_tek_kaynakla_uyumlu() -> None:
    from pypi_provenance_gate.surum import SURUM

    assert _veri()["project"]["version"] == SURUM
