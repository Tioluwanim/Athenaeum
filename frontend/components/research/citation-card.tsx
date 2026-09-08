"use client";

import Link from "next/link";
import { FileText } from "lucide-react";
import type { Citation } from "@/lib/api";

export function CitationCard({ citation }: { citation: Citation }) {
  return (
    <Link
      href={`/document/${citation.doc_id}?page=${citation.page_number}&highlight=${encodeURIComponent(citation.snippet)}`}
      className="block rounded-xl border border-ink-200/70 bg-white p-4 text-left transition-colors hover:border-index-400 hover:bg-index-400/5 dark:border-ink-800 dark:bg-ink-900 dark:hover:border-index-500"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-semibold text-index-600 dark:text-index-400">
          <FileText className="h-3.5 w-3.5" />
          {citation.citation_id} · p.{citation.page_number}
        </span>
        <span className="text-xs capitalize text-ink-400">{citation.section_type}</span>
      </div>
      <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-ink-700 dark:text-ink-300">
        &ldquo;{citation.snippet}&rdquo;
      </p>
      {citation.filename && (
        <p className="mt-2 truncate text-xs text-ink-400">{citation.filename}</p>
      )}
    </Link>
  );
}
