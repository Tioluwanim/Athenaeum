"use client";

import { Loader2, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function ResearchProgress({ label, done }: { label: string; done: boolean }) {
  return (
    <div className="flex items-center gap-2.5 text-sm">
      {done ? (
        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
      ) : (
        <Loader2 className="h-4 w-4 animate-spin text-index-500" />
      )}
      <span className={cn(done ? "text-ink-500 dark:text-ink-400" : "text-ink-800 dark:text-ink-100")}>{label}</span>
    </div>
  );
}
