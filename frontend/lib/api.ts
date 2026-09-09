const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface DocumentSummary {
  doc_id: string;
  filename: string;
  title: string;
  status: string;
  page_count: number;
  chunk_count: number;
  authors: string[];
  year: string;
  updated_at: string;
  last_error?: string | null;
}

export interface Citation {
  citation_id: string;
  doc_id: string;
  filename: string;
  page_number: number;
  section_type: string;
  snippet: string;
  score: number;
}

export interface ResearchResult {
  answer: string;
  citations: Citation[];
  provider_used: string;
  timings_ms: Record<string, number>;
}

export interface UploadResult {
  doc_id: string;
  filename: string;
  status: string;
  duplicate_of?: string | null;
}

export interface DocumentSection {
  section_type: string;
  title: string;
  content: string;
  page_start: number;
  page_end: number;
  word_count: number;
}

export interface CurrentUser {
  id: number;
  firebase_uid: string;
  email: string;
  full_name: string;
  role: "admin" | "staff";
  email_verified: boolean;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token: string | null,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.error || detail;
    } catch {
      // response wasn't JSON; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listDocuments: (token: string | null) =>
    request<DocumentSummary[]>("/api/documents", token),

  getDocument: (token: string | null, docId: string) =>
    request<Record<string, unknown>>(`/api/documents/${docId}`, token),

  deleteDocument: (token: string | null, docId: string) =>
    request<{ status: string }>(`/api/documents/${docId}`, token, { method: "DELETE" }),

  getSections: (token: string | null, docId: string) =>
    request<DocumentSection[]>(`/api/documents/${docId}/sections`,
