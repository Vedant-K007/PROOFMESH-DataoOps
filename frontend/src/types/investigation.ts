export interface InvestigationResponse {
  investigation_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  sha256: string;
}

export interface CaseDocument {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  sha256: string;
  status: string;
  created_at: string;
}

export interface InvestigationCase {
  id: string;
  name: string;
  case_reference: string | null;
  description: string | null;
  category: string;
  status: string;
  created_at: string;
  updated_at: string;
  documents: CaseDocument[];
}

export interface DashboardResponse {
  total_investigations: number;
  total_documents: number;
  pending_investigations: number;
  completed_investigations: number;
  investigations: Array<InvestigationCase & { document_count: number }>;
}
