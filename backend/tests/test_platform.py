import os

from fastapi.testclient import TestClient

from app.main import app


def test_case_lifecycle_and_duplicate_detection(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROOFMESH_DB_PATH", str(tmp_path / "proofmesh.db"))
    monkeypatch.setenv("PROOFMESH_EVIDENCE_DIR", str(tmp_path / "evidence"))
    client = TestClient(app)

    created = client.post("/api/v1/cases", json={"name": "Synthetic review", "category": "general"})
    assert created.status_code == 201
    case_id = created.json()["id"]

    upload = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": ("sample.pdf", b"%PDF-1.4 synthetic", "application/pdf")},
    )
    assert upload.status_code == 200
    duplicate = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files={"file": ("renamed.pdf", b"%PDF-1.4 synthetic", "application/pdf")},
    )
    assert duplicate.status_code == 409

    dashboard = client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["total_documents"] == 1
    assert client.get(f"/api/v1/cases/{case_id}/audit").json()
    assert client.get(f"/api/v1/cases/{case_id}/report").json()["report_id"]
    assert client.post(
        f"/api/v1/cases/{case_id}/assistant",
        json={"question": "How many documents are attached?"},
    ).json()["evidence"]["document_count"] == 1
