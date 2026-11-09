"""Command line interface for pypi-provenance-gate.

Exit codes: 0 = no policy error, 1 = policy error, 2 = usage/lockfile/git error.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from . import fark, kilit
from . import rapor as rapor_mod
from .cekirdek import kontrol
from .integrity import IntegrityIstemcisi
from .model import Seviye
from .onbellek import VARSAYILAN_TTL, Onbellek
from .politika import (
    Politika,
    PolitikaHatasi,
    beklenen_yukle,
    cikis_kodu,
    degerlendir,
    izin_normallestir,
    varsayilan_ci,
)
from .politika import (
    yukle as politika_yukle,
)
from .surum import SURUM

_EPILOG = """examples:
  provenance-gate uv.lock
  provenance-gate requirements.txt --json
  provenance-gate uv.lock --onceki HEAD~1 --ci
  provenance-gate poetry.lock --politika politika.toml
"""


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="provenance-gate",
        description="Check PEP 740 provenance for every package in a lockfile.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "kilit", metavar="LOCKFILE", help="uv.lock | poetry.lock | pylock.toml | requirements.txt"
    )
    p.add_argument(
        "--surum", "--version", action="store_true", dest="surum", help="print version and exit"
    )
    p.add_argument("--json", action="store_true", help="machine-readable JSON on stdout")
    p.add_argument("--politika", metavar="PATH", help="policy file (politika.toml)")
    p.add_argument("--beklenen", metavar="PATH", help="expected publisher file (beklenen.toml)")
    p.add_argument("--onceki", metavar="REV", help="compare with this git revision, e.g. HEAD~1")
    p.add_argument("--ci", action="store_true", help="strict policy: any finding is an error")
    p.add_argument(
        "--izin",
        metavar="NAME",
        action="append",
        default=[],
        help="allow an unattested package (name or name==version); repeatable",
    )
    p.add_argument("--onbellek", metavar="DIR", help="cache directory (default: per-user cache)")
    p.add_argument("--onbellek-ttl", type=int, default=VARSAYILAN_TTL, metavar="SECONDS")
    p.add_argument("--onbellek-yok", action="store_true", help="disable the response cache")
    p.add_argument(
        "--cevrimdisi", "--offline", action="store_true", dest="cevrimdisi", help="use cache only"
    )
    p.add_argument(
        "--istek-limiti", type=int, default=500, metavar="N", help="max HTTP requests (default 500)"
    )
    p.add_argument(
        "--gecikme",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="minimum delay between requests",
    )
    p.add_argument("--zaman-asimi", type=float, default=15.0, metavar="SECONDS")
    p.add_argument(
        "--dosya-limiti", type=int, default=10, metavar="N", help="max release files per package"
    )
    p.add_argument("--renk", choices=("auto", "always", "never"), default="auto")
    return p


def _hata(mesaj: str) -> None:
    print(f"provenance-gate: error: {mesaj}", file=sys.stderr)


def _politika_olustur(args: argparse.Namespace) -> Politika | None:
    politika: Politika | None = None
    if args.ci:
        politika = varsayilan_ci()
    if args.politika:
        politika = politika_yukle(args.politika, temel=politika)
    if args.beklenen:
        beklenen = beklenen_yukle(args.beklenen)
        # Only the expected-publisher rule is enabled; this must not silently
        # turn into the strict --ci policy.
        if politika is None:
            seviyeler = dict.fromkeys(Politika().seviyeler, Seviye.YOKSAY)
            seviyeler["yayinci_uyumsuz"] = Seviye.HATA
            politika = Politika(seviyeler=seviyeler)
        politika = replace(politika, beklenen=beklenen)
    if args.izin:
        temel = politika or Politika()
        izin = {izin_normallestir(i) for i in args.izin if i.strip()}
        politika = replace(temel, kanitsiz_izin=temel.kanitsiz_izin | izin)
    return politika


def main(argv: list[str] | None = None) -> int:
    parser = _argparse()
    ham = list(sys.argv[1:] if argv is None else argv)
    # The positional LOCKFILE is required, so argparse would reject --version
    # before we could handle it. Check the flag before parsing.
    if "--surum" in ham or "--version" in ham:
        print(f"pypi-provenance-gate {SURUM}")
        return 0
    args = parser.parse_args(ham)
    if args.surum:  # pragma: no cover - normalde yukarıdaki ön kontrol yakalar
        print(f"pypi-provenance-gate {SURUM}")
        return 0

    try:
        kilit_dosyasi = kilit.yukle(args.kilit)
    except kilit.KilitHatasi as exc:
        _hata(str(exc))
        return 2

    onbellek = None
    if not args.onbellek_yok:
        onbellek = Onbellek(args.onbellek, ttl=args.onbellek_ttl)

    istemci = IntegrityIstemcisi(
        onbellek=onbellek,
        butce=max(0, args.istek_limiti),
        gecikme=args.gecikme,
        cevrimdisi=args.cevrimdisi,
        zaman_asimi=args.zaman_asimi,
    )

    try:
        sonuc = kontrol(
            kilit_dosyasi.paketler,
            istemci,
            kilit_dosyasi=kilit_dosyasi.yol,
            dosya_limiti=args.dosya_limiti,
        )
        sonuc.uyarilar.extend(kilit_dosyasi.uyarilar)

        if args.onceki:
            onceki_metin = fark.onceki_metin(args.onceki, args.kilit)
            onceki_kilit = kilit.ayristir(
                onceki_metin, Path(args.kilit).name, yol=f"{args.onceki}:{Path(args.kilit).name}"
            )
            onceki = kontrol(
                onceki_kilit.paketler,
                istemci,
                kilit_dosyasi=onceki_kilit.yol,
                dosya_limiti=args.dosya_limiti,
            )
            fark.karsilastir(sonuc.paketler, onceki.paketler)
            sonuc.onceki_rev = args.onceki

        politika = _politika_olustur(args)
        if politika is not None:
            degerlendir(sonuc, politika)
    except (fark.GitHatasi, PolitikaHatasi) as exc:
        _hata(str(exc))
        return 2
    finally:
        if onbellek is not None:
            onbellek.kaydet()

    sonuc.istek_sayisi = istemci.istek_sayisi
    uretim = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.json:
        print(rapor_mod.json_metni(sonuc, uretim))
    else:
        renk = {"auto": None, "always": True, "never": False}[args.renk]
        print(rapor_mod.metin(sonuc, renk=renk))

    return cikis_kodu(sonuc.ihlaller)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
