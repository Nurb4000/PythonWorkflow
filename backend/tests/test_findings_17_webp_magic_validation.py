"""
Regression test for findings #17 (.webp uploads bypassed magic-byte validation).

`_MAGIC` had no "webp" key, so `_matches_magic` returned True at the
`if not sigs: return True` early-out *before* the webp RIFF/WEBP check — making
that check unreachable dead code. A `.webp` containing arbitrary bytes (e.g. a
Windows PE / `MZ` header) was therefore accepted.

Fix: make the webp branch reachable so RIFF....WEBP is actually verified.

Asserts both halves: a non-RIFF .webp is rejected, a valid RIFF/WEBP .webp passes.
"""
import pytest

from app.services.upload_validation import validate_upload, UploadValidationError


# A valid RIFF....WEBP header: "RIFF" + 4-byte size + "WEBP" + chunk data.
VALID_WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 \x10\x77\xbf\x60"


def test_non_riff_webp_is_rejected():
    # A Windows PE binary (MZ header) masquerading as .webp must be rejected.
    bad = b"MZ\x90\x00" + b"A" * 200
    with pytest.raises(UploadValidationError):
        validate_upload("photo.webp", bad)


def test_empty_garbage_webp_is_rejected():
    with pytest.raises(UploadValidationError):
        validate_upload("photo.webp", b"not a real webp file at all")


def test_missing_webp_tag_is_rejected():
    # Has RIFF but no WEBP tag at offset 8.
    no_tag = b"RIFF" + b"\x24\x00\x00\x00" + b"???? " + b"data"
    with pytest.raises(UploadValidationError):
        validate_upload("photo.webp", no_tag)


def test_valid_riff_webp_is_accepted():
    validate_upload("photo.webp", VALID_WEBP)


def test_short_content_webp_is_rejected():
    # Fewer than 12 bytes cannot contain a full RIFF....WEBP header.
    with pytest.raises(UploadValidationError):
        validate_upload("photo.webp", b"RIF")
