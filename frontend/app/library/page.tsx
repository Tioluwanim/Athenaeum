"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { Search as SearchIcon, Library as LibraryIcon, AlertTriangle, CheckSquare, X, Download, Loader2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { UploadDropzone } from "@/components/library/upload-dropzone";
import { DocumentCard } from "@/components/library/document-card";
import { useAuth } from "@/lib/auth-context";
import { api, type DocumentSummary, ApiError } from "@/lib/api";

const PROCESSING_STATES = new Set(["uploaded", "processing"]);

export default function LibraryPage() {
  const { getIdToken } = useAuth();
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [uploading, setUploading] = useState(false);

  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState<"xlsx" | "docx" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const token = await getIdToken();
      const docs = await api.listDocuments(token);
      setDocuments(docs);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the library server.");
    }
  }, [getIdToken]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while anything is still processing, so cards update to "Ready"
  // without the user needing to refresh.
  useEffect(() => {
    const hasPending = documents?.some((d) => PROCESSING_STATES.has(d.status));
    if (!hasPending) return;
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [documents, load]);

  const handleUpload = async (files: File[]) => {
    setUploading(true);
    try {
      const token = await getIdToken();
      await api.uploadDocuments(token, files);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const filtered = useMemo(() => {
    if (!documents) return null;
    if (!query.trim()) return documents;
    const q = query.toLowerCase();
    return documents.filter(
      (d) => d.title.toLowerCase().includes(q) || d.filename.toLowerCase().includes(q) || d.authors.some((a) => a.toLowerCase().includes(q))
    );
  }, [documents, query]);

  const readyCount = useMemo(() => filtered?.filter((d) => d.status === "ready").length ?? 0, [filtered]);

  const toggleSelectMode = () => {
    setSelectMode((v) => !v);
    setSelected(new Set());
    setExportError(null);
  };

  const toggleSelected = (docId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const selectAll = () => {
    if (!filtered) return;
    setSelected(new Set(filtered.filter((d) => d.status === "ready").map((d) => d.doc_id)));
  };

  const clearSelection = () => setSelected(new Set());

  const handleBulkExport = async (format: "xlsx" | "docx") => {
    if (selected.size === 0) return;
    setExporting(format);
    setExportError(null);
    try {
      const token = await getIdToken();
      await api.exportDocuments(token, Array.from(selected), format);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "Export failed. Please try again.");
    } finally {
      setExporting(null);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl px-8 py-10">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl text-ink-900 dark:text-parchment-50">Library</h1>
            <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
              {documents ? `${documents.length} document${documents.length === 1 ? "" : "s"}` : "Loading…"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative w-full max-w-xs">
              <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter by title or author…"
                aria-label="Filter documents"
                className="w-full rounded-full border border-ink-200 bg-white py-2 pl-9 pr-3 text-sm outline-none transition-colors focus:border-index-500 focus:ring-1 focus:ring-index-500 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100"
              />
            </div>
            {readyCount > 0 && (
              <button
                type="button"
                onClick={toggleSelectMode}
                className={cnBtn(selectMode)}
              >
                {selectMode ? <X className="h-4 w-4" /> : <CheckSquare className="h-4 w-4" />}
                {selectMode ? "Cancel" : "Select"}
              </button>
            )}
          </div>
        </div>

        <div className="mt-8">
          <UploadDropzone onFiles={handleUpload} uploading={uploading} />
        </div>

        {error && (
          <div className="mt-6 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {selectMode && (
          <div className="sticky top-4 z-10 mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-ink-200/70 bg-white/95 px-5 py-3 shadow-card backdrop-blur dark:border-ink-800 dark:bg-ink-900/95">
            <div className="flex items-center gap-4">
              <span className="text-sm font-medium text-ink-800 dark:text-ink-100">
                {selected.size} selected
              </span>
              <button type="button" onClick={selectAll} className="text-xs font-medium text-index-600 hover:text-index-500 dark:text-index-400">
                Select all ({readyCount})
              </button>
              {selected.size > 0 && (
                <button type="button" onClick={clearSelection} className="text-xs font-medium text-ink-500 hover:text-ink-800 dark:text-ink-400 dark:hover:text-ink-100">
                  Clear
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleBulkExport("docx")}
                disabled={selected.size === 0 || exporting !== null}
                className="flex items-center gap-1.5 rounded-lg border border-ink-200 px-3 py-1.5 text-xs font-medium text-ink-600 transition-colors hover:bg-ink-100 disabled:opacity-40 dark:border-ink-700 dark:text-ink-300 dark:hover:bg-ink-800"
              >
                {exporting === "docx" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                Export Word
              </button>
              <button
                type="button"
                onClick={() => handleBulkExport("xlsx")}
                disabled={selected.size === 0 || exporting !== null}
                className="flex items-center gap-1.5 rounded-lg bg-ink-900 px-3 py-1.5 text-xs font-medium text-parchment-50 transition-colors hover:bg-ink-700 disabled:opacity-40 dark:bg-parchment-100 dark:text-ink-900"
              >
                {exporting === "xlsx" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                Export Excel
              </button>
            </div>
          </div>
        )}

        {exportError && (
          <p className="mt-3 text-sm text-red-600 dark:text-red-400">{exportError}</p>
        )}

        <div className="mt-8">
          {documents === null && !error ? (
            <GridSkeleton />
          ) : filtered && filtered.length > 0 ? (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((doc) => (
                <DocumentCard
                  key={doc.doc_id}
                  doc={doc}
                  selectable={selectMode}
                  selected={selected.has(doc.doc_id)}
                  onToggleSelect={toggleSelected}
                />
              ))}
            </div>
          ) : documents && documents.length > 0 ? (
            <EmptyState title="No matches" body="Try a different title or author." />
          ) : (
            <EmptyState
              title="No documents yet"
              body="Drag a PDF above to start building the library."
              icon={LibraryIcon}
            />
          )}
        </div>
      </div>
    </AppShell>
  );
}

function cnBtn(active: boolean) {
  return [
    "flex shrink-0 items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-colors",
    active
      ? "bg-ink-900 text-parchment-50 dark:bg-parchment-100 dark:text-ink-900"
      : "border border-ink-200 text-ink-600 hover:bg-ink-100 dark:border-ink-700 dark:text-ink-300 dark:hover:bg-ink-800",
  ].join(" ");
}

function GridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-44 animate-pulse rounded-2xl border border-ink-200/70 bg-white/60 dark:border-ink-800 dark:bg-ink-900/60" />
      ))}
    </div>
  );
}

function EmptyState({
  title,
  body,
  icon: Icon = LibraryIcon,
}: {
  title: string;
  body: string;
  icon?: typeof LibraryIcon;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-ink-200 py-16 text-center dark:border-ink-800">
      <Icon className="h-8 w-8 text-ink-300 dark:text-ink-600" />
      <h3 className="mt-3 font-display text-base text-ink-800 dark:text-ink-100">{title}</h3>
      <p className="mt-1 max-w-xs text-sm text-ink-500 dark:text-ink-400">{body}</p>
    </div>
  );
}
