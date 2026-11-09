"""Small on-disk response cache for the Integrity API client.

The cache is deliberately dumb: URL -> (HTTP status, body) with a timestamp.
It exists so repeated CI runs and ``--offline`` mode do not hammer PyPI, and so
a previously observed "no provenance" (404) is remembered as well.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VARSAYILAN_TTL = 24 * 60 * 60  # 24 saat
_SURUM = 1


def varsayilan_dizin() -> Path:
    """Per-user cache directory (``XDG_CACHE_HOME`` respected)."""
    ozel = os.environ.get("PYPI_PROVENANCE_GATE_CACHE")
    if ozel:
        return Path(ozel)
    if os.name == "nt":
        taban = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(taban) / "pypi-provenance-gate" / "cache"
    taban = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(taban) / "pypi-provenance-gate"


@dataclass(frozen=True)
class OnbellekKaydi:
    kod: int
    govde: bytes
    zaman: float


class Onbellek:
    """JSON-file backed cache. Corrupt or unreadable files are treated as empty."""

    def __init__(
        self,
        dizin: str | Path | None = None,
        ttl: int = VARSAYILAN_TTL,
        simdi: Any = None,
    ) -> None:
        self.dizin = Path(dizin) if dizin is not None else varsayilan_dizin()
        self.ttl = ttl
        self._simdi = simdi or time.time
        self._kayitlar: dict[str, OnbellekKaydi] = {}
        self._kirli = False
        self._yukle()

    @property
    def yol(self) -> Path:
        return self.dizin / "onbellek.json"

    def _yukle(self) -> None:
        try:
            ham = self.yol.read_text(encoding="utf-8")
        except OSError:
            return
        try:
            veri = json.loads(ham)
            kayitlar = veri["kayitlar"]
            if not isinstance(kayitlar, dict):
                return
            for anahtar, deger in kayitlar.items():
                self._kayitlar[anahtar] = OnbellekKaydi(
                    kod=int(deger["kod"]),
                    govde=base64.b64decode(deger["govde"]),
                    zaman=float(deger["zaman"]),
                )
        except (ValueError, KeyError, TypeError, AttributeError):
            self._kayitlar = {}

    def al(self, anahtar: str) -> OnbellekKaydi | None:
        kayit = self._kayitlar.get(anahtar)
        if kayit is None:
            return None
        if self.ttl >= 0 and self._simdi() - kayit.zaman > self.ttl:
            del self._kayitlar[anahtar]
            self._kirli = True
            return None
        return kayit

    def koy(self, anahtar: str, kod: int, govde: bytes) -> None:
        self._kayitlar[anahtar] = OnbellekKaydi(kod=kod, govde=govde, zaman=self._simdi())
        self._kirli = True

    def kaydet(self) -> None:
        if not self._kirli:
            return
        veri = {
            "surum": _SURUM,
            "kayitlar": {
                k: {
                    "kod": v.kod,
                    "govde": base64.b64encode(v.govde).decode("ascii"),
                    "zaman": v.zaman,
                }
                for k, v in self._kayitlar.items()
            },
        }
        try:
            self.dizin.mkdir(parents=True, exist_ok=True)
            fd, gecici = tempfile.mkstemp(dir=str(self.dizin), prefix=".onbellek-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(veri, fh, ensure_ascii=False, sort_keys=True)
                os.replace(gecici, self.yol)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(gecici)
                raise
        except OSError:
            # Önbellek yazılamıyorsa çalışmayı durdurmayız; sadece kalıcı olmaz.
            return
        self._kirli = False
