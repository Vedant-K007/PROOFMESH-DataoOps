"""Deterministic local classification and structured field extraction."""

from __future__ import annotations

import re
from pathlib import Path

import fitz
from PIL import Image

from app.services.platform import _extract_fields, document_path

try:
    import pytesseract
except ImportError:
    pytesseract = None


def _text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as document:
            return "\n".join(page.get_text() for page in document)
    if pytesseract is None:
        return ""
    with Image.open(path) as image:
        return pytesseract.image_to_string(image)


def classify_and_extract(case_id: str, document_id: str) -> dict:
    path = document_path(case_id, document_id)
    text = _text(path)
    lowered = text.lower()
    categories = [
        ("bank_statement", ("bank statement", "account number", "ifsc"), "Banking terms were observed."),
        ("invoice", ("invoice", "tax invoice", "invoice number"), "Invoice terms were observed."),
        ("identity_document", ("date of birth", "government", "identity"), "Identity-document terms were observed."),
        ("application_form", ("application", "applicant", "signature"), "Application terms were observed."),
        ("contract_or_agreement", ("agreement", "contract", "party"), "Agreement terms were observed."),
    ]
    for category, markers, explanation in categories:
        hits = sum(marker in lowered for marker in markers)
        if hits:
            return {
                "document_id": document_id,
                "classification": category,
                "confidence": round(min(0.95, 0.55 + hits * 0.12), 2),
                "explanation": explanation,
                "extraction_method": "PyMuPDF text" if path.suffix.lower() == ".pdf" else "Tesseract OCR",
                "fields": [
                    {"name": name, "value": value, "confidence": 0.8, "page": 1, "verification_status": "unverified"}
                    for name, values in _extract_fields(text).items()
                    for value in values
                ],
            }
    return {
        "document_id": document_id,
        "classification": "other",
        "confidence": 0.35 if text else 0,
        "explanation": "No supported document-category markers were observed.",
        "extraction_method": "PyMuPDF text" if path.suffix.lower() == ".pdf" else "Tesseract OCR",
        "fields": [],
    }
