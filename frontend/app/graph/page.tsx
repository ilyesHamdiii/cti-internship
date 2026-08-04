"use client";

import { useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { Page, apiGet } from "@/lib/api";
import { CodeBlock, EmptyState, Fact, Panel, StatusBadge, Timeline, humanize, shortId } from "@/components/Soc";

const graphOrder = [
  "consume_cti",
  "extract_behaviors",
  "verify_attack_mapping",
  "coverage_analysis",
  "visibility_analysis",
  "policy_decision",
  "generate_candidate",
  "validate_candidate",
  "repair_candidate",
  "queue_review",
  "approved",
  "deployment",
  "terminal_covered",
  "terminal_visibility_gap",
  "terminal_insufficient_evidence",
  "terminal_failed",
  "terminal_rejected",
  "advance_behavior",
];

export default function GraphPage() {
  const [runs, setRuns] = useState<Page | null>(null);
  const [timeline, setTimeline] = useState<Page | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedNodeName, setSelectedNodeName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Page>("/graph-runs")
      .then((result) => {
        setRuns(result);
        const first = result.items[0]?.id ? String(result.items[0].id) : null;
        setSelectedRunId(first);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    apiGet<Page>(`/graph-runs/${selectedRunId}/timeline`)
      .then((result) => {
        setTimeline(result);
        setSelectedNodeName(String(result.items[result.items.length - 1]?.node_name ?? graphOrder[0]));
      })
      .catch((err: Error) => setError(err.message));
  }, [selectedRunId]);

  const selectedRun = runs?.items.find((item) => String(item.id) === selectedRunId);
  const nodes = useMemo(() => timeline?.items ?? [], [timeline]);
  const byName = useMemo(() => new Map(nodes.map((node) => [String(node.node_name), node])), [nodes]);
  const selectedNode = nodes.find((node) => String(node.node_name) === selectedNodeName) ?? nodes[nodes.length - 1];
  const currentIndex = Math.max(0, graphOrder.indexOf(String(selectedRun?.current_node ?? "")));

  return (
    <Shell>
      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Workflow Graph</h1>
            <p className="mt-1 text-sm text-slate-500">LangGraph execution path with AI nodes, deterministic gates, skipped resume context, and terminal outcomes.</p>
          </div>
          <select className="max-w-full rounded-md border border-border bg-slate-950 px-3 py-2 text-sm" value={selectedRunId ?? ""} onChange={(event) => setSelectedRunId(event.target.value)}>
            {(runs?.items ?? []).map((run) => <option value={String(run.id)} key={String(run.id)}>{shortId(run.id)} / {String(run.status)} / {String(run.current_node ?? "complete")}</option>)}
          </select>
        </div>

        {error ? <div className="rounded-md border border-danger bg-red-950/30 p-3 text-sm text-red-200">{error}</div> : null}

        {!selectedRun ? <EmptyState title="No graph executions" detail="Ingest a MISP event, then run the detection workflow from Threat Queue." /> : (
          <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_24rem]">
            <div className="min-w-0 space-y-4">
              <Panel title={`Run ${shortId(selectedRun.id)}`} action={<StatusBadge value={selectedRun.status} />}>
                <div className="grid grid-cols-2 gap-2 text-sm lg:grid-cols-6">
                  <Fact label="Workflow" value={shortId(selectedRun.workflow_id)} />
                  <Fact label="CTI Event" value={shortId(selectedRun.cti_event_id)} />
                  <Fact label="Current Node" value={selectedRun.current_node ?? "complete"} />
                  <Fact label="Duration" value={`${String(selectedRun.duration_ms ?? 0)} ms`} />
                  <Fact label="Tokens" value={selectedRun.total_tokens ?? 0} />
                  <Fact label="Cost" value={`$${Number(selectedRun.estimated_cost ?? 0).toFixed(6)}`} />
                  <Fact label="Trigger" value={selectedRun.trigger_source} />
                  <Fact label="Terminal" value={selectedRun.terminal_result ?? selectedRun.failure_reason ?? "-"} />
                </div>
              </Panel>

              <Panel title="Workflow Nodes">
                <div className="grid min-w-0 gap-2 md:grid-cols-2 2xl:grid-cols-3">
                  {graphOrder.map((name, index) => {
                    const node = byName.get(name);
                    const status = nodeStatus(node, selectedRun, index, currentIndex);
                    const inherited = isInherited(node);
                    return (
                      <button className={`min-w-0 rounded-md border p-3 text-left transition ${selectedNodeName === name ? "border-accent bg-accent/10" : tone(status)}`} key={name} onClick={() => setSelectedNodeName(name)} title={nodeTooltip(name, node)}>
                        <div className="flex min-w-0 items-center justify-between gap-2">
                          <span className="truncate text-sm font-semibold">{index + 1}. {humanize(name)}</span>
                          <StatusBadge value={inherited ? "inherited" : status} />
                        </div>
                        <div className="mt-1 text-[11px] uppercase text-slate-500">{nodeKind(name)}</div>
                        <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-slate-500">
                          <span>{String(node?.duration_ms ?? 0)} ms</span>
                          <span>{String(node?.retry_count ?? 0)} retries</span>
                          <span>{node?.selected_route ? humanize(node.selected_route) : node ? "recorded" : "not run"}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </Panel>

              <Panel title="Selected Node Snapshot">
                <div className="mb-3 grid grid-cols-2 gap-2 text-sm lg:grid-cols-4">
                  <Fact label="Node" value={selectedNodeName} />
                  <Fact label="Status" value={isInherited(selectedNode) ? "inherited" : selectedNode?.status ?? "not_started"} />
                  <Fact label="Retries" value={selectedNode?.retry_count ?? 0} />
                  <Fact label="Route" value={selectedNode?.selected_route ?? "-"} />
                  <Fact label="AI" value={formatAiUsage(selectedNode?.ai_usage)} />
                  <Fact label="Failure" value={selectedNode?.failure_reason ?? "-"} />
                </div>
                {selectedNode?.proposal_id ? <a className="mb-3 inline-block rounded-md border border-border px-2 py-1 text-xs text-slate-300 hover:bg-slate-900" href="/reviews">Open Proposal</a> : null}
                <CodeBlock value={selectedNode?.output_snapshot ?? selectedNode?.input_snapshot ?? { status: "not_started" }} maxHeight="28rem" />
              </Panel>
            </div>

            <div className="min-w-0 space-y-4">
              <Panel title="Timeline">
                <div className="max-h-[38rem] overflow-auto pr-1"><Timeline items={nodes} /></div>
              </Panel>
            </div>
          </div>
        )}
      </section>
    </Shell>
  );
}

function nodeStatus(node: Record<string, unknown> | undefined, selectedRun: Record<string, unknown>, index: number, currentIndex: number) {
  if (node?.status) return String(node.status);
  if (selectedRun.status === "running" && selectedRun.current_node === graphOrder[index]) return "running";
  if (selectedRun.status !== "running" && index > currentIndex && currentIndex >= 0) return "not_started";
  return "not_started";
}

function isInherited(node: Record<string, unknown> | undefined) {
  const output = node?.output_snapshot as Record<string, unknown> | undefined;
  const input = node?.input_snapshot as Record<string, unknown> | undefined;
  return node?.status === "skipped" && (output?.inherited === true || input?.inherited === true);
}

function tone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("succeed")) return "border-accent/40 bg-accent/10 hover:bg-accent/15";
  if (normalized.includes("fail")) return "border-danger/50 bg-danger/10 hover:bg-danger/15";
  if (normalized.includes("running")) return "border-warning/60 bg-warning/10 hover:bg-warning/15";
  if (normalized.includes("skip")) return "border-sky-500/40 bg-sky-500/10 hover:bg-sky-500/15";
  return "border-border bg-slate-950/50 hover:bg-slate-900";
}

function formatAiUsage(value: unknown) {
  if (!value || typeof value !== "object") return "-";
  const usage = value as Record<string, unknown>;
  return `${String(usage.provider)} / ${String(usage.prompt_version)} / ${String(usage.tokens ?? 0)} tok / $${Number(usage.cost ?? 0).toFixed(6)}`;
}

function nodeKind(name: string) {
  if (["extract_behaviors", "generate_candidate", "repair_candidate"].includes(name)) return "AI provider";
  if (name.startsWith("terminal")) return "Terminal route";
  if (["coverage_analysis", "visibility_analysis", "policy_decision", "validate_candidate", "verify_attack_mapping"].includes(name)) return "Deterministic gate";
  if (["queue_review", "approved", "deployment"].includes(name)) return "Analyst lifecycle";
  return "Workflow";
}

function nodeTooltip(name: string, node: Record<string, unknown> | undefined) {
  const output = node?.output_snapshot as Record<string, unknown> | undefined;
  const route = node?.selected_route ? humanize(node.selected_route) : output?.policy_decision ? humanize(output.policy_decision) : "-";
  const ai = formatAiUsage(node?.ai_usage);
  return [
    humanize(name),
    `Kind: ${nodeKind(name)}`,
    `Status: ${humanize(node?.status ?? "not started")}`,
    `Route: ${route}`,
    `AI: ${ai}`,
    `Duration: ${String(node?.duration_ms ?? 0)} ms`,
    output?.terminal_status ? `Terminal: ${humanize(output.terminal_status)}` : "",
    node?.failure_reason ? `Failure: ${String(node.failure_reason)}` : "",
  ].filter(Boolean).join("\n");
}
