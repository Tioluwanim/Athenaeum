"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Loader2, MailCheck } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { AuthShell } from "@/components/auth-shell";
import { Field } from "@/components/ui/field";

export default function RegisterPage() {
  const { registerWithEmail, signInWithGoogle } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<"email" | "google" | null>(null);
  const [verificationSent, setVerificationSent] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading("email");
    try {
      await registerWithEmail(email, password);
      setVerificationSent(true);
    } catch (err) {
      const code = (err as { code?: string })?.code ?? "";
      setError(code.includes("email-already-in-use") ? "An account with that email already exists." : "Could not create your account. Please try again.");
    } finally {
      setLoading(null);
    }
  };

  const handleGoogle = async () => {
    setLoading("google");
    try {
      await signInWithGoogle();
      window.location.href = "/library";
    } catch {
      setError("Something went wrong signing you in. Please try again.");
    } finally {
      setLoading(null);
    }
  };

  if (verificationSent) {
    return (
      <AuthShell title="Check your email" subtitle="One more step before you're in.">
        <div className="flex flex-col items-center py-4 text-center">
          <MailCheck className="h-8 w-8 text-index-500" />
          <p className="mt-4 text-sm text-ink-600 dark:text-ink-300">
            We sent a verification link to <span className="font-medium">{email}</span>. Verify your address, then sign in.
          </p>
          <Link href="/login" className="mt-6 text-sm font-medium text-index-600 hover:text-index-500 dark:text-index-400">
            Go to sign in
          </Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Create your account" subtitle="Join your library's shared research space.">
      <button
        type="button"
        onClick={handleGoogle}
        disabled={loading !== null}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-ink-200 bg-white py-2.5 text-sm font-medium text-ink-800 transition-colors hover:bg-ink-50 disabled:opacity-60 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100 dark:hover:bg-ink-800"
      >
        {loading === "google" && <Loader2 className="h-4 w-4 animate-spin" />}
        Continue with Google
      </button>

      <div className="my-6 flex items-center gap-3 text-xs uppercase tracking-wide text-ink-400">
        <div className="h-px flex-1 bg-ink-200 dark:bg-ink-800" />
        or
        <div className="h-px flex-1 bg-ink-200 dark:bg-ink-800" />
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" required />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          required
          hint="At least 8 characters."
        />

        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={loading !== null}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink-900 py-2.5 text-sm font-medium text-parchment-50 transition-colors hover:bg-ink-700 disabled:opacity-60 dark:bg-parchment-100 dark:text-ink-900"
        >
          {loading === "email" && <Loader2 className="h-4 w-4 animate-spin" />}
          Create account
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-500 dark:text-ink-400">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-index-600 hover:text-index-500 dark:text-index-400">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}
