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
  collection_id: number | null;
  collection_name: string | null;
  likely_scanned: boolean;
}

export interface Collection {
  id: number;
  name: string;
  description: string;
  color: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
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
  session_id: number;
  answer: string;
  citations: Citation[];
  provider_used: string;
  timings_ms: Record<string, number>;
}

export interface ChatSession {
  id: number;
  name: string | null;
  document_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessageOut {
  id: number;
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
  citations: Citation[];
  created_at: string;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessageOut[];
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
  listDocuments: (token: string | null, collectionId?: number) => {
    const params = collectionId !== undefined ? `?collection_id=${collectionId}` : "";
    return request<DocumentSummary[]>(`/api/documents${params}`, token);
  },

  listCollections: (token: string | null) =>
    request<Collection[]>("/api/collections", token),

  createCollection: (token: string | null, name: string, description = "", color?: string) =>
    request<Collection>("/api/collections", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description, color: color ?? null }),
    }),

  updateCollection: (token: string | null, id: number, patch: { name?: string; description?: string; color?: string }) =>
    request<Collection>(`/api/collections/${id}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  deleteCollection: (token: string | null, id: number) =>
    request<{ status: string }>(`/api/collections/${id}`, token, { method: "DELETE" }),

  assignDocumentCollection: (token: string | null, docId: string, collectionId: number | null) =>
    request<{ status: string }>(`/api/documents/${docId}/collection`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ collection_id: collectionId }),
    }),

  getDocument: (token: string | null, docId: string) =>
    request<Record<string, unknown>>(`/api/documents/${docId}`, token),

  deleteDocument: (token: string | null, docId: string) =>
    request<{ status: string }>(`/api/documents/${docId}`, token, { method: "DELETE" }),

  reprocessDocument: (token: string | null, docId: string) =>
    request<{ status: string }>(`/api/documents/${docId}/reprocess`, token, { method: "POST" }),

  getSections: (token: string | null, docId: string) =>
    request<DocumentSection[]>(`/api/documents/${docId}/sections`, token),

  /** Triggers a browser download of the export file — returns nothing,
   * navigates the browser via a temporary anchor click. */
  exportDocuments: async (
    token: string | null,
    docIds: string[],
    format: "xlsx" | "docx",
    template: "journal" | "thesis" = "journal"
  ) => {
    const res = await fetch(`${API_BASE}/api/export/${format}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ doc_ids: docIds, template }),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        // ignore
      }
      throw new ApiError(res.status, detail);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match?.[1] || `export.${format}`;

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  uploadDocuments: async (token: string | null, files: File[]): Promise<UploadResult[]> => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await fetch(`${API_BASE}/api/documents/upload`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },

  search: (token: string | null, query: string, docId?: string) => {
    const params = new URLSearchParams({ q: query });
    if (docId) params.set("doc_id", docId);
    return request<Array<{ chunk_id: string; doc_id: string; page_number: number; section_type: string; content: string; score: number }>>(
      `/api/search?${params.toString()}`,
      token
    );
  },

  research: (token: string | null, query: string, docId?: string, sessionId?: number) =>
    request<ResearchResult>("/api/research", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, doc_id: docId ?? null, session_id: sessionId ?? null }),
    }),

  /** Streams newline-delimited JSON progress events, then the final result. */
  researchStream: async (
    token: string | null,
    query: string,
    docId: string | undefined,
    onEvent: (event: { event: string; [key: string]: unknown }) => void,
    sessionId?: number
  ) => {
    const res = await fetch(`${API_BASE}/api/research/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ query, doc_id: docId ?? null, session_id: sessionId ?? null }),
    });
    if (!res.ok || !res.body) throw new ApiError(res.status, await res.text());

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          onEvent(JSON.parse(line));
        } catch {
          // ignore malformed partial line
        }
      }
    }
  },

  libraryStats: (token: string | null) =>
    request<Record<string, unknown>>("/api/library/stats", token),

  listChatSessions: (token: string | null, docId?: string) => {
    const params = docId ? `?doc_id=${encodeURIComponent(docId)}` : "";
    return request<ChatSession[]>(`/api/chat/sessions${params}`, token);
  },

  getChatSession: (token: string | null, sessionId: number) =>
    request<ChatSessionDetail>(`/api/chat/sessions/${sessionId}`, token),

  deleteChatSession: (token: string | null, sessionId: number) =>
    request<{ status: string }>(`/api/chat/sessions/${sessionId}`, token, { method: "DELETE" }),

  me: (token: string | null) => request<CurrentUser>("/api/auth/me", token),

  promoteToAdmin: (token: string | null, inviteCode: string) =>
    request<{ status: string }>("/api/auth/promote-to-admin", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite_code: inviteCode }),
    }),
};

export { ApiError, API_BASE };
