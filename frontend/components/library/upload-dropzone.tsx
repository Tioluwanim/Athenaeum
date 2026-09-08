"use client";

import { useCallback, useRef, useState } from "react";
import { UploadCloud, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function UploadDropzone({
  onFiles,
  uploading,
}: {
  onFiles: (files: File[]) => void;
  uploading: boolean;
}) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const files = Array.from(e.dataTransfer.files).filter((f) => f.type === "application/pdf");
      if (files.length) onFiles(files);
    },
    [onFiles]
  );

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-index-500",
        dragActive
          ? "border-index-500 bg-index-400/5"
          : "border-ink-200 hover:border-ink-300 dark:border-ink-700 dark:hover:border-ink-600"
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        multiple
        // @ts-expect-error -- webkitdirectory isn't in the TS DOM lib but works in supporting browsers
        webkitdirectory=""
        directory=""
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []).filter((f) => f.type === "application/pdf" || f.name.endsWith(".pdf"));
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
      {uploading ? (
        <Loader2 className="h-7 w-7 animate-spin text-index-500" />
      ) : (
        <UploadCloud className="h-7 w-7 text-ink-400" />
      )}
      <p className="mt-3 text-sm font-medium text-ink-700 dark:text-ink-200">
        {uploading ? "Uploading…" : "Drag PDFs here, or click to browse"}
      </p>
      <p className="mt-1 text-xs text-ink-400">Multiple files or a whole folder — duplicates are caught automatically.</p>
    </div>
  );
}
