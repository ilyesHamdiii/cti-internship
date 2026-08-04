"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import { ActionButton, CodeBlock, EmptyState, Fact, Panel, StatusBadge, humanize, shortId } from "@/components/Soc";

type Dashboard = {
  current_session: Record<string, unknown> | null;
  watcher_status: Record<string, number>;
  watchers: Record<string, unknown>[];
  revisions: Record<string, unknown>[];
  confidence_timeline: Record<string, unknown>[];
  trust_timeline?: Record<string, unknown>[];
  limits?: Record<string, unknown>;
  provider: string | null;
  model: string | null;
  tokens: number;
  latency_ms: number | null;
  termination_reason: string | null;
  consumption: Record<string, unknown>;
};

export default function AiDashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    setData(await apiGet<Dashboard>("/ai/dashboard"));
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  const session = data?.current_session;
  const consumption = data?.consumption as Record<string, unknown> | undefined;
  const counts = consumption?.counts as Record<string, unknown> | undefined;

  return (
    <Shell>
      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">AI Dashboard</h1>
            <p className="mt-1 text-sm text-slate-500">Structured AI session state, guardrails, confidence, trust, and MISP consumption telemetry.</p>
          </div>
          <ActionButton onClick={() => void load()}><RefreshCw className="mr-2 inline h-4 w-4" />Refresh</ActionButton>
        </div>

        {error ? <div className="rounded-md border border-danger bg-red-950/30 p-3 text-sm text-red-200">{error}</div> : null}

        {!data ? <Skeleton /> : !session ? <EmptyState title="No AI sessions yet" detail="Ingest a MISP event and run the workflow to create a reasoning session." /> : (
          <>
            <Panel title={`Current Session ${shortId(session.id)}`} action={<StatusBadge value={session.status} />}>
              <div className="grid grid-cols-2 gap-2 text-sm lg:grid-cols-6">
                <Fact label="Current Node" value={session.current_node} />
                <Fact label="Revision" value={session.current_revision} />
                <Fact label="Revision Count" value={data.revisions.length} />
                <Fact label="Confidence" value={Number(session.confidence_score ?? 0).toFixed(2)} />
                <Fact label="Confidence Target" value={data.limits?.confidence_target ?? "-"} />
                <Fact label="Trust" value={Number(session.trust_score ?? 0).toFixed(2)} />
                <Fact label="Trust Target" value={data.limits?.trust_target ?? "-"} />
                <Fact label="Recommendation" value={session.approval_recommendation} />
                <Fact label="Termination" value={data.termination_reason ?? "-"} />
                <Fact label="Provider" value={data.provider ?? "-"} />
                <Fact label="Model" value={data.model ?? "-"} />
                <Fact label="Tokens" value={data.tokens} />
                <Fact label="Latency" value={data.latency_ms == null ? "-" : `${data.latency_ms} ms`} />
              </div>
            </Panel>

            <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_22rem]">
              <div className="space-y-4">
                <Panel title="AI Watchers" action={<StatusBadge value={`${Object.values(data.watcher_status ?? {}).reduce((a, b) => a + b, 0)} checks`} />}>
                  <div className="mb-3 grid grid-cols-3 gap-2 text-sm">
                    <Fact label="Pass" value={data.watcher_status.PASS ?? 0} />
                    <Fact label="Warning" value={data.watcher_status.WARNING ?? 0} />
                    <Fact label="Fail" value={data.watcher_status.FAIL ?? 0} />
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    {(data.watchers ?? []).slice(0, 12).map((watcher) => (
                      <div className="rounded-md border border-border bg-slate-950/50 p-3" key={String(watcher.id)}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm font-semibold">{humanize(watcher.watcher_name)}</span>
                          <StatusBadge value={watcher.status} />
                        </div>
                        <div className="mt-2 text-xs text-slate-400">{String(watcher.message ?? "")}</div>
                      </div>
                    ))}
                  </div>
                </Panel>

                <Panel title="Revision Timeline">
                  {data.revisions.length === 0 ? <EmptyState title="No revisions" detail="The workflow has not reached validation yet." /> : (
                    <div className="space-y-2">
                      {data.revisions.map((revision) => (
                        <div className="rounded-md border border-border bg-slate-950/50 p-3" key={String(revision.id)}>
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold">Revision {String(revision.revision_number)} / {humanize(revision.stage)}</span>
                            <StatusBadge value={revision.termination_reason ?? revision.reason} />
                          </div>
                          <div className="mt-2 grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
                            <Fact label="Before" value={revision.confidence_before == null ? "-" : Number(revision.confidence_before).toFixed(2)} />
                            <Fact label="After" value={Number(revision.confidence_after ?? 0).toFixed(2)} />
                            <Fact label="Delta" value={Number(revision.confidence_delta ?? 0).toFixed(2)} />
                            <Fact label="Reason" value={revision.reason} />
                            <Fact label="Route" value={revision.route_selected ?? "-"} />
                            <Fact label="Decision" value={revision.stopping_decision ?? "-"} />
                            <Fact label="Trust" value={revision.trust_score == null ? "-" : Number(revision.trust_score).toFixed(2)} />
                            <Fact label="Recommendation" value={revision.recommendation ?? "-"} />
                          </div>
                          <div className="mt-2 text-xs text-slate-400">{Array.isArray(revision.changed_fields) ? `Changed: ${revision.changed_fields.join(", ") || "-"}` : null}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
              </div>

              <div className="space-y-4">
                <Panel title="MISP Consumption" action={<StatusBadge value={String(consumption?.polling_status ?? "unknown")} />}>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <Fact label="Last Poll" value={consumption?.last_misp_poll} />
                    <Fact label="Next Poll" value={consumption?.next_scheduled_poll} />
                    <Fact label="Interval" value={`${String(consumption?.poll_interval_seconds ?? 0)}s`} />
                    <Fact label="Scheduler" value={consumption?.scheduler_status} />
                    <Fact label="Consumed" value={counts?.consumed ?? 0} />
                    <Fact label="Duplicate" value={counts?.duplicate ?? 0} />
                    <Fact label="Skipped" value={counts?.skipped ?? 0} />
                    <Fact label="Failed" value={counts?.failed ?? 0} />
                  </div>
                </Panel>
                <Panel title="Session Memory">
                  <CodeBlock value={session.session_summary} maxHeight="28rem" />
                </Panel>
                <Panel title="Trust Progression">
                  <CodeBlock value={data.trust_timeline ?? []} maxHeight="14rem" />
                </Panel>
              </div>
            </div>
          </>
        )}
      </section>
    </Shell>
  );
}

function Skeleton() {
  return <div className="h-32 animate-pulse rounded-md border border-border bg-slate-950/60" />;
}
