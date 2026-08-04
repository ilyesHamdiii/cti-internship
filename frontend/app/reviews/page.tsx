"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import { Shell } from "@/components/Shell";
import { ApiError, Page, apiDownload, apiGet, apiPost } from "@/lib/api";
import { ActionButton, CodeBlock, EmptyState, Fact, Panel, StatusBadge, Timeline, shortId } from "@/components/Soc";

type Workspace = {
  proposal: Record<string, unknown>;
  cti_event: Record<string, unknown> | null;
  workflow: Record<string, unknown> | null;
  behavior: Record<string, unknown> | null;
  attack_mappings: Record<string, unknown>[];
  coverage_results: Record<string, unknown>[];
  visibility_results: Record<string, unknown>[];
  revisions: Record<string, unknown>[];
  validation_results: Record<string, unknown>[];
  review_actions: Record<string, unknown>[];
  graph_runs: Record<string, unknown>[];
  deployment_artifacts: Record<string, unknown>[];
  policy_decisions: Record<string, unknown>[];
  ai_interactions: Record<string, unknown>[];
};

export default function ReviewsPage() {
  const [data, setData] = useState<Page | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async (proposalId?: string | null) => {
    setError(null);
    const result = await apiGet<Page>("/proposals");
    setData(result);
    const next = proposalId ?? (result.items[0]?.id ? String(result.items[0].id) : null);
    setSelected(next);
    setWorkspace(next ? await apiGet<Workspace>(`/proposals/${next}/workspace`) : null);
  }, []);

  useEffect(() => {
    load().catch((err) => setError(formatError(err, "Failed to load proposals")));
  }, [load]);

  async function choose(proposalId: string) {
    setSelected(proposalId);
    setError(null);
    try {
      setWorkspace(await apiGet<Workspace>(`/proposals/${proposalId}/workspace`));
    } catch (err) {
      setError(formatError(err, "Failed to load workspace"));
    }
  }

  async function act(action: "approve" | "reject" | "request-changes") {
    if (!workspace || !selected) return;
    const revision = workspace.proposal.current_revision_number;
    let comment = "";
    if (action === "request-changes") {
      comment = window.prompt("Describe the required Sigma change") ?? "";
      if (!comment.trim()) return;
    }
    if (action === "reject" && !window.confirm("Reject this proposal and stop deployment?")) return;
    setBusy(action);
    setError(null);
    setMessage(null);
    try {
      const result = await apiPost<Record<string, unknown>>(`/proposals/${selected}/${action}`, { revision_number: revision, comment });
      setMessage(`${actionLabel(action)} completed / graph ${shortId(result.graph_run_id)}${result.artifact_id ? ` / artifact ${shortId(result.artifact_id)}` : ""}`);
      await load(selected);
    } catch (err) {
      setError(formatError(err, `${actionLabel(action)} failed`));
    } finally {
      setBusy(null);
    }
  }

  async function downloadArtifact(artifactId: unknown) {
    if (!artifactId) return;
    setBusy("download");
    setError(null);
    try {
      await apiDownload(`/deployment-artifacts/${artifactId}/download`, `deployment-${String(artifactId)}.yml`);
      setMessage(`Downloaded artifact ${shortId(artifactId)}`);
    } catch (err) {
      setError(formatError(err, "Download failed"));
    } finally {
      setBusy(null);
    }
  }

  const currentRevision = workspace?.revisions[workspace.revisions.length - 1];
  const currentValidation = workspace?.validation_results[workspace.validation_results.length - 1];
  const compiledOutputs = currentValidation?.compiled_outputs as Record<string, unknown> | undefined;
  const compiledQuery = compiledOutputs?.query ?? compiledOutputs ?? {};
  const duplicateResult = compiledOutputs?.duplicate_result as Record<string, unknown> | undefined;
  const previousRevision = workspace && workspace.revisions.length > 1 ? workspace.revisions[workspace.revisions.length - 2] : null;
  const latestRepair = workspace?.ai_interactions.filter((item) => item.prompt_version === "sigma_repair_v2").slice(-1)[0];
  const canReview = workspace?.proposal.status === "ready_review";

  const timeline = useMemo(() => [
    ...(workspace?.graph_runs ?? []).map((run) => ({
      id: run.id,
      node_name: `Graph ${shortId(run.id)} / ${String(run.current_node ?? "completed")}`,
      status: run.status,
      started_at: run.finished_at ?? run.started_at,
      duration_ms: run.duration_ms,
    })),
    ...(workspace?.review_actions ?? []).map((action) => ({
      id: action.id,
      node_name: `Analyst ${String(action.action)}`,
      status: action.action,
      started_at: action.created_at,
    })),
    ...(workspace?.deployment_artifacts ?? []).map((artifact) => ({
      id: artifact.id,
      node_name: `Deployment artifact ${shortId(artifact.id)}`,
      status: "deployed",
      started_at: artifact.created_at,
    })),
  ], [workspace]);

  return (
    <Shell>
      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Review Workspace</h1>
            <p className="mt-1 text-sm text-slate-500">Approve, reject, or request immutable Sigma revisions from graph-generated proposals.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <ActionButton disabled={busy != null || !workspace || !canReview} tone="good" onClick={() => void act("approve")}><CheckCircle2 className="mr-2 inline h-4 w-4" />Approve</ActionButton>
            <ActionButton disabled={busy != null || !workspace || !canReview} tone="warn" onClick={() => void act("request-changes")}><RotateCcw className="mr-2 inline h-4 w-4" />Request Changes</ActionButton>
            <ActionButton disabled={busy != null || !workspace || !["ready_review", "changes_requested"].includes(String(workspace?.proposal.status))} tone="bad" onClick={() => void act("reject")}><XCircle className="mr-2 inline h-4 w-4" />Reject</ActionButton>
          </div>
        </div>

        {message ? <div className="rounded-md border border-accent/50 bg-accent/10 p-3 text-sm text-emerald-100">{message}</div> : null}
        {error ? <div className="rounded-md border border-danger bg-red-950/30 p-3 text-sm text-red-200">{error}</div> : null}

        <div className="grid min-w-0 gap-4 xl:grid-cols-[22rem_1fr]">
          <Panel title="Proposal Queue" action={<StatusBadge value={data ? `${data.total} proposals` : "loading"} />}>
            {!data ? <Skeleton /> : data.items.length === 0 ? (
              <EmptyState title="No proposals" detail="Run a CTI workflow from the Threat Queue to generate a candidate Sigma proposal." />
            ) : (
              <div className="max-h-[42rem] space-y-2 overflow-auto pr-1">
                {data.items.map((item) => (
                  <button key={String(item.id)} onClick={() => void choose(String(item.id))} className={`w-full rounded-md border p-3 text-left ${selected === item.id ? "border-accent bg-accent/10" : "border-border bg-slate-950/50 hover:bg-slate-900"}`}>
                    <div className="flex min-w-0 items-center justify-between gap-3">
                      <span className="truncate text-sm font-semibold">{String(item.behavior_summary ?? item.id)}</span>
                      <div className="flex shrink-0 items-center gap-2">
                        {Number(item.duplicate_count ?? 1) > 1 ? <StatusBadge value={`merged ${item.duplicate_count}`} /> : null}
                        <StatusBadge value={item.status} />
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-slate-500">
                      <span>rev {String(item.current_revision_number)}</span>
                      <span>Q {String(item.quality_score ?? "-")}</span>
                      <span>{Array.isArray(item.attack_techniques) ? item.attack_techniques.join(", ") : "-"}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Panel>

          {!workspace ? (
            <Panel title="Proposal Details"><EmptyState title="No proposal selected" detail="Select a proposal to inspect Sigma YAML, validation, and graph history." /></Panel>
          ) : (
            <div className="min-w-0 space-y-4">
              <Panel title="Threat Summary" action={<StatusBadge value={workspace.proposal.status} />}>
                <div className="grid grid-cols-2 gap-2 text-sm lg:grid-cols-6">
                  <Fact label="MISP Event" value={workspace.cti_event?.misp_event_id} />
                  <Fact label="Workflow" value={shortId(workspace.workflow?.id)} />
                  <Fact label="Proposal" value={shortId(workspace.proposal.id)} />
                  <Fact label="Revision" value={workspace.proposal.current_revision_number} />
                  <Fact label="Confidence" value={workspace.proposal.confidence} />
                  <Fact label="Quality" value={workspace.proposal.quality_score} />
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-300">{String(workspace.behavior?.summary ?? workspace.cti_event?.title ?? "No behavior summary available.")}</p>
              </Panel>

              <div className="grid min-w-0 gap-4 lg:grid-cols-[1fr_24rem]">
                <Panel title="Sigma YAML">
                  <CodeBlock value={String(currentRevision?.sigma_yaml ?? "")} maxHeight="34rem" />
                </Panel>
                <div className="min-w-0 space-y-4">
                  <Panel title="Compiled Query">
                    <CodeBlock value={compiledQuery} maxHeight="12rem" />
                  </Panel>
                  <Panel title="Validation">
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <Fact label="Schema" value={String(currentValidation?.schema_valid)} />
                      <Fact label="Sigma" value={String(currentValidation?.sigma_valid)} />
                      <Fact label="Compilation" value={String(currentValidation?.compilation_success)} />
                      <Fact label="ATT&CK" value={String(currentValidation?.attack_verified)} />
                      <Fact label="Duplicate" value={String(currentValidation?.duplicate_status)} />
                      <Fact label="Quality" value={String(currentValidation?.quality_score)} />
                    </div>
                    <CodeBlock value={duplicateResult ?? { status: currentValidation?.duplicate_status ?? "unknown" }} maxHeight="10rem" />
                  </Panel>
                  <Panel title="Deployment">
                    <div className="space-y-2 text-sm">
                      {workspace.deployment_artifacts.length === 0 ? <span className="text-slate-500">No deployment artifact yet.</span> : workspace.deployment_artifacts.map((artifact) => (
                        <div key={String(artifact.id)} className="rounded-md border border-border bg-slate-950/50 p-2">
                          <StatusBadge value={artifact.status ?? "generated"} /> <span className="ml-2 font-mono text-xs">{shortId(artifact.id)}</span>
                          <button disabled={busy != null} className="ml-3 text-xs text-accent hover:underline disabled:text-slate-600" onClick={() => void downloadArtifact(artifact.id)}>Download</button>
                        </div>
                      ))}
                    </div>
                  </Panel>
                </div>
              </div>

              <div className="grid min-w-0 gap-4 lg:grid-cols-3">
                <Panel title="ATT&CK Mapping">
                  <CompactList items={workspace.attack_mappings} primary="technique_id" secondary="technique_name" status="verification_status" />
                </Panel>
                <Panel title="Coverage">
                  <CompactList items={workspace.coverage_results} primary="coverage_status" secondary="similarity_score" status="coverage_status" />
                </Panel>
                <Panel title="Visibility">
                  <CompactList items={workspace.visibility_results} primary="visibility_status" secondary="required_sources" status="visibility_status" />
                </Panel>
              </div>

              <div className="grid min-w-0 gap-4 lg:grid-cols-3">
                <Panel title="Policy Decision">
                  <CompactList items={workspace.policy_decisions} primary="decision" secondary="deterministic_rationale" status="decision" />
                </Panel>
                <Panel title="Behavior Evidence">
                  <CodeBlock value={{ evidence_refs: workspace.behavior?.evidence_refs, observables: workspace.behavior?.observables }} maxHeight="14rem" />
                </Panel>
                <Panel title="AI Interactions">
                  <div className="max-h-56 space-y-2 overflow-auto pr-1">
                    {workspace.ai_interactions.length === 0 ? <span className="text-sm text-slate-500">No AI interactions.</span> : workspace.ai_interactions.map((item) => (
                      <div className="rounded-md border border-border bg-slate-950/50 p-2 text-sm" key={String(item.id)}>
                        <div className="font-medium">{String(item.provider)} / {String(item.prompt_version)}</div>
                        <div className="mt-1 text-xs text-slate-500">{String(item.total_tokens)} tokens / ${Number(item.estimated_cost ?? 0).toFixed(6)} / {String(item.latency_ms ?? 0)} ms</div>
                      </div>
                    ))}
                  </div>
                </Panel>
              </div>

              <div className="grid min-w-0 gap-4 lg:grid-cols-2">
                <Panel title="Revision History">
                  <div className="max-h-72 space-y-2 overflow-auto pr-1">
                    {workspace.revisions.map((revision) => (
                      <div className="rounded-md border border-border bg-slate-950/50 p-2 text-sm" key={String(revision.id)}>
                        <span className="font-semibold">Revision {String(revision.revision_number)}</span>
                        <span className="ml-3 text-slate-500">confidence {String(revision.confidence)} / cost ${Number(revision.estimated_cost ?? 0).toFixed(6)}</span>
                      </div>
                    ))}
                  </div>
                </Panel>
                <Panel title="Repair Diff">
                  <CodeBlock value={revisionDiff(previousRevision, currentRevision, latestRepair)} maxHeight="18rem" />
                </Panel>
              </div>

              <div className="grid min-w-0 gap-4 lg:grid-cols-2">
                <Panel title="Timeline">
                  <div className="max-h-72 overflow-auto pr-1"><Timeline items={timeline} /></div>
                </Panel>
              </div>
            </div>
          )}
        </div>
      </section>
    </Shell>
  );
}

function CompactList({ items, primary, secondary, status }: { items: Record<string, unknown>[]; primary: string; secondary: string; status: string }) {
  if (items.length === 0) return <div className="text-sm text-slate-500">No records.</div>;
  return (
    <div className="max-h-48 space-y-2 overflow-auto pr-1">
      {items.map((item) => (
        <div className="rounded-md border border-border bg-slate-950/50 p-2 text-sm" key={String(item.id)}>
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-medium">{String(item[primary] ?? "-")}</span>
            <StatusBadge value={item[status]} />
          </div>
          <div className="mt-1 truncate text-xs text-slate-500">{Array.isArray(item[secondary]) ? (item[secondary] as unknown[]).join(", ") : String(item[secondary] ?? "")}</div>
        </div>
      ))}
    </div>
  );
}

function Skeleton() {
  return <div className="space-y-2">{[0, 1, 2].map((row) => <div className="h-16 animate-pulse rounded-md border border-border bg-slate-950/70" key={row} />)}</div>;
}

function actionLabel(action: string) {
  return action.replace("-", " ");
}

function revisionDiff(previous: Record<string, unknown> | null | undefined, current: Record<string, unknown> | undefined, repair: Record<string, unknown> | undefined) {
  const previousSigma = previous?.sigma_json as Record<string, unknown> | undefined;
  const currentSigma = current?.sigma_json as Record<string, unknown> | undefined;
  const repairResponse = repair?.response_json as Record<string, unknown> | undefined;
  return {
    previous_revision: previous?.revision_number ?? null,
    current_revision: current?.revision_number ?? null,
    previous_selection: (previousSigma?.detection as Record<string, unknown> | undefined)?.selection,
    current_selection: (currentSigma?.detection as Record<string, unknown> | undefined)?.selection,
    analyst_instruction: (repair?.request_json as Record<string, unknown> | undefined)?.payload,
    interpretation: repairResponse?.instruction_interpretation,
    change_summary: (current?.structured_justification as Record<string, unknown> | undefined)?.change_summary,
  };
}

function formatError(err: unknown, fallback: string) {
  if (err instanceof ApiError && err.status === 401) return "Authentication required. Please log in again.";
  if (err instanceof Error) return `${fallback}: ${err.message}`;
  return fallback;
}
