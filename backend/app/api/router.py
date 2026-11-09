from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.models.health import HealthResponse
from app.models.auth import LoginRequest, RegisterRequest
from app.models.platform import DashboardResponse, InvestigationCreate, InvestigationRecord
from app.models.investigation import (
    CopyMoveAnalysisResponse,
    DocumentForensicsResponse,
    EvidenceFusionResponse,
    EvidenceGraphResponse,
    ImageForensicsResponse,
    InvestigationResponse,
    MetadataAnalysisResponse,
    OCRAnalysisResponse,
)
from app.services.copy_move_detection import analyze_copy_move
from app.services.document_forensics import analyze_document_forensics
from app.services.evidence_storage import investigation_file, store_evidence
from app.services.evidence_fusion import analyze_evidence_fusion
from app.services.evidence_graph import build_evidence_graph
from app.services.image_forensics import analyze_image_forensics
from app.services.metadata_analysis import analyze_metadata
from app.services.ocr import analyze_ocr
from app.services.platform import (
    add_document,
    audit_entries,
    build_report,
    build_pdf_report,
    compare_fields,
    create_case,
    delete_case,
    document_path,
    get_case,
    list_cases,
    answer_assistant,
    custody_entries,
    methodology_entries,
    record_analysis,
    standards_mapping,
    verify_document_integrity,
    document_dna,
    timeline_entries,
    semantic_search,
    entity_graph,
    missing_evidence,
    review_finding,
    reviews,
)
from app.services.demo import create_demo_case
from app.services.document_intelligence import classify_and_extract
from app.services.security import login_user, register_user


api_router = APIRouter()


@api_router.post("/api/v1/auth/register", status_code=201, tags=["auth"])
def register(payload: RegisterRequest) -> dict:
    return register_user(**payload.model_dump())


@api_router.post("/api/v1/auth/login", tags=["auth"])
def login(payload: LoginRequest) -> dict:
    return login_user(**payload.model_dump())


@api_router.post("/api/v1/demo", status_code=201, tags=["platform"])
async def load_demo() -> dict:
    return await create_demo_case()


def _record_if_case(investigation_id: str, analysis_type: str) -> None:
    try:
        record_analysis(investigation_id, analysis_type)
    except HTTPException as error:
        if error.status_code != status.HTTP_404_NOT_FOUND:
            raise


@api_router.get("/api/v1/dashboard", response_model=DashboardResponse, tags=["platform"])
def dashboard() -> DashboardResponse:
    return DashboardResponse(**list_cases())


@api_router.post("/api/v1/cases", response_model=InvestigationRecord, status_code=201, tags=["platform"])
def create_case_route(payload: InvestigationCreate) -> InvestigationRecord:
    return InvestigationRecord(**create_case(**payload.model_dump()))


@api_router.get("/api/v1/cases/{case_id}", response_model=InvestigationRecord, tags=["platform"])
def get_case_route(case_id: str) -> InvestigationRecord:
    return InvestigationRecord(**get_case(case_id))


@api_router.post("/api/v1/cases/{case_id}/documents", tags=["platform"])
async def add_case_document(case_id: str, file: UploadFile = File(...)) -> dict:
    return await add_document(case_id, file)


@api_router.get("/api/v1/cases/{case_id}/documents/{document_id}", tags=["platform"])
def download_case_document(case_id: str, document_id: str) -> FileResponse:
    path = document_path(case_id, document_id)
    return FileResponse(path, filename=path.name.split("_", 1)[-1])


@api_router.post("/api/v1/cases/{case_id}/documents/{document_id}/intelligence", tags=["platform"])
def analyze_document_intelligence(case_id: str, document_id: str) -> dict:
    return classify_and_extract(case_id, document_id)


@api_router.get("/api/v1/cases/{case_id}/documents/{document_id}/integrity", tags=["platform"])
def verify_case_document(case_id: str, document_id: str) -> dict:
    return verify_document_integrity(case_id, document_id)


@api_router.get("/api/v1/cases/{case_id}/documents/{document_id}/dna", tags=["platform"])
def get_document_dna(case_id: str, document_id: str) -> dict:
    return document_dna(case_id, document_id)


@api_router.get("/api/v1/cases/{case_id}/compare", tags=["platform"])
def compare_case_documents(case_id: str) -> dict:
    return compare_fields(case_id)


@api_router.get("/api/v1/cases/{case_id}/audit", tags=["platform"])
def get_case_audit(case_id: str) -> list[dict]:
    return audit_entries(case_id)


@api_router.get("/api/v1/cases/{case_id}/timeline", tags=["platform"])
def get_case_timeline(case_id: str) -> list[dict]:
    return timeline_entries(case_id)


@api_router.get("/api/v1/cases/{case_id}/search", tags=["platform"])
def search_case(case_id: str, q: str) -> list[dict]:
    return semantic_search(case_id, q)


@api_router.get("/api/v1/cases/{case_id}/entities", tags=["platform"])
def get_case_entities(case_id: str) -> dict:
    return entity_graph(case_id)


@api_router.get("/api/v1/cases/{case_id}/gaps", tags=["platform"])
def get_case_gaps(case_id: str) -> dict:
    return missing_evidence(case_id)


@api_router.post("/api/v1/cases/{case_id}/reviews", tags=["platform"])
def review_case_finding(case_id: str, payload: dict[str, str]) -> dict:
    return review_finding(case_id, payload.get("finding_id", ""), payload.get("decision", ""), payload.get("comment"))


