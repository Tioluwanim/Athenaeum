"use client";

import Link from "next/link";
import { FileText, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import type { DocumentSummary } from "@/lib/api";
import { formatDate, cn } from "@/lib/utils";

const STATUS_META: Record<string, { icon: typeof CheckCircle2; label: string; className: string }> = {
  ready: { icon: CheckCircle2, label: "Ready", className: "text-emerald-600 dark:text-emerald-400" },
  processing: { icon: Loader2, label: "Processing…", className: "text-index-600 dark:text-index-400" },
  uploaded: { icon: Loader2, label: "Queued…", className: "text-ink-400" },
  failed: { icon: AlertCircle, label: "Failed", className: "text-red-600 dark:text-red-400" },
};

export function DocumentCard({ doc }: { doc: DocumentSummary }) {
  const meta = STATUS_META[doc.status] ?? STATUS_META.uploaded;
  const StatusIcon = meta.icon;
  const isReady = doc.status === "ready";

  const content = (
    <>
      <div className="flex items-start justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-parchment-100 dark:bg-ink-800">
          <FileText className="h-5 w-5 text-index-600 dark:text-index-400" />
        </div>
        <span className={cn("flex items-center gap-1.5 text-xs font-medium", meta.className)}>
          <StatusIcon className={cn("h-3.5 w-3.5", (doc.status === "processing" || doc.status === "uploaded") && "animate-spin")} />
          {meta.label}
        </span>
      </div>

      <h3 className="mt-4 line-clamp-2 font-display text-base text-ink-900 dark:text-parchment-50">
        {doc.title || doc.filename}
      </h3>

      {doc.authors.length > 0 && (
        <p className="mt-1 truncate text-xs text-ink-500 dark:text-ink-400">{doc.authors.join(", ")}</p>
      )}

      <div className="mt-auto flex items-center justify-between pt-4 text-xs text-ink-400">
        <span>{doc.page_count ? `${doc.page_count} pages` : "\u00A0"}</span>
        <span>{formatDate(doc.updated_at)}</span>
      </div>

      {doc.status === "failed" && doc.last_error && (
        <p className="mt-2 line-clamp-2 text-xs text-red-500 dark:text-red-400">{doc.last_error}</p>
      )}
    </>
  );

  const className = cn(
    "group flex flex-col rounded-2xl border border-ink-200/70 bg-white p-5 text-left shadow-card transition-all dark:border-ink-800 dark:bg-ink-900",
    isReady && "hover:-translate-y-0.5 hover:shadow-lg"
  );

  if (isReady) {
    return (
      <Link href={`/document/${doc.doc_id}`} className={className}>
        {content}
      </Link>
    );
  }
  return <div className={className}>{content}</div>;
}
