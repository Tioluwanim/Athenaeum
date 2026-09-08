"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Library, Search, LogOut, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/library", label: "Library", icon: Library },
  { href: "/research", label: "Research", icon: Search },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-parchment-50 dark:bg-ink-950">
        <Loader2 className="h-6 w-6 animate-spin text-ink-400" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-parchment-50 dark:bg-ink-950">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-ink-900 focus:px-4 focus:py-2 focus:text-parchment-50"
      >
        Skip to content
      </a>

      <aside className="flex w-56 shrink-0 flex-col border-r border-ink-200/70 bg-white/60 px-4 py-6 dark:border-ink-800 dark:bg-ink-900/40">
        <Link href="/library" className="mb-8 flex items-center gap-2 px-2 font-display text-lg font-medium text-ink-900 dark:text-parchment-50">
          <Library className="h-5 w-5 text-index-500" />
          Athenaeum
        </Link>

        <nav className="flex flex-1 flex-col gap-1" aria-label="Primary">
          {NAV.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-ink-900 text-parchment-50 dark:bg-parchment-100 dark:text-ink-900"
                    : "text-ink-600 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-ink-800"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto space-y-3 border-t border-ink-200/70 pt-4 dark:border-ink-800">
          <div className="flex items-center justify-between px-2">
            <span className="truncate text-xs text-ink-500 dark:text-ink-400">{user.email}</span>
            <ThemeToggle />
          </div>
          <button
            onClick={() => signOut()}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-800 dark:text-ink-400 dark:hover:bg-ink-800 dark:hover:text-ink-100"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      <main id="main-content" className="min-w-0 flex-1">
        {children}
      </main>
    </div>
  );
}
