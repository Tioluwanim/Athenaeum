"use client";

import { useEffect, useState } from "react";
import { Loader2, FileText, ChevronDown } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { api, type DocumentSection } from "@/lib/api";
import { cn } from "@/lib/utils";

const SECTION_LABELS: Record<string, string> = {
  abstract: "Abstract",
  introduction: "Introduction",
  methods: "Methods",
  results: "Results",
  discussion: "Discussion",
  conclusion: "Conclusion",
  references: "References",
  other: "Other",
};

export function SectionsPanel({ docId }: { docId: string }) {
  const { getIdToken } = useAuth();
  const [sections, setSections] = useState<DocumentSection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getIdToken();
        const data = await api.getSections(token, docId);
        if (!cancelled) setSections(data);
      } catch {
        if (!cancelled) setError("Could not load the section breakdown for this document.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [docId, getIdToken]);

  if (error) {
    return <p className="p-6 text-sm text-red-600 dark:text-red-400">{error}</p>;
  }

  if (sections === null) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-ink-400" />
      </div>
    );
  }

  if (sections.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center">
        <FileText className="h-8 w-8 text-ink-300 dark:text-ink-600" />
        <p className="mt-3 text-sm text-ink-500 dark:text-ink-400">
          No section structure was detected for this document.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-4">
      <div className="space-y-2">
        {sections.map((s, i) => {
          const isOpen = openIndex === i;
          const label = s.title || SECTION_LABELS[s.section_type] || s.section_type;
          return (
            <div
              key={`${s.section_type}-${i}`}
              className="overflow-hidden rounded-xl border border-ink-200/70 bg-white dark:border-ink-800 dark:bg-ink-900"
            >
              <button
                type="button"
                onClick={() => setOpenIndex(isOpen ? null : i)}
                aria-expanded={isOpen}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="shrink-0 rounded-full bg-parchment-100 px-2 py-0.5 text-[11px] font-medium capitalize text-index-600 dark:bg-ink-800 dark:text-index-400">
                    {SECTION_LABELS[s.section_type] ?? s.section_type}
                  </span>
                  <span className="truncate font-display text-sm text-ink-900 dark:text-parchment-50">
                    {label}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="text-xs text-ink-400">
                    {s.page_start === s.page_end ? `p.${s.page_start}` : `p.${s.page_start}–${s.page_end}`}
                    {" · "}
                    {s.word_count} words
                  </span>
                  <ChevronDown className={cn("h-4 w-4 text-ink-400 transition-transform", isOpen && "rotate-180")} />
                </div>
              </button>
              {isOpen && (
                <div className="border-t border-ink-200/70 px-4 py-3 dark:border-ink-800">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-700 dark:text-ink-300">
                    {s.content}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
