import Link from "next/link";
import { Library } from "lucide-react";
import type { ReactNode } from "react";

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-parchment-50 px-6 dark:bg-ink-950">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2 font-display text-lg font-medium text-ink-900 dark:text-parchment-50">
          <Library className="h-5 w-5 text-index-500" />
          Athenaeum
        </Link>
        <div className="rounded-2xl border border-ink-200/70 bg-white p-8 shadow-card dark:border-ink-800 dark:bg-ink-900">
          <h1 className="font-display text-2xl text-ink-900 dark:text-parchment-50">{title}</h1>
          <p className="mt-1.5 text-sm text-ink-500 dark:text-ink-400">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  );
}