@api_router.get("/api/v1/cases/{case_id}/reviews", tags=["platform"])
def get_case_reviews(case_id: str) -> list[dict]:
    return reviews(case_id)


@api_router.get("/api/v1/cases/{case_id}/custody", tags=["platform"])
def get_case_custody(case_id: str, document_id: str | None = None) -> list[dict]:
    return custody_entries(case_id, document_id)


@api_router.get("/api/v1/cases/{case_id}/methodology", tags=["platform"])
def get_case_methodology(case_id: str) -> list[dict]:
    return methodology_entries(case_id)


@api_router.get("/api/v1/standards", tags=["platform"])
def get_standards() -> list[dict[str, str]]:
    return standards_mapping()


@api_router.get("/api/v1/cases/{case_id}/report", tags=["platform"])
def get_case_report(case_id: str) -> dict:
    return build_report(case_id)


@api_router.get("/api/v1/cases/{case_id}/report.pdf", tags=["platform"])
def get_case_pdf_report(case_id: str) -> Response:
    return Response(
        content=build_pdf_report(case_id),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="proofmesh-{case_id}.pdf"'},
    )


@api_router.delete("/api/v1/cases/{case_id}", status_code=204, tags=["platform"])
def delete_case_route(case_id: str) -> None:
    delete_case(case_id)


@api_router.post("/api/v1/cases/{case_id}/assistant", tags=["platform"])
def case_assistant(case_id: str, payload: dict[str, str]) -> dict:
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="A question is required.")
    return answer_assistant(case_id, question, payload.get("language", "en"))


@api_router.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    """Return the service readiness state."""
    return HealthResponse()


@api_router.post(
    "/api/v1/investigations",
    response_model=InvestigationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["investigations"],
)
async def create_investigation(file: UploadFile = File(...)) -> InvestigationResponse:
    """Store an evidence file and return immutable intake metadata."""
    return await store_evidence(file)


@api_router.get(
    "/api/v1/investigations/{investigation_id}/evidence",
    response_class=FileResponse,
    tags=["investigations"],
)
def download_investigation_evidence(investigation_id: str) -> FileResponse:
    """Stream the original evidence only after the investigation id is known."""
    path = investigation_file(investigation_id)
    return FileResponse(path, filename=path.name)


@api_router.post(
    "/api/v1/investigations/{investigation_id}/analyze/metadata",
    response_model=MetadataAnalysisResponse,
    tags=["investigations"],
)
def analyze_investigation_metadata(investigation_id: str) -> MetadataAnalysisResponse:
    """Extract source metadata without making manipulation claims from absent metadata."""
    result = analyze_metadata(investigation_id)
    _record_if_case(investigation_id, "metadata")
    return result


@api_router.post(
    "/api/v1/investigations/{investigation_id}/analyze/image",
    response_model=ImageForensicsResponse,
    tags=["investigations"],
)
def analyze_investigation_image(investigation_id: str) -> ImageForensicsResponse:
    """Measure lightweight image-forensic heuristics without asserting image manipulation."""
    result = analyze_image_forensics(investigation_id)
    _record_if_case(investigation_id, "image_forensics")
    return result


@api_router.post(
    "/api/v1/investigations/{investigation_id}/analyze/copy-move",
    response_model=CopyMoveAnalysisResponse,
    tags=["investigations"],
)
def analyze_investigation_copy_move(investigation_id: str) -> CopyMoveAnalysisResponse:
    """Find visually duplicated image areas using bounded local-feature matching."""
    result = analyze_copy_move(investigation_id)
    _record_if_case(investigation_id, "copy_move")
    return result


@api_router.post(
    "/api/v1/investigations/{investigation_id}/analyze/ocr",
    response_model=OCRAnalysisResponse,
    tags=["investigations"],
)
def analyze_investigation_ocr(investigation_id: str) -> OCRAnalysisResponse:
    """Extract OCR text and source-pixel word boxes from image or PDF evidence."""
    result = analyze_ocr(investigation_id)
    _record_if_case(investigation_id, "ocr")
    return result


@api_router.post(
    "/api/v1/investigations/{investigation_id}/analyze/document",
    response_model=DocumentForensicsResponse,
    tags=["investigations"],
)
def analyze_investigation_document(investigation_id: str) -> DocumentForensicsResponse:
    """Compare OCR layout patterns and relate text boxes to image-analysis regions."""
    result = analyze_document_forensics(investigation_id)
    _record_if_case(investigation_id, "document_forensics")
    return result


@api_router.post(
    "/api/v1/investigations/{investigation_id}/analyze/fusion",
    response_model=EvidenceFusionResponse,
    tags=["investigations"],
)
def analyze_investigation_fusion(investigation_id: str) -> EvidenceFusionResponse:
    """Combine available evidence-analysis signals into a reproducible integrity score."""
    result = analyze_evidence_fusion(investigation_id)
    _record_if_case(investigation_id, "evidence_fusion")
    return result


@api_router.get(
    "/api/v1/investigations/{investigation_id}/graph",
    response_model=EvidenceGraphResponse,
    tags=["investigations"],
)
def get_investigation_graph(investigation_id: str) -> EvidenceGraphResponse:
    """Return evidence-backed artifact, signal, region, and finding relationships."""
    return build_evidence_graph(investigation_id)
