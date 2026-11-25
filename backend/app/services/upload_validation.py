"""
M1 fix: upload input validation.

Validates client file uploads against an allowlist of extensions and verifies
the on-disk *content* via magic-byte signatures, so a renamed executable
(e.g. ``shell.exe`` renamed to ``shell.png``) is rejected even when the client
lies about its content type. Client-supplied ``content_type`` is treated as
untrusted; magic bytes are authoritative.
"""
import os
from typing import Iterable, List


class UploadValidationError(ValueError):
    """Raised when an uploaded file fails validation."""


# Extensions we are willing to store. Everything else is rejected outright.
ALLOWED_EXTENSIONS = {
    # images
    "png", "jpg", "jpeg", "gif", "bmp", "webp",
    # documents
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip",
    # plain text / data
    "txt", "csv", "json", "xml",
}

# Extensions whose content must be decodable text (not binary).
TEXT_EXTENSIONS = {"txt", "csv", "json", "xml"}

# Expected leading bytes per extension. ``None`` entries mean "no magic check"
# (handled by TEXT_EXTENSIONS or a generic fallback).
_MAGIC: dict[str, List[bytes]] = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "gif": [b"GIF87a", b"GIF89a"],
    "bmp": [b"BM"],
    "pdf": [b"%PDF-"],
    "zip": [b"PK\x03\x04"],
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "ppt": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "docx": [b"PK\x03\x04"],
    "xlsx": [b"PK\x03\x04"],
    "pptx": [b"PK\x03\x04"],
}


def _matches_magic(content: bytes, ext: str) -> bool:
    """Return True if *content* begins with an expected signature for *ext*."""
    # webp: RIFF....WEBP — the "WEBP" type tag sits at offset 8 (a 4-byte file-size
    # field sits between RIFF and WEBP), so it cannot be expressed as a single
    # startswith prefix. Check it explicitly *before* the generic path; this is the
    # branch that was previously unreachable dead code (findings #17).
    if ext == "webp":
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    sigs = _MAGIC.get(ext)
    if not sigs:
        return True  # no magic requirement (e.g. text extensions, checked elsewhere)
    return any(content.startswith(sig) for sig in sigs)


def _is_text(content: bytes) -> bool:
    """Heuristic: decodes as UTF-8 without a NUL byte early on."""
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    return "\x00" not in text


def validate_upload(filename: str, content: bytes) -> None:
    """Validate an uploaded file's type and content.

    Raises :class:`UploadValidationError` (a ``ValueError`` subclass) when the
    file is empty, has a disallowed extension, or its bytes do not match the
    expected format for that extension.
    """
    if not filename:
        raise UploadValidationError("Missing filename")
    if not content:
        raise UploadValidationError("Uploaded file is empty")

    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(f"File type '.{ext}' is not allowed")

    if not _matches_magic(content, ext):
        raise UploadValidationError(
            f"File content does not match the '{ext or 'unknown'}' format "
            "(possible renamed/misdeclared file)"
        )

    if ext in TEXT_EXTENSIONS and not _is_text(content):
        raise UploadValidationError(f".{ext} files must be valid text")
