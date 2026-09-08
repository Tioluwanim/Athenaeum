"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Field } from "@/components/ui/field";
import { AuthShell } from "@/components/auth-shell";

export default function LoginPage() {
  const { signInWithEmail, signInWithGoogle } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<"email" | "google" | null>(null);

  const handleEmailSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading("email");
    try {
      await signInWithEmail(email, password);
      router.push("/library");
    } catch (err) {
      setError(readableAuthError(err));
    } finally {
      setLoading(null);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    setLoading("google");
    try {
      await signInWithGoogle();
      router.push("/library");
    } catch (err) {
      setError(readableAuthError(err));
    } finally {
      setLoading(null);
    }
  };

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to continue your research.">
      <button
        type="button"
        onClick={handleGoogle}
        disabled={loading !== null}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-ink-200 bg-white py-2.5 text-sm font-medium text-ink-800 transition-colors hover:bg-ink-50 disabled:opacity-60 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100 dark:hover:bg-ink-800"
      >
        {loading === "google" ? <Loader2 className="h-4 w-4 animate-spin" /> : <GoogleIcon />}
        Continue with Google
      </button>

      <div className="my-6 flex items-center gap-3 text-xs uppercase tracking-wide text-ink-400">
        <div className="h-px flex-1 bg-ink-200 dark:bg-ink-800" />
        or
        <div className="h-px flex-1 bg-ink-200 dark:bg-ink-800" />
      </div>

      <form onSubmit={handleEmailSubmit} className="space-y-4">
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" required />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" required />

        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={loading !== null}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink-900 py-2.5 text-sm font-medium text-parchment-50 transition-colors hover:bg-ink-700 disabled:opacity-60 dark:bg-parchment-100 dark:text-ink-900"
        >
          {loading === "email" && <Loader2 className="h-4 w-4 animate-spin" />}
          Sign in
        </button>
      </form>

      <div className="mt-6 flex justify-between text-sm">
        <Link href="/reset-password" className="text-ink-500 hover:text-ink-800 dark:text-ink-400 dark:hover:text-ink-100">
          Forgot password?
        </Link>
        <Link href="/register" className="font-medium text-index-600 hover:text-index-500 dark:text-index-400">
          Create an account
        </Link>
      </div>
    </AuthShell>
  );
}

function readableAuthError(err: unknown): string {
  const code = (err as { code?: string })?.code ?? "";
  if (code.includes("wrong-password") || code.includes("invalid-credential")) return "Incorrect email or password.";
  if (code.includes("user-not-found")) return "No account found with that email.";
  if (code.includes("too-many-requests")) return "Too many attempts. Please wait a moment and try again.";
  if (code.includes("popup-closed-by-user")) return "Sign-in was cancelled.";
  return "Something went wrong signing you in. Please try again.";
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden>
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.9 2.4 30.4 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.2 13 17.6 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.5 3-2.2 5.5-4.7 7.2l7.3 5.6c4.3-4 6.8-9.9 6.8-17.3z" />
      <path fill="#FBBC05" d="M10.4 19.3c-.5 1.5-.8 3.1-.8 4.7s.3 3.2.8 4.7l-7.8 6.1C1 31.5 0 27.9 0 24s1-7.5 2.6-10.8z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.3-5.6c-2.1 1.4-4.9 2.3-8.6 2.3-6.4 0-11.8-3.5-13.6-9.2l-7.8 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  );
}
