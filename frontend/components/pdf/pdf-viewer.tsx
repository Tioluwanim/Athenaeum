"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { ChevronLeft, ChevronRight, Loader2, ZoomIn, ZoomOut } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export function PdfViewer({
  docId,
  initialPage = 1,
  highlight,
}: {
  docId: string;
  initialPage?: number;
  highlight?: string;
}) {
  const { getIdToken } = useAuth();
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(initialPage);
  const [scale, setScale] = useState(1.15);
  const containerRef = useRef<HTMLDivElement>(null);

  // Fetch the PDF as an authenticated blob — <embed>/<iframe> can't attach
  // an Authorization header, and this endpoint requires a valid Firebase
  // session like everything else.
  useEffect(() => {
    let revoked = "";
    (async () => {
      try {
        const token = await getIdToken();
        const res = await fetch(`${API_BASE}/api/documents/${docId}/file`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error("Could not load this document.");
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        revoked = url;
        setBlobUrl(url);
      } catch {
        setError("Could not load this document. It may still be processing, or you may not have access.");
      }
    })();
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [docId, getIdToken]);

  useEffect(() => {
    setPageNumber(initialPage);
  }, [initialPage]);

  // Highlight matching text spans in the rendered text layer once the page
  // (and its text layer) has painted.
  const highlightPage = () => {
    if (!highlight || !containerRef.current) return;
    const needle = highlight.trim().slice(0, 60).toLowerCase(); // enough to match uniquely, short enough to survive line breaks
    const spans = containerRef.current.querySelectorAll(".react-pdf__Page__textContent span");
    let combined = "";
    const spanList: { el: Element; start: number; end: number }[] = [];
    spans.forEach((el) => {
      const text = (el.textContent || "").toLowerCase();
      spanList.push({ el, start: combined.length, end: combined.length + text.length });
      combined += text;
    });
    const idx = combined.indexOf(needle);
    if (idx === -1) return;
    const end = idx + needle.length;
    spanList
      .filter((s) => s.end > idx && s.start < end)
      .forEach((s) => {
        (s.el as HTMLElement).classList.add("pdf-highlight");
        if (s.start <= idx) (s.el as HTMLElement).scrollIntoView({ block: "center", behavior: "smooth" });
      });
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-ink-200/70 px-4 py-2.5 dark:border-ink-800">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
            disabled={pageNumber <= 1}
            aria-label="Previous page"
            className="rounded-lg p-1.5 text-ink-500 hover:bg-ink-100 disabled:opacity-30 dark:text-ink-400 dark:hover:bg-ink-800"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-xs text-ink-500 dark:text-ink-400">
            Page {pageNumber} {numPages ? `of ${numPages}` : ""}
          </span>
          <button
            onClick={() => setPageNumber((p) => Math.min(numPages || p + 1, p + 1))}
            disabled={numPages > 0 && pageNumber >= numPages}
            aria-label="Next page"
            className="rounded-lg p-1.5 text-ink-500 hover:bg-ink-100 disabled:opacity-30 dark:text-ink-400 dark:hover:bg-ink-800"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setScale((s) => Math.max(0.6, s - 0.15))} aria-label="Zoom out" className="rounded-lg p-1.5 text-ink-500 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800">
            <ZoomOut className="h-4 w-4" />
          </button>
          <button onClick={() => setScale((s) => Math.min(2.5, s + 0.15))} aria-label="Zoom in" className="rounded-lg p-1.5 text-ink-500 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-800">
            <ZoomIn className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div ref={containerRef} className="flex-1 overflow-auto bg-ink-100/50 dark:bg-ink-950 [&_.pdf-highlight]:rounded-sm [&_.pdf-highlight]:bg-index-400/50">
        {error && <p className="p-8 text-center text-sm text-red-600 dark:text-red-400">{error}</p>}
        {!error && !blobUrl && (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-ink-400" />
          </div>
        )}
        {blobUrl && (
          <Document
            file={blobUrl}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            loading={<div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-ink-400" /></div>}
            error={<p className="p-8 text-center text-sm text-red-600 dark:text-red-400">Could not render this PDF.</p>}
            className="flex justify-center py-8"
          >
            <Page
              pageNumber={pageNumber}
              scale={scale}
              onRenderTextLayerSuccess={highlightPage}
              className="shadow-card"
            />
          </Document>
        )}
      </div>
    </div>
  );
}
