"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Brain, FileCheck, GitBranch, RadioTower, ShieldCheck } from "lucide-react";
import { Shell } from "@/components/Shell";
import { apiGet, Page } from "@/lib/api";
import { MetricCard, MiniBars, Panel, StatusBadge, Timeline, shortId } from "@/components/Soc";

type Summary = {
  pending_cti: number;
  running_graphs: number;
  queued_reviews: number;
  coverage_percent: number;
  visibility_percent: number;
  average_confidence: number;
  average_cost: number;
  average_runtime_ms: number;
};

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [threats, setThreats] = useState<Page | null>(null);
  const [runs, setRuns] = useState<Page | null>(null);
  const [proposals, setProposals] = useState<Page | null>(null);
  const [health, setHealth] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Summary>("/dashboard/summary").then(setSummary).catch((err: Error) => setError(err.message));
    apiGet<Page>("/cti-events").then(setThreats).catch(() => undefined);
    apiGet<Page>("/automation-runs").then(setRuns).catch(() => undefined);
    apiGet<Page>("/proposals").then(setProposals).catch(() => undefined);
    apiGet<Page>("/system-health").then(setHealth).catch(() => undefined);
  }, []);

  const today = new Date().toISOString().slice(0, 10);
  const threatItems = useMemo(() => threats?.items ?? [], [threats]);
  const runItems = useMemo(() => runs?.items ?? [], [runs]);
  const proposalItems = useMemo(() => proposals?.items ?? [], [proposals]);
  const threatsToday = threatItems.filter((item) => String(item.received_at ?? "").startsWith(today)).length;
  const failedRuns = runItems.filter((item) => String(item.status).toLowerCase().includes("fail")).length;
  const durations = runItems.slice().reverse().map((item) => Number(item.duration_ms ?? 0));
  const generatedTrend = proposalItems.slice().reverse().map((_, index) => index + 1);

  const latestReview = proposalItems.slice(0, 4);
  const recentTimeline = useMemo(() => runItems.slice(0, 6).map((item) => ({
    id: item.id,
    node_name: `Workflow ${shortId(item.workflow_id)} reached ${String(item.current_node ?? "pending")}`,
    status: item.status,
    started_at: item.finished_at ?? item.started_at,
    duration_ms: item.duration_ms,
  })), [runItems]);

  return (
    <Shell>
      <section className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Detection Engineering Demo</h1>
            <p className="mt-1 text-sm text-slate-500">MISP CTI is converted into behavior records, graph decisions, Sigma proposals, and analyst-approved catalog entries.</p>
          </div>
          {error ? <div className="rounded-md border border-danger bg-red-950/30 px-3 py-2 text-sm text-red-200">{error}</div> : null}
        </div>

        <div className="grid grid-cols-4 gap-3">
          <MetricCard label="Threats Processed Today" value={threatsToday} detail={`${threatItems.length} total ingested`} tone="good" />
          <MetricCard label="Behaviors Extracted" value={threatItems.reduce((sum, item) => sum + Number(item.behavior_count ?? 0), 0)} detail="from normalized CTI" />
          <MetricCard label="Sigma Proposals" value={proposalItems.length} detail="generated candidates" tone="good" />
          <MetricCard label="Validated Detections" value={proposalItems.filter((item) => Number(item.quality_score ?? 0) >= 75).length} detail="quality gate passed" tone="good" />
          <MetricCard label="Coverage" value={`${Math.round(summary?.coverage_percent ?? 0)}%`} detail="existing catalog overlap" tone={(summary?.coverage_percent ?? 0) > 50 ? "good" : "warn"} />
          <MetricCard label="Visibility" value={`${Math.round(summary?.visibility_percent ?? 0)}%`} detail="telemetry available" tone={(summary?.visibility_percent ?? 0) > 80 ? "good" : "warn"} />
          <MetricCard label="Running Workflows" value={summary?.running_graphs ?? 0} detail="currently executing" />
          <MetricCard label="Pending Reviews" value={summary?.queued_reviews ?? 0} detail="ready for analyst action" tone={(summary?.queued_reviews ?? 0) > 0 ? "warn" : "neutral"} />
          <MetricCard label="Avg Duration" value={`${Math.round(summary?.average_runtime_ms ?? 0)} ms`} detail="graph runtime" />
          <MetricCard label="Avg Candidate Confidence" value={(summary?.average_confidence ?? 0).toFixed(2)} detail="AI or fixture provider output" />
          <MetricCard label="Avg Provider Cost" value={`$${(summary?.average_cost ?? 0).toFixed(5)}`} detail="per proposal revision" />
          <MetricCard label="Failed Workflows" value={failedRuns} detail="needs triage" tone={failedRuns > 0 ? "bad" : "good"} />
        </div>

        <div className="grid grid-cols-4 gap-4">
          <Panel title="Threat Ingestion"><MiniBars values={threatItems.length ? threatItems.map((_, i) => i + 1) : [0]} /></Panel>
          <Panel title="Workflow Duration"><MiniBars values={durations.length ? durations : [0]} color="#f6c453" /></Panel>
          <Panel title="Coverage Trend"><MiniBars values={[Math.round(summary?.coverage_percent ?? 0), Math.round(summary?.visibility_percent ?? 0)]} color="#5ea1ff" /></Panel>
          <Panel title="Proposal Generation"><MiniBars values={generatedTrend.length ? generatedTrend : [0]} color="#28d3a6" /></Panel>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <Panel title="Recent Activity">
            <Timeline items={recentTimeline} />
          </Panel>
          <Panel title="Latest Review Requests">
            <div className="space-y-3">
              {latestReview.length === 0 ? <p className="text-sm text-slate-500">No proposals are awaiting review.</p> : latestReview.map((item) => (
                <div className="rounded-md border border-border bg-slate-950/50 p-3" key={String(item.id)}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm font-medium">{String(item.behavior_summary ?? item.id)}</span>
                    <StatusBadge value={item.status} />
                  </div>
                  <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
                    <FileCheck className="h-3.5 w-3.5" /> rev {String(item.current_revision_number)}
                    <Brain className="h-3.5 w-3.5" /> {String(item.confidence)}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="System Health">
            <div className="grid gap-2">
              {(health?.items ?? []).slice(0, 8).map((item) => (
                <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-slate-950/50 px-3 py-2 text-sm" key={String(item.component)}>
                  <span>{String(item.component)}</span>
                  <StatusBadge value={item.status} />
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <div className="grid grid-cols-4 gap-3 text-xs text-slate-500">
          <div className="flex items-center gap-2"><RadioTower className="h-4 w-4 text-accent" /> MISP ingestion source</div>
          <div className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-accent" /> persisted graph audit trail</div>
          <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-accent" /> deterministic validation</div>
          <div className="flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-warning" /> analyst approval gate</div>
        </div>
      </section>
    </Shell>
  );
}
