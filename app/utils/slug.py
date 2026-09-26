import re
import unicodedata

_RESERVED = {"project", "secrets"}


def slugify(text: str, fallback: str = "collection") -> str:
    """Turn a display name into a safe, readable file stem (``Productos`` -> ``productos``)."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    slug = slug[:60].strip("-") or fallback
    if slug in _RESERVED:
        slug = f"{slug}-collection"
    return slug


def unique_slug(text: str, taken: set[str], fallback: str = "collection") -> str:
    base = slugify(text, fallback)
    candidate, counter = base, 2
    while candidate in taken:
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def unique_name(name: str, taken: set[str]) -> str:
    """``Crear producto`` -> ``Crear producto copy`` -> ``Crear producto copy 2``."""
    if name not in taken:
        return name
    candidate, counter = f"{name} copy", 2
    while candidate in taken:
        candidate = f"{name} copy {counter}"
        counter += 1
    return candidate
