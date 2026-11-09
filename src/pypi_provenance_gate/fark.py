"""Compare the current lockfile state with a previous git revision."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .model import Durum, Gecis, OncekiDurum, PaketSonuc, ad_normallestir


class GitHatasi(RuntimeError):
    """git is missing, the revision does not exist, or the file is outside the repo."""


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitHatasi("git bulunamadı; --onceki için git gerekli") from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - çok yavaş disk
        raise GitHatasi("git komutu zaman aşımına uğradı") from exc


def repo_koku(yol: str | Path) -> Path:
    p = Path(yol).resolve()
    sonuc = _git(["rev-parse", "--show-toplevel"], p.parent)
    if sonuc.returncode != 0:
        raise GitHatasi(
            f"{p}: bir git deposu içinde değil "
            f"({sonuc.stderr.strip() or 'git rev-parse başarısız'})"
        )
    return Path(sonuc.stdout.strip())


def onceki_metin(rev: str, yol: str | Path) -> str:
    """Return the file content at ``rev`` (``git show rev:path``)."""
    p = Path(yol).resolve()
    kok = repo_koku(p)
    try:
        goreli = p.relative_to(kok).as_posix()
    except ValueError as exc:
        raise GitHatasi(f"{p}: git deposu kökü dışında") from exc
    sonuc = _git(["show", f"{rev}:{goreli}"], kok)
    if sonuc.returncode != 0:
        hata = sonuc.stderr.strip().splitlines()
        raise GitHatasi(
            f"'{rev}' içinde {goreli} okunamadı: {hata[-1] if hata else 'bilinmeyen git hatası'}"
        )
    return sonuc.stdout


def karsilastir(mevcut: list[PaketSonuc], onceki: list[PaketSonuc]) -> None:
    """Annotate current results with the previous state (in place).

    A package counts as a regression when it was attested before and is not
    fully attested now -- whether the version changed or the attestation of the
    same version disappeared.  Unknown results are *not* regressions.
    """
    indeks: dict[str, PaketSonuc] = {}
    for sonuc in onceki:
        indeks[ad_normallestir(sonuc.ad)] = sonuc

    for sonuc in mevcut:
        eski = indeks.get(ad_normallestir(sonuc.ad))
        if eski is None:
            continue
        sonuc.onceki = OncekiDurum(surum=eski.surum, durum=eski.durum, depolar=tuple(eski.depolar))
        if eski.durum is Durum.KANITLI:
            if sonuc.durum in (Durum.KANITSIZ, Durum.KISMI):
                sonuc.gecis = Gecis.GERILEDI
                sonuc.notlar.append(
                    f"önceki sürüm {eski.surum} kanıtlıydı, şimdi {_durum(sonuc.durum)}"
                )
            elif sonuc.durum is Durum.BILINMIYOR:
                sonuc.gecis = Gecis.YOK
                sonuc.notlar.append(
                    f"önceki sürüm {eski.surum} kanıtlıydı; şimdiki durum bilinmiyor "
                    "(geriye gidiş olarak sayılmadı)"
                )
            elif set(eski.depolar) != set(sonuc.depolar) and eski.depolar and sonuc.depolar:
                sonuc.gecis = Gecis.YAYINCI_DEGISTI
                sonuc.notlar.append(
                    "yayıncı deposu değişti: "
                    f"{', '.join(eski.depolar)} → {', '.join(sonuc.depolar)}"
                )
            else:
                sonuc.gecis = Gecis.DEGISMEDI
        elif sonuc.durum is Durum.KANITLI:
            sonuc.gecis = Gecis.IYILESME
        else:
            sonuc.gecis = Gecis.DEGISMEDI


def _durum(durum: Durum) -> str:
    return {
        Durum.KANITSIZ: "kanıtsız",
        Durum.KISMI: "kısmi kanıtlı",
        Durum.BILINMIYOR: "bilinmiyor",
        Durum.KANITLI: "kanıtlı",
        Durum.ATLANDI: "atlandı",
    }[durum]
