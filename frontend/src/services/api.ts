import type {
  HealthResponse,
} from "../types/health";
import type { InvestigationResponse } from "../types/investigation";
import type { DashboardResponse, InvestigationCase, CaseDocument } from "../types/investigation";
import type {
  MetadataAnalysisResponse,
  ImageForensicsResponse,
  CopyMoveAnalysisResponse,
  OCRAnalysisResponse,
  DocumentForensicsResponse,
  EvidenceFusionResponse,
} from "../types/analysis";
import type { EvidenceGraphResponse } from "../types/graph";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export function evidenceUrl(investigationId: string): string {
  return `${apiBaseUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/evidence`;
}

export async function getDashboard(): Promise<DashboardResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/dashboard`);
  return handleResponse<DashboardResponse>(response, "Unable to load the investigation dashboard.");
}

export async function createCase(payload: {
  name: string;
  case_reference?: string;
  description?: string;
  category: string;
}): Promise<InvestigationCase> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<InvestigationCase>(response, "Unable to create the investigation.");
}

export async function uploadCaseDocument(caseId: string, file: File): Promise<CaseDocument> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/documents`, {
    method: "POST",
    body: formData,
  });
  return handleResponse<CaseDocument>(response, "Unable to attach the document.");
}

export async function classifyDocument(caseId: string, documentId: string): Promise<{
  classification: string;
  confidence: number;
  explanation: string;
  fields: Array<{ name: string; value: string; confidence: number; page: number; verification_status: string }>;
}> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/intelligence`, { method: "POST" });
  return handleResponse(response, "Unable to classify the document.");
}

export async function getCase(caseId: string): Promise<InvestigationCase> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}`);
  return handleResponse<InvestigationCase>(response, "Unable to load the investigation case.");
}

export async function getCaseComparison(caseId: string): Promise<{
  investigation_id: string;
  documents: CaseDocument[];
  comparisons: Array<{ left_document: string; right_document: string; status: string; explanation: string }>;
}> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/compare`);
  return handleResponse(response, "Unable to load the document comparison.");
}

export async function getCaseReport(caseId: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/report`);
  return handleResponse<Record<string, unknown>>(response, "Unable to generate the report.");
}

export function casePdfReportUrl(caseId: string): string {
  return `${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/report.pdf`;
}

export async function askCaseAssistant(caseId: string, question: string, language = "en"): Promise<{
  investigation_id: string;
  question: string;
  answer: string;
  evidence: { document_count: number; audit_events: number };
}> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/assistant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, language }),
  });
  return handleResponse(response, "Unable to answer the investigation question.");
}

export async function verifyCaseDocument(caseId: string, documentId: string): Promise<{ verified: boolean; computed_sha256: string }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(documentId)}/integrity`);
  return handleResponse(response, "Unable to verify evidence integrity.");
}

export async function getCaseTimeline(caseId: string): Promise<Array<{ action: string; created_at: string; details: Record<string, unknown> }>> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/timeline`);
  return handleResponse(response, "Unable to load evidence timeline.");
}

export async function searchCase(caseId: string, query: string): Promise<Array<{ filename: string; score: number; snippet: string; matched_terms: string[] }>> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/search?q=${encodeURIComponent(query)}`);
  return handleResponse(response, "Unable to search evidence.");
}

export async function getCaseEntities(caseId: string): Promise<{ nodes: Array<{ id: string; type: string; label: string }>; edges: Array<{ source: string; target: string; relationship: string }> }> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/entities`);
  return handleResponse(response, "Unable to load entity graph.");
}

export async function reviewFinding(caseId: string, findingId: string, decision: "accepted" | "rejected" | "flagged", comment: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/reviews`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ finding_id: findingId, decision, comment }),
  });
  await handleResponse(response, "Unable to record finding review.");
}

export async function getCaseCustody(caseId: string): Promise<Array<{ event_type: string; actor: string; details: Record<string, unknown>; created_at: string }>> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/custody`);
  return handleResponse(response, "Unable to load chain of custody.");
}

export async function getCaseMethodology(caseId: string): Promise<Array<{ analysis_type: string; engine: string; engine_version: string; outcome: string; completed_at: string }>> {
  const response = await fetch(`${apiBaseUrl}/api/v1/cases/${encodeURIComponent(caseId)}/methodology`);
  return handleResponse(response, "Unable to load analysis methodology.");
}

export async function getStandards(): Promise<Array<{ framework: string; requirement: string; control: string; status: string; verification: string; gap: string }>> {
  const response = await fetch(`${apiBaseUrl}/api/v1/standards`);
  return handleResponse(response, "Unable to load standards mapping.");
}

export async function loadDemoCase(): Promise<InvestigationCase> {
  const response = await fetch(`${apiBaseUrl}/api/v1/demo`, { method: "POST" });
  return handleResponse<InvestigationCase>(response, "Unable to load the synthetic demonstration case.");
}

export async function register(email: string, password: string, displayName: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${apiBaseUrl}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
  return handleResponse(response, "Unable to create the account.");
}

export async function login(email: string, password: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${apiBaseUrl}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse(response, "Unable to sign in.");
}

async function handleResponse<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? fallbackMessage);
  }
  return response.json() as Promise<T>;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/health`);
  return handleResponse<HealthResponse>(response, `Health check failed with status ${response.status}`);
}

export async function uploadEvidence(file: File): Promise<InvestigationResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${apiBaseUrl}/api/v1/investigations`, {
    method: "POST",
    body: formData,
  });

  return handleResponse<InvestigationResponse>(response, "Unable to upload evidence.");
}

export async function analyzeMetadata(investigationId: string): Promise<MetadataAnalysisResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/analyze/metadata`,
    { method: "POST" },
  );
  return handleResponse<MetadataAnalysisResponse>(response, "Metadata analysis failed.");
}

export async function analyzeImage(investigationId: string): Promise<ImageForensicsResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/analyze/image`,
    { method: "POST" },
  );
  return handleResponse<ImageForensicsResponse>(response, "Image forensics analysis failed.");
}

export async function analyzeCopyMove(investigationId: string): Promise<CopyMoveAnalysisResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/analyze/copy-move`,
    { method: "POST" },
  );
  return handleResponse<CopyMoveAnalysisResponse>(response, "Copy-move analysis failed.");
}

export async function analyzeOCR(investigationId: string): Promise<OCRAnalysisResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/analyze/ocr`,
    { method: "POST" },
  );
  return handleResponse<OCRAnalysisResponse>(response, "OCR analysis failed.");
}

export async function analyzeDocument(investigationId: string): Promise<DocumentForensicsResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/analyze/document`,
    { method: "POST" },
  );
  return handleResponse<DocumentForensicsResponse>(response, "Document forensics analysis failed.");
}

export async function analyzeFusion(investigationId: string): Promise<EvidenceFusionResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/analyze/fusion`,
    { method: "POST" },
  );
  return handleResponse<EvidenceFusionResponse>(response, "Evidence fusion analysis failed.");
}

export async function getEvidenceGraph(investigationId: string): Promise<EvidenceGraphResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/graph`,
  );
  return handleResponse<EvidenceGraphResponse>(response, "Evidence graph retrieval failed.");
}
