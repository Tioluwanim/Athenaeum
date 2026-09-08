"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Loader2, MailCheck } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { AuthShell } from "@/components/auth-shell";
import { Field } from "@/components/ui/field";

export default function ResetPasswordPage() {
  const { resetPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await resetPassword(email);
      setSent(true);
    } catch {
      // Don't reveal whether the email exists — same UX either way.
      setSent(true);
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <AuthShell title="Check your email" subtitle="If an account exists, a reset link is on its way.">
        <div className="flex flex-col items-center py-4 text-center">
          <MailCheck className="h-8 w-8 text-index-500" />
          <Link href="/login" className="mt-6 text-sm font-medium text-index-600 hover:text-index-500 dark:text-index-400">
            Back to sign in
          </Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Reset your password" subtitle="We'll email you a link to choose a new one.">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" required />
        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink-900 py-2.5 text-sm font-medium text-parchment-50 transition-colors hover:bg-ink-700 disabled:opacity-60 dark:bg-parchment-100 dark:text-ink-900"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          Send reset link
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-ink-500 dark:text-ink-400">
        <Link href="/login" className="font-medium text-index-600 hover:text-index-500 dark:text-index-400">
          Back to sign in
        </Link>
      </p>
    </AuthShell>
  );
}
