"use client";

import { useEffect, useState } from "react";
import { ArrowDown, RefreshCw } from "lucide-react";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import { ActionButton, EmptyState, Fact, Panel, StatusBadge, humanize, shortId } from "@/components/Soc";

type WorkflowPayload = {
  graph_run: Record<string, unknown> | null;
  session: Record<string, unknown> | null;
  routes: Record<string, unknown>;
  limits: Record<string, unknown>;
  nodes: Record<string, unknown>[];
};

export default function AiWorkflowPage() {
  const [data, setData] = useState<WorkflowPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    setData(await apiGet<WorkflowPayload>("/ai/workflow"));
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  return (
    <Shell>
      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">AI Workflow Architecture</h1>
            <p className="mt-1 text-sm text-slate-500">MISP ingestion through bounded AI revision, deterministic validation, review, deployment, and catalog publication.</p>
          </div>
          <ActionButton onClick={() => void load()}><RefreshCw className="mr-2 inline h-4 w-4" />Refresh</ActionButton>
        </div>

        {error ? <div className="rounded-md border border-danger bg-red-950/30 p-3 text-sm text-red-200">{error}</div> : null}

        {!data ? <Skeleton /> : data.nodes.length === 0 ? <EmptyState title="No workflow metadata" detail="The API returned no workflow nodes." /> : (
          <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_22rem]">
            <div className="min-w-0">
              <Panel title={data.graph_run ? `Latest Run ${shortId(data.graph_run.id)}` : "Workflow Blueprint"} action={<StatusBadge value={data.graph_run?.status ?? "blueprint"} />}>
                <div className="space-y-2">
                  {data.nodes.map((node, index) => (
                    <div key={`${String(node.node)}-${String(node.stage ?? index)}`}>
                      <div className={`rounded-md border p-3 ${tone(String(node.executor), String(node.status))}`}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-semibold">{index + 1}. {humanize(node.stage ?? node.node)}</div>
                            <div className="mt-1 text-xs uppercase text-slate-500">{humanize(node.executor)}</div>
                          </div>
                          <StatusBadge value={node.status} />
                        </div>
                        <div className="mt-3 text-sm text-slate-300">{String(node.purpose)}</div>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-sm lg:grid-cols-5">
                          <Fact label="Input" value={node.input} />
                          <Fact label="Output" value={node.output} />
                          <Fact label="Runtime Map" value={node.runtime_mapping ?? node.node} />
                          <Fact label="Time" value={node.execution_time_ms == null ? "-" : `${String(node.execution_time_ms)} ms`} />
                          <Fact label="Confidence" value={node.confidence == null ? "-" : Number(node.confidence).toFixed(2)} />
                          <Fact label="Watchers" value={`${String(node.watcher_failures ?? 0)} fail / ${String(node.watcher_warnings ?? 0)} warn`} />
                        </div>
                      </div>
                      {index < data.nodes.length - 1 ? <div className="flex justify-center py-1 text-slate-600"><ArrowDown className="h-4 w-4" /></div> : null}
                    </div>
                  ))}
                </div>
              </Panel>
            </div>

            <div className="space-y-4">
              <Panel title="Bounded Loop Controls">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <Fact label="Max Revisions" value={data.limits.max_revisions} />
                  <Fact label="Max Repairs" value={data.limits.max_repair_attempts} />
                  <Fact label="Min Delta" value={data.limits.min_improvement_delta} />
                  <Fact label="Confidence Target" value={data.limits.confidence_target} />
                  <Fact label="Trust Target" value={data.limits.trust_target} />
                </div>
              </Panel>
              <Panel title="Legend">
                <div className="space-y-2 text-sm text-slate-300">
                  {["AI Operation", "Deterministic Watcher", "Deterministic Validator", "Scoring Gate", "Policy Gate", "Analyst Action", "Terminal State"].map((item) => (
                    <div className="rounded-md border border-border bg-slate-950/50 p-2" key={item}>{item}</div>
                  ))}
                </div>
              </Panel>
              <Panel title="Routing">
                <div className="space-y-2 text-sm">
                  {Object.entries(data.routes).map(([key, value]) => (
                    <div className="rounded-md border border-border bg-slate-950/50 p-2" key={key}>
                      <div className="text-xs uppercase text-slate-500">{humanize(key)}</div>
                      <div className="mt-1 text-slate-200">{String(value)}</div>
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel title="Current Session" action={<StatusBadge value={data.session?.status ?? "none"} />}>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <Fact label="Session" value={shortId(data.session?.id)} />
                  <Fact label="Node" value={data.session?.current_node} />
                  <Fact label="Confidence" value={data.session?.confidence_score == null ? "-" : Number(data.session.confidence_score).toFixed(2)} />
                  <Fact label="Trust" value={data.session?.trust_score == null ? "-" : Number(data.session.trust_score).toFixed(2)} />
                  <Fact label="Decision" value={data.session?.approval_recommendation} />
                  <Fact label="Reason" value={data.session?.termination_reason} />
                </div>
              </Panel>
            </div>
          </div>
        )}
      </section>
    </Shell>
  );
}

function tone(executor: string, status: string) {
  if (status.toLowerCase().includes("fail")) return "border-danger/50 bg-danger/10";
  if (executor === "ai") return "border-sky-500/40 bg-sky-500/10";
  if (executor.includes("watcher")) return "border-cyan-500/40 bg-cyan-500/10";
  if (executor.includes("validator")) return "border-emerald-500/40 bg-emerald-500/10";
  if (executor.includes("scoring")) return "border-warning/40 bg-warning/10";
  if (executor.includes("policy")) return "border-purple-500/40 bg-purple-500/10";
  if (executor === "human") return "border-fuchsia-500/40 bg-fuchsia-500/10";
  if (executor === "terminal") return "border-danger/50 bg-danger/10";
  return "border-border bg-slate-950/50";
}

function Skeleton() {
  return <div className="h-64 animate-pulse rounded-md border border-border bg-slate-950/60" />;
}
