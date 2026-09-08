"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Search,
  BookMarked,
  Highlighter,
  FolderKanban,
  MoveRight,
  Library,
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/lib/auth-context";

const FEATURES = [
  {
    icon: Search,
    title: "Fast, hybrid search",
    body: "Vector and keyword search run together, so an exact name or acronym surfaces just as reliably as a loosely-worded question.",
  },
  {
    icon: Highlighter,
    title: "Evidence, not guesses",
    body: "Every answer carries citations that jump straight to the source page and highlight the sentence that backs the claim.",
  },
  {
    icon: FolderKanban,
    title: "Collections that hold up",
    body: "Group documents the way your library actually works — by course, department, or shelf — not a flat, unsorted pile.",
  },
  {
    icon: BookMarked,
    title: "Built for a real reading room",
    body: "Multiple staff, one shared library, one shared index. No per-device setup, no accounts syncing separately.",
  },
];

const STEPS = [
  { n: "01", title: "Sign in", body: "Google or email — your library account, verified." },
  { n: "02", title: "Upload", body: "Drag in one PDF or a whole folder. Duplicates are caught automatically." },
  { n: "03", title: "Organize", body: "Sort into collections as the library fills in." },
  { n: "04", title: "Ask", body: "Pose a real research question in plain language." },
  { n: "05", title: "Read the evidence", body: "Click any citation to land on the exact page, highlighted." },
];

export default function LandingPage() {
  const { user } = useAuth();
  const stackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let ctx: gsap.Context | undefined;
    (async () => {
      const { gsap } = await import("gsap");
      if (!stackRef.current) return;
      ctx = gsap.context(() => {
        gsap.set(".doc-card", { opacity: 0, y: 40, rotate: 0 });
        gsap.to(".doc-card", {
          opacity: 1,
          y: 0,
          rotate: (i: number) => [-6, 3, -2, 5][i] ?? 0,
          duration: 0.9,
          ease: "power3.out",
          stagger: 0.12,
          delay: 0.2,
        });
      }, stackRef);
    })();
    return () => ctx?.revert();
  }, []);

  return (
    <div className="min-h-screen bg-parchment-50 dark:bg-ink-950">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2 font-display text-lg font-medium tracking-tight">
          <Library className="h-5 w-5 text-index-500" />
          Athenaeum
        </div>
        <nav className="flex items-center gap-3">
          <ThemeToggle />
          {user ? (
            <Link
              href="/library"
              className="rounded-full bg-ink-900 px-4 py-2 text-sm font-medium text-parchment-50 transition-colors hover:bg-ink-700 dark:bg-parchment-100 dark:text-ink-900 dark:hover:bg-white"
            >
              Go to library
            </Link>
          ) : (
            <Link
              href="/login"
              className="rounded-full bg-ink-900 px-4 py-2 text-sm font-medium text-parchment-50 transition-colors hover:bg-ink-700 dark:bg-parchment-100 dark:text-ink-900 dark:hover:bg-white"
            >
              Sign in
            </Link>
          )}
        </nav>
      </header>

      {/* Hero */}
      <section className="mx-auto grid max-w-6xl gap-12 px-6 pb-24 pt-12 md:grid-cols-2 md:items-center md:pt-20">
        <div>
          <h1 className="text-balance font-display text-4xl leading-[1.1] tracking-tight text-ink-900 dark:text-parchment-50 md:text-5xl">
            A research library that <em className="not-italic text-index-600 dark:text-index-400">shows its work</em>.
          </h1>
          <p className="mt-6 max-w-md text-lg leading-relaxed text-ink-600 dark:text-ink-300">
            Upload the collection. Ask a real question. Get an answer with citations
            that land on the exact page — every time.
          </p>
          <div className="mt-8 flex items-center gap-4">
            <Link
              href={user ? "/library" : "/register"}
              className="group inline-flex items-center gap-2 rounded-full bg-index-500 px-6 py-3 text-sm font-medium text-ink-950 transition-colors hover:bg-index-400"
            >
              {user ? "Open your library" : "Start a library"}
              <MoveRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="#how-it-works"
              className="text-sm font-medium text-ink-600 underline decoration-ink-300 underline-offset-4 hover:text-ink-900 dark:text-ink-300 dark:hover:text-parchment-50"
            >
              See how it works
            </Link>
          </div>
        </div>

        <div ref={stackRef} className="relative mx-auto h-72 w-full max-w-sm">
          {[
            { top: "10%", left: "8%", label: "Diocesan Report.pdf" },
            { top: "22%", left: "34%", label: "Kelly Criterion — Notes.pdf" },
            { top: "6%", left: "52%", label: "Yoruba NLP Corpus.pdf" },
            { top: "38%", left: "20%", label: "CPE 316 — Lab 43.pdf" },
          ].map((c, i) => (
            <div
              key={c.label}
              className="doc-card absolute w-48 rounded-lg border border-ink-200 bg-white p-4 shadow-card dark:border-ink-700 dark:bg-ink-900"
              style={{ top: c.top, left: c.left, zIndex: i }}
            >
              <div className="mb-2 h-1.5 w-8 rounded-full bg-index-400" />
              <p className="truncate font-display text-sm text-ink-800 dark:text-ink-100">{c.label}</p>
              <div className="mt-3 space-y-1.5">
                <div className="h-1.5 w-full rounded-full bg-ink-100 dark:bg-ink-700" />
                <div className="h-1.5 w-4/5 rounded-full bg-ink-100 dark:bg-ink-700" />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="border-y border-ink-200/60 bg-white/60 py-20 dark:border-ink-800 dark:bg-ink-900/40">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="max-w-lg font-display text-3xl tracking-tight text-ink-900 dark:text-parchment-50">
            Built for people who need the source, not just the summary.
          </h2>
          <div className="mt-12 grid gap-8 sm:grid-cols-2">
            {FEATURES.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ duration: 0.5, delay: i * 0.06 }}
                className="rounded-2xl border border-ink-200/70 bg-parchment-50 p-6 dark:border-ink-800 dark:bg-ink-950"
              >
                <f.icon className="h-5 w-5 text-index-600 dark:text-index-400" />
                <h3 className="mt-4 font-display text-lg text-ink-900 dark:text-parchment-50">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-600 dark:text-ink-400">{f.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="font-display text-3xl tracking-tight text-ink-900 dark:text-parchment-50">
          From upload to evidence, in five steps.
        </h2>
        <div className="mt-12 grid gap-8 md:grid-cols-5">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
            >
              <span className="font-display text-sm text-index-500">{s.n}</span>
              <h3 className="mt-2 font-display text-base text-ink-900 dark:text-parchment-50">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-600 dark:text-ink-400">{s.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <div className="rounded-3xl bg-ink-900 px-8 py-14 text-center dark:bg-ink-900/80">
          <h2 className="mx-auto max-w-lg font-display text-3xl tracking-tight text-parchment-50">
            Give your library a memory it can cite.
          </h2>
          <Link
            href={user ? "/library" : "/register"}
            className="mt-8 inline-flex items-center gap-2 rounded-full bg-index-500 px-6 py-3 text-sm font-medium text-ink-950 transition-colors hover:bg-index-400"
          >
            {user ? "Open your library" : "Create your library"}
            <MoveRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <footer className="mx-auto max-w-6xl px-6 pb-10 text-sm text-ink-500 dark:text-ink-500">
        Athenaeum — a research library, not a search engine.
      </footer>
    </div>
  );
}
