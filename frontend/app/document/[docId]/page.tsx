"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Send, Sparkles, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PdfViewer } from "@/components/pdf/pdf-viewer";
import { ResearchProgress } from "@/components/research/progress";
import { CitationCard } from "@/components/research/citation-card";
import { useAuth } from "@/lib/auth-context";
import { api, type Citation, type DocumentSummary } from "@/lib/api";

export default function DocumentPage() {
  const params = useParams<{ docId: string }>();
  const searchParams = useSearchParams();
  const { getIdToken } = useAuth();

  const initialPage = Number(searchParams.get("page") ?? 1) || 1;
  const highlight = searchParams.get("highlight") ?? undefined;

  const [doc, setDoc] = useState<DocumentSummary | null>(null);
  const [query, setQuery] = useState("");
  const [asking, setAsking] = useState(false);
  const [stageLabel, setStageLabel] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);

  useEffect(() => {
    (async () => {
      const token = await getIdToken();
      const docs = await api.listDocuments(token);
      setDoc(docs.find((d) => d.doc_id === params.docId) ?? null);
    })();
  }, [params.docId, getIdToken]);

  const handleAsk = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim() || asking) return;
    setAsking(true);
    setAnswer(null);
    setCitations([]);
    setStageLabel("Searching this document…");
    try {
      const token = await getIdToken();
      await api.researchStream(token, query, params.docId, (event) => {
        if (event.event === "stage") setStageLabel(String(event.label));
        if (event.event === "result") {
          setAnswer(String(event.answer));
          setCitations((event.citations as Citation[]) ?? []);
        }
      });
    } finally {
      setAsking(false);
      setStageLabel(null);
    }
  };

  return (
    <AppShell>
      <div className="flex h-screen flex-col">
        <div className="flex items-center gap-3 border-b border-ink-200/70 px-6 py-3 dark:border-ink-800">
          <Link href="/library" className="flex items-center gap-1.5 text-sm text-ink-500 hover:text-ink-800 dark:text-ink-400 dark:hover:text-ink-100">
            <ArrowLeft className="h-4 w-4" />
            Library
          </Link>
          <span className="text-ink-300 dark:text-ink-700">/</span>
          <h1 className="truncate font-display text-sm text-ink-800 dark:text-ink-100">
            {doc?.title || doc?.filename || "Document"}
          </h1>
        </div>

        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1">
            <PdfViewer docId={params.docId} initialPage={initialPage} highlight={highlight} />
          </div>

          <aside className="flex w-96 shrink-0 flex-col border-l border-ink-200/70 dark:border-ink-800">
            <div className="border-b border-ink-200/70 px-5 py-4 dark:border-ink-800">
              <h2 className="font-display text-sm text-ink-900 dark:text-parchment-50">Ask about this document</h2>
              <form onSubmit={handleAsk} className="mt-3 flex gap-2">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="What does this document say about…"
                  aria-label="Question about this document"
                  className="flex-1 rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-index-500 focus:ring-1 focus:ring-index-500 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100"
                />
                <button
                  type="submit"
                  disabled={asking || !query.trim()}
                  aria-label="Ask"
                  className="flex items-center justify-center rounded-lg bg-ink-900 px-3 text-parchment-50 transition-colors hover:bg-ink-700 disabled:opacity-50 dark:bg-parchment-100 dark:text-ink-900"
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>
            </div>

            <div className="flex-1 overflow-auto px-5 py-4">
              {stageLabel && <ResearchProgress label={stageLabel} done={false} />}

              {answer && (
                <div className="animate-fade-up rounded-xl border border-ink-200/70 bg-white p-4 dark:border-ink-800 dark:bg-ink-900">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-index-600 dark:text-index-400">
                    <Sparkles className="h-3.5 w-3.5" />
                    Answer
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink-800 dark:text-ink-100">{answer}</p>
                </div>
              )}

              {citations.length > 0 && (
                <div className="mt-4 space-y-3">
                  {citations.map((c) => (
                    <CitationCard key={c.citation_id} citation={c} />
                  ))}
                </div>
              )}

              {!stageLabel && !answer && (
                <p className="mt-2 text-sm text-ink-400">
                  Questions here are answered only from this document — useful for close reading rather than library-wide research.
                </p>
              )}
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}
