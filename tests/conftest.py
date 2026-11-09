"""Shared test helpers: recorded responses, fake transport, fixture paths."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pypi_provenance_gate.integrity import Yanit

FIKSTUR = Path(__file__).parent / "fiksturler"

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64

SDIST = "example_attested-1.0.0.tar.gz"
WHEEL = "example_attested-1.0.0-py3-none-any.whl"
PLAIN_WHEEL = "example_plain-2.1.0-py3-none-any.whl"


def kanit_url(ad: str, surum: str, dosya: str) -> str:
    return f"https://pypi.org/integrity/{ad}/{surum}/{dosya}/provenance"


def json_url(ad: str, surum: str) -> str:
    return f"https://pypi.org/pypi/{ad}/{surum}/json"


def kanit_govdesi(depo: str = "example-org/example-project", adet: int = 1) -> bytes:
    return json.dumps(
        {
            "attestation_bundles": [
                {
                    "attestations": [{"version": 1}] * adet,
                    "publisher": {
                        "claims": None,
                        "environment": "",
                        "kind": "GitHub",
                        "repository": depo,
                        "workflow": "release.yml",
                    },
                }
            ],
            "version": 1,
        }
    ).encode()


def pypi_json_govdesi(
    ad: str,
    surum: str,
    dosyalar: list[tuple[str, str]],
) -> bytes:
    return json.dumps(
        {
            "info": {"name": ad, "version": surum},
            "urls": [
                {
                    "filename": dosya,
                    "digests": {"sha256": sha},
                    "url": f"https://files.pythonhosted.org/packages/aa/bb/{dosya}",
                }
                for dosya, sha in dosyalar
            ],
        }
    ).encode()


class SahteTasima:
    """Deterministic transport: maps URL to a response or an exception.

    Unknown ``/integrity/`` URLs answer 404 (PyPI's "no provenance" answer) and
    unknown ``/pypi/.../json`` URLs answer 404 as well, so tests only declare
    what matters for them.
    """

    def __init__(self, harita: dict[str, Any] | None = None) -> None:
        self.harita = harita or {}
        self.cagrilar: list[tuple[str, str | None]] = []

    def get(self, url: str, kabul: str | None = None) -> Yanit:
        self.cagrilar.append((url, kabul))
        deger = self.harita.get(url)
        if deger is None:
            return Yanit(kod=404, govde=b"")
        if isinstance(deger, Exception):
            raise deger
        if callable(deger):
            return deger(url)
        assert isinstance(deger, Yanit)
        return deger

    @property
    def integrity_cagrilari(self) -> list[str]:
        return [u for u, _ in self.cagrilar if "/integrity/" in u]


@pytest.fixture
def tasima() -> SahteTasima:
    return SahteTasima()


@pytest.fixture
def kanit_govde() -> bytes:
    return (FIKSTUR / "kanit_var.json").read_bytes()


def istemci_kur(tasima: SahteTasima, **kwargs: Any) -> Any:
    from pypi_provenance_gate.integrity import IntegrityIstemcisi

    kwargs.setdefault("uyku", lambda _s: None)
    return IntegrityIstemcisi(tasima=tasima, **kwargs)


Fabrika = Callable[..., Any]
