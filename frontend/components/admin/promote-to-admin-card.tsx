"use client";

import { useState, type FormEvent } from "react";
import { ShieldCheck, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError } from "@/lib/api";

export function PromoteToAdminCard({ onPromoted }: { onPromoted: () => void }) {
  const { getIdToken } = useAuth();
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const token = await getIdToken();
      await api.promoteToAdmin(token, code.trim());
      onPromoted();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not verify that code. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mb-6 rounded-2xl border border-index-400/40 bg-index-400/5 p-5">
      <div className="flex items-start gap-3">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-index-600 dark:text-index-400" />
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-sm text-ink-900 dark:text-parchment-50">
            Uploads need an admin account
          </h2>
          <p className="mt-1 text-sm text-ink-600 dark:text-ink-400">
            Your account is currently staff (search &amp; ask only). Enter the library's
            admin invite code once to unlock uploading and managing documents.
          </p>
          <form onSubmit={handleSubmit} className="mt-3 flex flex-wrap gap-2">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Admin invite code"
              aria-label="Admin invite code"
              className="min-w-[180px] flex-1 rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-index-500 focus:ring-1 focus:ring-index-500 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100"
            />
            <button
              type="submit"
              disabled={loading || !code.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-ink-900 px-4 py-2 text-sm font-medium text-parchment-50 transition-colors hover:bg-ink-700 disabled:opacity-50 dark:bg-parchment-100 dark:text-ink-900"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              Become admin
            </button>
          </form>
          {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
      </div>
    </div>
  );
}
