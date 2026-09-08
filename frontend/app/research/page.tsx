"use client";

import { useState, type FormEvent } from "react";
import { Sparkles, Send, AlertTriangle } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { ResearchProgress } from "@/components/research/progress";
import { CitationCard } from "@/components/research/citation-card";
import { useAuth } from "@/lib/auth-context";
import { api, type Citation, ApiError } from "@/lib/api";

type Stage = { stage: string; label: string } | null;

export default function ResearchPage() {
  const { getIdToken } = useAuth();
  const [query, setQuery] = useState("");
  const [asking, setAsking] = useState(false);
  const [stage, setStage] = useState<Stage>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim() || asking) return;

    setAsking(true);
    setAnswer(null);
    setCitations([]);
    setError(null);
    setStage({ stage: "searching", label: "Searching the library…" });

    try {
      const token = await getIdToken();
      await api.researchStream(token, query, undefined, (event) => {
        if (event.event === "stage") {
          setStage({ stage: String(event.stage), label: String(event.label) });
        } else if (event.event === "result") {
          setAnswer(String(event.answer));
          setCitations((event.citations as Citation[]) ?? []);
        }
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setAsking(false);
      setStage(null);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto flex h-full max-w-6xl gap-8 px-8 py-10">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-2xl text-ink-900 dark:text-parchment-50">Research</h1>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
            Ask a question across the whole library. Answers are grounded in your documents, with citations to the source page.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. What does the diocesan report say about hostel assignment?"
              aria-label="Research question"
              className="flex-1 rounded-xl border border-ink-200 bg-white px-4 py-3 text-sm outline-none transition-colors focus:border-index-500 focus:ring-1 focus:ring-index-500 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100"
            />
            <button
              type="submit"
              disabled={asking || !query.trim()}
              className="flex items-center gap-2 rounded-xl bg-ink-900 px-5 text-sm font-medium text-parchment-50 transition-colors hover:bg-ink-700 disabled:opacity-50 dark:bg-parchment-100 dark:text-ink-900"
            >
              <Send className="h-4 w-4" />
              Ask
            </button>
          </form>

          <div className="mt-8">
            {stage && <ResearchProgress label={stage.label} done={false} />}

            {error && (
              <div className="mt-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            {answer && (
              <div className="mt-2 animate-fade-up rounded-2xl border border-ink-200/70 bg-white p-6 dark:border-ink-800 dark:bg-ink-900">
                <div className="flex items-center gap-2 text-xs font-medium text-index-600 dark:text-index-400">
                  <Sparkles className="h-3.5 w-3.5" />
                  Evidence-backed answer
                </div>
                <p className="mt-3 whitespace-pre-wrap text-[15px] leading-relaxed text-ink-800 dark:text-ink-100">
                  {answer}
                </p>
              </div>
            )}

            {!stage && !answer && !error && (
              <div className="mt-4 rounded-2xl border border-dashed border-ink-200 py-16 text-center dark:border-ink-800">
                <p className="text-sm text-ink-400">Ask a question to see evidence-backed research here.</p>
              </div>
            )}
          </div>
        </div>

        {citations.length > 0 && (
          <aside className="w-80 shrink-0">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-400">
              Sources ({citations.length})
            </h2>
            <div className="mt-3 space-y-3">
              {citations.map((c) => (
                <CitationCard key={c.citation_id} citation={c} />
              ))}
            </div>
          </aside>
        )}
      </div>
    </AppShell>
  );
}
