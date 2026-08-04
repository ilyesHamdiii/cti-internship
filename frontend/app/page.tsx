import Link from "next/link";
import { ArrowRight, CheckCircle2, FileCheck, GitBranch, RadioTower, ShieldCheck } from "lucide-react";

const steps = [
  ["MISP ingestion", "Pulls real MISP events through the MISP API and normalizes CTI evidence.", RadioTower],
  ["LangGraph workflow", "Extracts behavior, verifies ATT&CK, checks coverage and telemetry, then routes to a terminal outcome or proposal.", GitBranch],
  ["Detection proposal", "Uses the configured AI provider or deterministic fixture to draft Sigma candidates with repair history.", FileCheck],
  ["Validation and review", "Compiles with pySigma, records duplicate analysis, and requires analyst approval before catalog publication.", ShieldCheck],
];

export default function Home() {
  return (
    <main className="min-h-screen bg-background text-slate-100">
      <section className="mx-auto flex min-h-screen max-w-6xl flex-col justify-center px-5 py-10">
        <div className="max-w-3xl">
          <div className="text-xs font-semibold uppercase text-accent">CTI Detection Engineering Platform</div>
          <h1 className="mt-3 text-4xl font-semibold tracking-normal text-white md:text-5xl">From MISP intelligence to reviewed Sigma detections.</h1>
          <p className="mt-4 text-base leading-7 text-slate-400">
            A production-style demonstration of a detection engineering workflow: real MISP ingestion, LangGraph orchestration, deterministic policy gates,
            pySigma compilation, analyst review, deployment artifacts, and catalog publication.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link className="inline-flex items-center rounded-md border border-accent bg-accent px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-accent/90" href="/login">
              Open Demo <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
            <Link className="inline-flex items-center rounded-md border border-border px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-900" href="/dashboard">
              Dashboard
            </Link>
          </div>
        </div>

        <div className="mt-10 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {steps.map(([title, detail, Icon]) => (
            <article className="rounded-md border border-border bg-panel/95 p-4" key={title as string}>
              <Icon className="h-5 w-5 text-accent" />
              <h2 className="mt-3 text-sm font-semibold">{title as string}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">{detail as string}</p>
            </article>
          ))}
        </div>

        <div className="mt-6 grid gap-3 text-sm text-slate-400 md:grid-cols-3">
          <div className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-accent" /> Fixture mode is labeled when active.</div>
          <div className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-accent" /> AI output is gated by deterministic validation.</div>
          <div className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-accent" /> Approval is required before deployment.</div>
        </div>
      </section>
    </main>
  );
}
