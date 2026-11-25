"""
Regression tests for M1: upload extension allowlist + magic-byte validation.
"""
import pytest

from app.services.upload_validation import validate_upload, UploadValidationError

PNG = b"\x89PNG\r\n\x1a\n\x00\x00extra-bytes"
PDF = b"%PDF-1.4\n% binary-ish comment"
GIF = b"GIF89a\x01\x02\x03"
ZIP = b"PK\x03\x04\x14\x00ok"
WEBP = b"RIFF\x00\x00\x00\x00WEBP"
PE = b"MZ\x90\x00\x03\x00\x00\x00"  # Windows .exe boot sector


def test_accepts_valid_png():
    assert validate_upload("logo.png", PNG) is None


def test_accepts_valid_pdf_gif_zip_webp():
    assert validate_upload("a.pdf", PDF) is None
    assert validate_upload("a.gif", GIF) is None
    assert validate_upload("a.docx", ZIP) is None
    assert validate_upload("a.webp", WEBP) is None


def test_rejects_disallowed_extension():
    with pytest.raises(UploadValidationError):
        validate_upload("shell.exe", PE)


def test_rejects_renamed_executable_as_png():
    # A PE binary masquerading as .png must fail the magic-byte check.
    with pytest.raises(UploadValidationError):
        validate_upload("evil.png", PE)


def test_rejects_empty_file():
    with pytest.raises(UploadValidationError):
        validate_upload("empty.txt", b"")


def test_rejects_binary_content_in_text_extension():
    # .txt must be text; a NUL-bearing blob is rejected.
    with pytest.raises(UploadValidationError):
        validate_upload("notes.txt", b"hello\x00world\x00")


def test_rejects_missing_filename():
    with pytest.raises(UploadValidationError):
        validate_upload("", PNG)
