"""Persistent case management and contextual comparison for the local platform."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
import fitz
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

from app.services.evidence_storage import (
    ALLOWED_FILE_TYPES,
    CHUNK_SIZE_BYTES,
    MAX_FILE_SIZE_BYTES,
    evidence_directory,
)

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "proofmesh.db"


def _db_path() -> Path:
    return Path(os.environ.get("PROOFMESH_DB_PATH", str(DEFAULT_DB)))


@contextmanager
def _connect():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, case_reference TEXT,
                description TEXT, category TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL, filename TEXT NOT NULL,
                stored_name TEXT NOT NULL, file_type TEXT NOT NULL, file_size INTEGER NOT NULL,
                sha256 TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(investigation_id, sha256),
                FOREIGN KEY(investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id TEXT NOT NULL,
                action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS custody_events (
                id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL, document_id TEXT NOT NULL,
                event_type TEXT NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL, document_id TEXT,
                analysis_type TEXT NOT NULL, engine TEXT NOT NULL, engine_version TEXT NOT NULL,
                configuration TEXT NOT NULL, input_sha256 TEXT, outcome TEXT NOT NULL,
                warnings TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT NOT NULL,
                FOREIGN KEY(investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS finding_reviews (
                id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL, finding_id TEXT NOT NULL,
                decision TEXT NOT NULL, comment TEXT, reviewer TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
            );
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(connection: sqlite3.Connection, investigation_id: str, action: str, details: Any) -> None:
    connection.execute(
        "INSERT INTO audit_log (investigation_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (investigation_id, action, json.dumps(details, default=str), _now()),
    )


def create_case(name: str, case_reference: str | None, description: str | None, category: str) -> dict[str, Any]:
    init_db()
    case_id = str(uuid4())
    timestamp = _now()
    with _connect() as connection:
        connection.execute(
            "INSERT INTO investigations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (case_id, name.strip(), case_reference, description, category, "created", timestamp, timestamp),
        )
        _audit(connection, case_id, "investigation.created", {"name": name, "category": category})
    return get_case(case_id)


def get_case(case_id: str) -> dict[str, Any]:
    init_db()
    with _connect() as connection:
        case = connection.execute("SELECT * FROM investigations WHERE id = ?", (case_id,)).fetchone()
        if case is None:
            raise HTTPException(status_code=404, detail="Investigation not found.")
        documents = connection.execute(
            "SELECT id, filename, file_type, file_size, sha256, status, created_at FROM documents WHERE investigation_id = ? ORDER BY created_at",
            (case_id,),
        ).fetchall()
    result = dict(case)
    result["documents"] = [dict(document) for document in documents]
    return result


def list_cases() -> dict[str, Any]:
    init_db()
    with _connect() as connection:
        cases = connection.execute(
            "SELECT i.*, COUNT(d.id) AS document_count FROM investigations i LEFT JOIN documents d ON d.investigation_id = i.id GROUP BY i.id ORDER BY i.updated_at DESC"
        ).fetchall()
    rows = [dict(case) for case in cases]
    return {
        "total_investigations": len(rows),
        "total_documents": sum(row["document_count"] for row in rows),
        "pending_investigations": sum(row["status"] in {"created", "processing"} for row in rows),
        "completed_investigations": sum(row["status"] == "complete" for row in rows),
        "investigations": rows,
    }


def _safe_name(filename: str) -> tuple[str, str]:
    original = filename or ""
    extension = Path(original).suffix.lower()
    file_type = ALLOWED_FILE_TYPES.get(extension)
    if not file_type:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only PNG, JPG, JPEG, and PDF files are supported.")
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(original).name), file_type


async def add_document(case_id: str, file: UploadFile) -> dict[str, Any]:
    init_db()
    case = get_case(case_id)
    safe_name, file_type = _safe_name(file.filename or "")
    document_id = str(uuid4())
    case_dir = evidence_directory() / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{document_id}_{safe_name}"
    temporary = case_dir / f".{stored_name}.uploading"
    destination = case_dir / stored_name
    size = 0
    digest = hashlib.sha256()
    try:
        with temporary.open("wb") as target:
            while chunk := await file.read(CHUNK_SIZE_BYTES):
                size += len(chunk)
                if size > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="Files must not exceed 50 MB.")
                digest.update(chunk)
                target.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        digest_value = digest.hexdigest()
        with _connect() as connection:
            duplicate = connection.execute(
                "SELECT id FROM documents WHERE investigation_id = ? AND sha256 = ?", (case_id, digest_value)
            ).fetchone()
            if duplicate:
                raise HTTPException(status_code=409, detail="This evidence is already attached to the investigation.")
            temporary.replace(destination)
            timestamp = _now()
            connection.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (document_id, case_id, file.filename or safe_name, stored_name, file_type, size, digest_value, "uploaded", timestamp),
            )
            connection.execute("UPDATE investigations SET status = 'processing', updated_at = ? WHERE id = ?", (timestamp, case_id))
            _audit(connection, case_id, "document.uploaded", {"document_id": document_id, "filename": file.filename, "sha256": digest_value})
            connection.execute(
                "INSERT INTO custody_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid4()), case_id, document_id, "acquired", "local-user", json.dumps({
                    "original_filename": file.filename or safe_name,
                    "mime_type": file_type,
                    "size": size,
                    "sha256": digest_value,
                    "acquisition_method": "multipart upload",
                }), timestamp),
            )
        return get_case(case_id)["documents"][-1]
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


def document_path(case_id: str, document_id: str) -> Path:
    init_db()
    with _connect() as connection:
        row = connection.execute("SELECT stored_name FROM documents WHERE id = ? AND investigation_id = ?", (document_id, case_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = evidence_directory() / case_id / row["stored_name"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored evidence is unavailable.")
    return path


def audit_entries(case_id: str) -> list[dict[str, Any]]:
    get_case(case_id)
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM audit_log WHERE investigation_id = ? ORDER BY created_at DESC", (case_id,)).fetchall()
    return [{**dict(row), "details": json.loads(row["details"])} for row in rows]


def custody_entries(case_id: str, document_id: str | None = None) -> list[dict[str, Any]]:
    get_case(case_id)
    with _connect() as connection:
        query = "SELECT * FROM custody_events WHERE investigation_id = ?"
        parameters: list[str] = [case_id]
        if document_id:
            query += " AND document_id = ?"
            parameters.append(document_id)
        query += " ORDER BY created_at DESC"
        rows = connection.execute(query, parameters).fetchall()
    return [{**dict(row), "details": json.loads(row["details"])} for row in rows]


def record_analysis(
    case_id: str,
    analysis_type: str,
    *,
    document_id: str | None = None,
    input_sha256: str | None = None,
    outcome: str = "completed",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    get_case(case_id)
    timestamp = _now()
    run = {
        "id": str(uuid4()),
        "investigation_id": case_id,
        "document_id": document_id,
        "analysis_type": analysis_type,
        "engine": "ProofMesh forensic pipeline",
        "engine_version": "0.1.0",
        "configuration": {"python": "runtime", "method": "deterministic local heuristics"},
        "input_sha256": input_sha256,
        "outcome": outcome,
        "warnings": warnings or [],
        "started_at": timestamp,
        "completed_at": timestamp,
    }
    with _connect() as connection:
        connection.execute(
            "INSERT INTO analysis_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run["id"], case_id, document_id, analysis_type, run["engine"], run["engine_version"],
             json.dumps(run["configuration"]), input_sha256, outcome, json.dumps(run["warnings"]),
             timestamp, timestamp),
        )
        _audit(connection, case_id, "analysis.completed", {"analysis_id": run["id"], "type": analysis_type, "outcome": outcome})
    return run


def methodology_entries(case_id: str) -> list[dict[str, Any]]:
    get_case(case_id)
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM analysis_runs WHERE investigation_id = ? ORDER BY completed_at DESC", (case_id,)).fetchall()
    return [
        {**dict(row), "configuration": json.loads(row["configuration"]), "warnings": json.loads(row["warnings"])}
        for row in rows
    ]


def standards_mapping() -> list[dict[str, str]]:
    return [
        {"framework": "ISO/IEC 27037", "requirement": "Identify, acquire and preserve digital evidence", "control": "SHA-256 evidence IDs, immutable original storage, acquisition custody events", "status": "Partially implemented", "verification": "Upload and custody API tests", "gap": "Production encryption and independent assessment"},
        {"framework": "ISO/IEC 27041", "requirement": "Assure investigative method validity", "control": "Persisted engine/version/configuration/input hash analysis runs", "status": "Implemented", "verification": "Methodology API and integration tests", "gap": "External validation dataset"},
        {"framework": "ISO/IEC 27042", "requirement": "Traceable analysis and interpretation", "control": "Confidence-bearing heuristic findings with limitations and source references", "status": "Partially implemented", "verification": "Forensic response schemas and UI disclaimers", "gap": "Investigator approval workflow"},
        {"framework": "NIST SP 800-86", "requirement": "Collection, examination, analysis, reporting", "control": "Case workflow, forensic pipeline, audit trail and JSON dossier", "status": "Partially implemented", "verification": "End-to-end case tests", "gap": "Formal evidence export package"},
        {"framework": "OWASP ML Security", "requirement": "Protect untrusted document and AI processing", "control": "No external LLM by default; local grounded assistant; strict file validation", "status": "Partially implemented", "verification": "Upload validation and grounded assistant tests", "gap": "Malware scanner and production auth"},
    ]


def verify_document_integrity(case_id: str, document_id: str) -> dict[str, Any]:
    path = document_path(case_id, document_id)
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, filename, sha256, file_size, created_at FROM documents WHERE id = ? AND investigation_id = ?",
            (document_id, case_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    verified = hmac_compare(digest, row["sha256"])
    with _connect() as connection:
        _audit(connection, case_id, "evidence.integrity_verified", {"document_id": document_id, "verified": verified})
    return {
        "document_id": document_id,
        "filename": row["filename"],
        "stored_sha256": row["sha256"],
        "computed_sha256": digest,
        "verified": verified,
        "checked_at": _now(),
    }


def hmac_compare(left: str, right: str) -> bool:
    return hashlib.sha256(left.encode()).digest() == hashlib.sha256(right.encode()).digest()


def document_dna(case_id: str, document_id: str) -> dict[str, Any]:
    path = document_path(case_id, document_id)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return {
        "document_id": document_id,
        "sha256": digest,
        "size": len(data),
        "extension": path.suffix.lower(),
        "dna": {
            "prefix": digest[:16],
            "suffix": digest[-16:],
            "byte_entropy_sample": round(len(set(data[:4096])) / 256, 4) if data else 0,
        },
        "experimental": True,
        "limitation": "This DNA is a deterministic integrity fingerprint, not a semantic identity model.",
    }


def timeline_entries(case_id: str) -> list[dict[str, Any]]:
    get_case(case_id)
    with _connect() as connection:
        audit = connection.execute("SELECT action, details, created_at FROM audit_log WHERE investigation_id = ?", (case_id,)).fetchall()
        custody = connection.execute("SELECT event_type AS action, details, created_at FROM custody_events WHERE investigation_id = ?", (case_id,)).fetchall()
        analysis = connection.execute("SELECT analysis_type AS action, warnings AS details, completed_at AS created_at FROM analysis_runs WHERE investigation_id = ?", (case_id,)).fetchall()
    events = []
    for row in [*audit, *custody, *analysis]:
        details = row["details"]
        events.append({"action": row["action"], "details": json.loads(details), "created_at": row["created_at"]})
    return sorted(events, key=lambda event: event["created_at"])


def semantic_search(case_id: str, query: str) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    terms = {term.lower() for term in re.findall(r"\w+", query) if len(term) > 2}
    results = []
    for document in get_case(case_id)["documents"]:
        text = _document_text(document_path(case_id, document["id"]))
        lowered = text.lower()
        hits = sorted(term for term in terms if term in lowered)
        if hits:
            results.append({"document_id": document["id"], "filename": document["filename"], "matched_terms": hits, "score": round(len(hits) / max(1, len(terms)), 3), "snippet": text[:240].replace("\n", " ")})
    return sorted(results, key=lambda result: result["score"], reverse=True)


def entity_graph(case_id: str) -> dict[str, Any]:
    case = get_case(case_id)
    nodes = []
    edges = []
    for document in case["documents"]:
        text = _document_text(document_path(case_id, document["id"]))
        entities = []
        for label, pattern in {
            "account": r"\b\d{8,}\b",
            "date": r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
            "amount": r"\b(?:INR|USD|₹|\$)\s?[\d,]+(?:\.\d+)?\b",
        }.items():
            entities.extend((label, value) for value in re.findall(pattern, text, flags=re.IGNORECASE))
        document_node = f"document:{document['id']}"
        nodes.append({"id": document_node, "type": "document", "label": document["filename"], "evidence_reference": document["id"]})
        for label, value in sorted(set(entities)):
            entity_id = f"{label}:{value.lower()}"
            nodes.append({"id": entity_id, "type": label, "label": value, "evidence_reference": document["id"]})
            edges.append({"source": document_node, "target": entity_id, "relationship": "derived_from"})
    unique_nodes = {node["id"]: node for node in nodes}
    return {"investigation_id": case_id, "nodes": list(unique_nodes.values()), "edges": edges}


def missing_evidence(case_id: str) -> dict[str, Any]:
    case = get_case(case_id)
    names = {document["filename"].lower() for document in case["documents"]}
    suggestions = []
    if len(case["documents"]) < 2:
        suggestions.append({"requirement": "related document", "reason": "Cross-document consistency cannot be assessed with one document."})
    if not any("identity" in name for name in names):
        suggestions.append({"requirement": "identity evidence", "reason": "No filename indicates identity evidence; confirm whether it is required for this case."})
    if not any("bank" in name or "statement" in name for name in names):
        suggestions.append({"requirement": "financial evidence", "reason": "No filename indicates a statement; confirm whether financial verification is required."})
    return {"investigation_id": case_id, "gaps": suggestions}


def review_finding(case_id: str, finding_id: str, decision: str, comment: str | None, reviewer: str = "local-user") -> dict[str, Any]:
    if decision not in {"accepted", "rejected", "flagged"}:
        raise HTTPException(status_code=422, detail="Decision must be accepted, rejected, or flagged.")
    get_case(case_id)
    review = {"id": str(uuid4()), "investigation_id": case_id, "finding_id": finding_id, "decision": decision, "comment": comment, "reviewer": reviewer, "created_at": _now()}
    with _connect() as connection:
        connection.execute("INSERT INTO finding_reviews VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(review.values()))
        _audit(connection, case_id, "finding.reviewed", review)
    return review


def reviews(case_id: str) -> list[dict[str, Any]]:
    get_case(case_id)
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM finding_reviews WHERE investigation_id = ? ORDER BY created_at DESC", (case_id,)).fetchall()
    return [dict(row) for row in rows]


def delete_case(case_id: str) -> None:
    case = get_case(case_id)
    with _connect() as connection:
        connection.execute("DELETE FROM investigations WHERE id = ?", (case_id,))
    case_dir = evidence_directory() / case_id
    for path in case_dir.iterdir() if case_dir.is_dir() else []:
        path.unlink()
    if case_dir.is_dir():
        case_dir.rmdir()


def _document_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as document:
            return "\n".join(page.get_text() for page in document)
    if pytesseract is None:
        return ""
    with Image.open(path) as image:
        return pytesseract.image_to_string(image)


def _extract_fields(text: str) -> dict[str, list[str]]:
    patterns = {
        "dates": r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
        "amounts": r"(?:₹|\$|USD|INR)\s?[0-9][0-9,]*(?:\.[0-9]{1,2})?",
        "account_numbers": r"\b(?:account|a/c|acct)[\s:#-]*([0-9][0-9 -]{5,})",
        "invoice_numbers": r"\b(?:invoice|inv)[\s:#-]*([A-Z0-9-]{3,})",
    }
    return {
        field: sorted({match.strip(" -:") for match in re.findall(pattern, text, flags=re.IGNORECASE)})
        for field, pattern in patterns.items()
    }


def compare_fields(case_id: str) -> dict[str, Any]:
    case = get_case(case_id)
    documents = case["documents"]
    extracted = []
    for document in documents:
        text = _document_text(document_path(case_id, document["id"]))
        extracted.append({"document": document["filename"], "fields": _extract_fields(text)})
    comparisons: list[dict[str, Any]] = []
    for left_index, left in enumerate(documents):
        for right in documents[left_index + 1:]:
            left_fields = extracted[left_index]["fields"]
            right_index = documents.index(right)
            right_fields = extracted[right_index]["fields"]
            matches = []
            conflicts = []
            for field in sorted(set(left_fields) | set(right_fields)):
                shared = sorted(set(left_fields.get(field, [])) & set(right_fields.get(field, [])))
                left_only = sorted(set(left_fields.get(field, [])) - set(right_fields.get(field, [])))
                right_only = sorted(set(right_fields.get(field, [])) - set(left_fields.get(field, [])))
                if shared:
                    matches.append({"field": field, "values": shared})
                elif left_only and right_only:
                    conflicts.append({"field": field, "left": left_only, "right": right_only})
            comparisons.append({
                "left_document": left["filename"],
                "right_document": right["filename"],
                "status": "conflict" if conflicts else "consistent" if matches else "insufficient_evidence",
                "matches": matches,
                "conflicts": conflicts,
                "explanation": (
                    "Extracted values conflict and require human review."
                    if conflicts else "Extracted values are consistent for the fields observed."
                    if matches else "No comparable structured fields were extracted."
                ),
            })
    return {"investigation_id": case_id, "documents": documents, "extracted_fields": extracted, "comparisons": comparisons}


def build_report(case_id: str) -> dict[str, Any]:
    case = get_case(case_id)
    report = {
        "report_id": str(uuid4()),
        "generated_at": _now(),
        "investigation": case,
        "audit": audit_entries(case_id),
        "limitations": [
            "Forensic signals are heuristic observations and are not proof of fraud.",
            "OCR and contextual comparisons require human verification against the original evidence.",
        ],
    }
    with _connect() as connection:
        _audit(connection, case_id, "report.generated", {"report_id": report["report_id"]})
    return report


def build_pdf_report(case_id: str) -> bytes:
    """Create a portable dossier from persisted case, custody, and audit facts."""
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    report = build_report(case_id)
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("ProofMesh Investigation Dossier", styles["Title"]),
        Paragraph(f"Report ID: {report['report_id']}", styles["Normal"]),
        Paragraph(f"Generated: {report['generated_at']}", styles["Normal"]),
        Spacer(1, 10),
        Paragraph(f"Case: {report['investigation']['name']}", styles["Heading2"]),
        Paragraph(f"Category: {report['investigation']['category']}", styles["Normal"]),
        Paragraph("This report presents traceable technical observations for human review. It is not a determination of fraud.", styles["BodyText"]),
        Spacer(1, 10),
    ]
    rows = [["Document", "Type", "Size", "SHA-256", "Status"]]
    for document_record in report["investigation"]["documents"]:
        rows.append([
            document_record["filename"],
            document_record["file_type"],
            str(document_record["file_size"]),
            document_record["sha256"],
            document_record["status"],
        ])
    table = Table(rows, repeatRows=1, colWidths=[35 * mm, 28 * mm, 16 * mm, 72 * mm, 20 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17253B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.extend([table, Spacer(1, 12), Paragraph("Limitations", styles["Heading2"])])
    story.extend(Paragraph(f"• {limitation}", styles["BodyText"]) for limitation in report["limitations"])
    story.extend([Spacer(1, 12), Paragraph("Audit activity", styles["Heading2"])])
    story.append(Paragraph(f"{len(report['audit'])} persisted audit event(s) are available through the API.", styles["BodyText"]))
    document.build(story)
    return buffer.getvalue()


def answer_assistant(case_id: str, question: str, language: str = "en") -> dict[str, Any]:
    case = get_case(case_id)
    audit = audit_entries(case_id)
    normalized = question.lower()
    if "how many" in normalized and "document" in normalized:
        answer = f"This investigation contains {len(case['documents'])} attached document(s)."
    elif "audit" in normalized or "activity" in normalized:
        answer = f"The audit trail contains {len(audit)} recorded event(s)."
    elif "compare" in normalized or "mismatch" in normalized or "conflict" in normalized:
        comparison = compare_fields(case_id)
        conflicts = [item for item in comparison["comparisons"] if item["status"] == "conflict"]
        answer = f"{len(conflicts)} document pair(s) have extracted field conflicts." if conflicts else "No extracted field conflicts were found; insufficient evidence may still limit comparison."
    else:
        answer = "I can answer questions about attached document counts, audit activity, and extracted cross-document conflicts. The response is limited to evidence currently available in this case."
    if language == "hi":
        answer = f"जांच में {len(case['documents'])} दस्तावेज़ जुड़े हैं।" if "document" in normalized else f"यह स्थानीय साक्ष्य-आधारित उत्तर है: {answer}"
    elif language == "mr":
        answer = f"तपासणीमध्ये {len(case['documents'])} दस्तऐवज जोडले आहेत." if "document" in normalized else f"हा स्थानिक पुराव्यावर आधारित उत्तर आहे: {answer}"
    return {"investigation_id": case_id, "question": question, "language": language, "answer": answer, "evidence": {"document_count": len(case["documents"]), "audit_events": len(audit)}}
