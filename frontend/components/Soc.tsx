"use client";

import { Activity, AlertTriangle, CheckCircle2, Clock, Info, XCircle } from "lucide-react";

export function StatusBadge({ value }: { value: unknown }) {
  const text = humanize(value);
  const normalized = text.toLowerCase();
  const Icon = normalized.includes("fail") || normalized.includes("reject") || normalized.includes("missing") || normalized.includes("gap") || normalized.includes("unhealthy")
    ? XCircle
    : normalized.includes("running") || normalized.includes("pending") || normalized.includes("partial") || normalized.includes("changes")
      ? Clock
      : normalized.includes("succeed") || normalized.includes("ready") || normalized.includes("deploy") || normalized.includes("healthy") || normalized.includes("covered") || normalized.includes("visible") || normalized.includes("active")
        ? CheckCircle2
        : Info;
  const tone = normalized.includes("fail") || normalized.includes("reject") || normalized.includes("missing") || normalized.includes("gap") || normalized.includes("unhealthy")
    ? "border-danger/50 bg-danger/10 text-red-200"
    : normalized.includes("running") || normalized.includes("pending") || normalized.includes("partial") || normalized.includes("changes")
      ? "border-warning/50 bg-warning/10 text-amber-100"
      : normalized.includes("succeed") || normalized.includes("ready") || normalized.includes("deploy") || normalized.includes("healthy") || normalized.includes("covered") || normalized.includes("visible") || normalized.includes("active")
        ? "border-accent/50 bg-accent/10 text-emerald-100"
        : "border-border bg-slate-900 text-slate-300";
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${tone}`}><Icon className="h-3 w-3" />{text}</span>;
}

export function SeverityBadge({ value }: { value: unknown }) {
  const text = String(value ?? "medium");
  const tone = text.toLowerCase() === "critical" || text.toLowerCase() === "high"
    ? "border-danger/60 bg-danger/10 text-red-100"
    : text.toLowerCase() === "low"
      ? "border-accent/50 bg-accent/10 text-emerald-100"
      : "border-warning/50 bg-warning/10 text-amber-100";
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${tone}`}>{text}</span>;
}

export function Panel({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-md border border-border bg-panel/95 shadow-[0_20px_60px_rgba(0,0,0,0.18)]">
      <div className="flex min-h-11 items-center justify-between gap-3 border-b border-border px-3 py-2">
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {action}
      </div>
      <div className="min-w-0 p-3">{children}</div>
    </section>
  );
}

export function CodeBlock({ value, maxHeight = "24rem" }: { value: unknown; maxHeight?: string }) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2);
  return (
    <pre className="min-w-0 overflow-auto rounded-md border border-border bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-200" style={{ maxHeight }}>
      {text || "-"}
    </pre>
  );
}

export function Fact({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-slate-950/50 p-2">
      <div className="text-[11px] font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-medium text-slate-100" title={displayValue(value)}>{displayValue(value)}</div>
    </div>
  );
}

export function ActionButton({ children, tone = "neutral", disabled, onClick }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" | "bad"; disabled?: boolean; onClick?: () => void }) {
  const style = tone === "good"
    ? "border-accent bg-accent text-slate-950 hover:bg-accent/90"
    : tone === "warn"
      ? "border-warning text-warning hover:bg-warning/10"
      : tone === "bad"
        ? "border-danger text-danger hover:bg-danger/10"
        : "border-border text-slate-200 hover:bg-slate-800";
  return (
    <button disabled={disabled} onClick={onClick} className={`rounded-md border px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${style}`}>
      {children}
    </button>
  );
}

export function MetricCard({ label, value, detail, tone = "neutral" }: { label: string; value: React.ReactNode; detail?: string; tone?: "neutral" | "good" | "warn" | "bad" }) {
  const color = tone === "good" ? "text-accent" : tone === "warn" ? "text-warning" : tone === "bad" ? "text-danger" : "text-white";
  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${color}`}>{value}</div>
      {detail ? <div className="mt-1 text-xs text-slate-500">{detail}</div> : null}
    </div>
  );
}

export function MiniBars({ values, color = "#28d3a6" }: { values: number[]; color?: string }) {
  const max = Math.max(1, ...values);
  return (
    <div className="flex h-24 items-end gap-1">
      {values.map((value, index) => (
        <div className="flex-1 rounded-t-sm bg-slate-800" key={index}>
          <div className="rounded-t-sm" style={{ height: `${Math.max(8, (value / max) * 96)}px`, background: color }} />
        </div>
      ))}
    </div>
  );
}

export function Timeline({ items }: { items: Record<string, unknown>[] }) {
  if (items.length === 0) {
    return <div className="text-sm text-slate-500">No timeline events recorded.</div>;
  }
  return (
    <ol className="space-y-3">
      {items.map((item, index) => {
        const status = String(item.status ?? "succeeded").toLowerCase();
        const Icon = status.includes("fail") ? XCircle : status.includes("running") ? Clock : status.includes("pending") ? AlertTriangle : CheckCircle2;
        return (
          <li className="flex min-w-0 gap-3" key={String(item.id ?? index)}>
            <div className="mt-0.5">
              <Icon className={`h-4 w-4 ${status.includes("fail") ? "text-danger" : status.includes("running") || status.includes("pending") ? "text-warning" : "text-accent"}`} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate font-medium text-slate-100">{String(item.node_name ?? item.action ?? item.title ?? item.component ?? "Event")}</span>
                <span className="text-xs text-slate-500">{String(item.started_at ?? item.created_at ?? item.checked_at ?? "")}</span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <StatusBadge value={item.status ?? item.action ?? "recorded"} />
                {item.duration_ms != null ? <span>{String(item.duration_ms)} ms</span> : null}
                {item.retry_count != null ? <span>{String(item.retry_count)} retries</span> : null}
                {item.failure_reason ? <span className="text-danger">{String(item.failure_reason)}</span> : null}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-slate-950/40 p-6 text-sm">
      <div className="flex items-center gap-2 font-semibold text-slate-200"><Activity className="h-4 w-4 text-accent" />{title}</div>
      <p className="mt-2 text-slate-500">{detail}</p>
    </div>
  );
}

export function shortId(value: unknown) {
  return String(value ?? "").slice(0, 8);
}

export function displayValue(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.map(displayValue).join(", ") : "-";
  if (typeof value === "object") return "Available";
  return humanize(value);
}

export function humanize(value: unknown): string {
  return String(value ?? "unknown")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
