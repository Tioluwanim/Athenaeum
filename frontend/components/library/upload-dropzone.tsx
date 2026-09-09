"use client";

import { useCallback, useRef, useState } from "react";
import { UploadCloud, Loader2, FolderUp, FileUp } from "lucide-react";
import { cn } from "@/lib/utils";

// Kept in sync with backend ALLOWED_EXTENSIONS (app/config.py) — the server
// re-validates regardless, this just avoids an obviously-doomed upload.
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".doc", ".pptx", ".txt", ".xlsx", ".xls", ".csv"];
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");

function isAcceptedFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export function UploadDropzone({
  onFiles,
  uploading,
}: {
  onFiles: (files: File[]) => void;
  uploading: boolean;
}) {
  const [dragActive, setDragActive] = useState(false);
  const filesInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const files = Array.from(e.dataTransfer.files).filter(isAcceptedFile);
      if (files.length) onFiles(files);
    },
    [onFiles]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors",
        dragActive
          ? "border-index-500 bg-index-400/5"
          : "border-ink-200 dark:border-ink-700"
      )}
    >
      {/* Plain multi-file picker — no directory flag, so it opens a normal
          file dialog where the user can select one or several files. */}
      <input
        ref={filesInputRef}
        type="file"
        accept={ACCEPT_ATTR}
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []).filter(isAcceptedFile);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />

      {/* Separate folder picker — only this input carries webkitdirectory,
          and only fires when the user explicitly asks for it. */}
      <input
        ref={folderInputRef}
        type="file"
        accept={ACCEPT_ATTR}
        multiple
        // @ts-expect-error -- webkitdirectory isn't in the TS DOM lib but works in supporting browsers
        webkitdirectory=""
        directory=""
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []).filter(isAcceptedFile);
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
        {uploading ? "Uploading…" : "Drag files here"}
      </p>
      <p className="mt-1 text-xs text-ink-400">
        PDF, Word, PowerPoint, Excel, CSV or text — duplicates are caught automatically.
      </p>

      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => filesInputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-1.5 rounded-full border border-ink-200 px-4 py-2 text-sm font-medium text-ink-700 transition-colors hover:bg-ink-100 disabled:opacity-50 dark:border-ink-700 dark:text-ink-200 dark:hover:bg-ink-800"
        >
          <FileUp className="h-4 w-4" />
          Choose file{"\u00A0"}or files
        </button>
        <button
          type="button"
          onClick={() => folderInputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-1.5 rounded-full border border-ink-200 px-4 py-2 text-sm font-medium text-ink-700 transition-colors hover:bg-ink-100 disabled:opacity-50 dark:border-ink-700 dark:text-ink-200 dark:hover:bg-ink-800"
        >
          <FolderUp className="h-4 w-4" />
          Choose a folder
        </button>
      </div>
    </div>
  );
}
