"""Lockfile readers: ``uv.lock``, ``requirements.txt``, ``poetry.lock``, ``pylock.toml``."""

from __future__ import annotations

from . import poetry, pylock, requirements, uv
from .ortak import KilitDosyasi, KilitHatasi

__all__ = ["KilitDosyasi", "KilitHatasi", "ayristir", "tur_belirle", "yukle"]


def tur_belirle(dosya_adi: str, metin: str) -> str:
    """Pick a parser from the filename, falling back to content sniffing."""
    ad = dosya_adi.lower().replace("\\", "/").rsplit("/", 1)[-1]
    if ad == "uv.lock":
        return "uv"
    if ad == "poetry.lock":
        return "poetry"
    if ad.endswith(".lock"):
        return "poetry"
    if ad == "pylock.toml" or ad.endswith(".pylock.toml"):
        return "pylock"
    if ad.endswith((".txt", ".in")) or ad.startswith("requirements"):
        if "[[package]]" in metin or "[[packages]]" in metin:
            return "pylock" if "[[packages]]" in metin else "poetry"
        return "requirements"
    # Bilinmeyen ad: içeriğe bak.
    if "[[packages]]" in metin:
        return "pylock"
    if "[[package]]" in metin:
        return "uv" if "wheels" in metin else "poetry"
    if "==" in metin:
        return "requirements"
    raise KilitHatasi(
        f"{dosya_adi}: kilit dosyası biçimi tanınmadı "
        "(uv.lock, poetry.lock, pylock.toml veya hash'li requirements.txt bekleniyor)"
    )


def ayristir(metin: str, dosya_adi: str, yol: str | None = None) -> KilitDosyasi:
    tur = tur_belirle(dosya_adi, metin)
    hedef = yol or dosya_adi
    if tur == "uv":
        return uv.ayristir(metin, dosya_adi, hedef)
    if tur == "poetry":
        return poetry.ayristir(metin, dosya_adi, hedef)
    if tur == "pylock":
        return pylock.ayristir(metin, dosya_adi, hedef)
    return requirements.ayristir(metin, dosya_adi, hedef)


def yukle(yol: str) -> KilitDosyasi:
    from .ortak import yukle as _yukle

    return _yukle(yol)
