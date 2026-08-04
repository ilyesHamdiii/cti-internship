"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { Page, apiGet } from "@/lib/api";
import { CodeBlock, EmptyState, Fact, Panel, StatusBadge, shortId } from "@/components/Soc";

export default function DetectionsPage() {
  const [data, setData] = useState<Page | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await apiGet<Page>("/detections");
    setData(result);
    const next = result.items[0]?.id ? String(result.items[0].id) : null;
    setSelected(next);
    if (next) setDetail(await apiGet<Record<string, unknown>>(`/detections/${next}`));
  }, []);

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, [load]);

  async function choose(id: string) {
    setSelected(id);
    setError(null);
    try {
      setDetail(await apiGet<Record<string, unknown>>(`/detections/${id}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load detection");
    }
  }

  const normalized = detail?.normalized_logic as Record<string, unknown> | undefined;
  const compiledOutputs = normalized?.compiled_outputs as Record<string, unknown> | undefined;
  const validation = normalized?.validation as Record<string, unknown> | undefined;
  const compiledQuery = compiledOutputs?.query ?? compiledOutputs ?? detail?.compiled_query ?? {};
  const mappings = useMemo(() => detail?.attack_mappings as Record<string, unknown>[] | undefined, [detail]);

  return (
    <Shell>
      <section className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Detection Catalog</h1>
          <p className="mt-1 text-sm text-slate-500">Imported and generated detections, including Sigma content, compiled query, proposal lineage, and ATT&CK mappings.</p>
        </div>
        {error ? <div className="rounded-md border border-danger bg-red-950/30 p-3 text-sm text-red-200">{error}</div> : null}

        <div className="grid min-w-0 gap-4 xl:grid-cols-[24rem_1fr]">
          <Panel title="Catalog" action={<StatusBadge value={data ? `${data.total} detections` : "loading"} />}>
            {!data ? <Skeleton /> : data.items.length === 0 ? (
              <EmptyState title="No detections" detail="Approve a proposal from Review Workspace to publish a generated catalog entry." />
            ) : (
              <div className="max-h-[42rem] space-y-2 overflow-auto pr-1">
                {data.items.map((item) => (
                  <button key={String(item.id)} onClick={() => void choose(String(item.id))} className={`w-full rounded-md border p-3 text-left ${selected === item.id ? "border-accent bg-accent/10" : "border-border bg-slate-950/50 hover:bg-slate-900"}`}>
                    <div className="flex min-w-0 items-center justify-between gap-3">
                      <span className="truncate text-sm font-semibold">{String(item.name ?? item.id)}</span>
                      <StatusBadge value={item.status} />
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-slate-500">
                      <span>{String(item.source)}</span>
                      <span>rev {String(item.revision_number ?? "-")}</span>
                      <span>{Array.isArray(item.attack_mappings) ? item.attack_mappings.map((m) => String((m as Record<string, unknown>).technique_id)).join(", ") : "-"}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Panel>

          {!detail ? (
            <Panel title="Detection Detail"><EmptyState title="No detection selected" detail="Select a catalog row to inspect generated Sigma and compiled query output." /></Panel>
          ) : (
            <div className="min-w-0 space-y-4">
              <Panel title="Detection Summary" action={<StatusBadge value={detail.source} />}>
                <div className="grid grid-cols-2 gap-2 text-sm lg:grid-cols-6">
                  <Fact label="Detection" value={shortId(detail.id)} />
                  <Fact label="Type" value={detail.detection_type} />
                  <Fact label="Status" value={detail.status} />
                  <Fact label="Proposal" value={shortId(normalized?.proposal_id)} />
                  <Fact label="Revision" value={normalized?.revision_number} />
                  <Fact label="Quality" value={normalized?.quality_score} />
                </div>
              </Panel>

              <div className="grid min-w-0 gap-4 lg:grid-cols-[1fr_24rem]">
                <Panel title="Sigma YAML">
                  <CodeBlock value={String(detail.content ?? "")} maxHeight="34rem" />
                </Panel>
                <div className="min-w-0 space-y-4">
                  <Panel title="Compiled Query">
                    <CodeBlock value={compiledQuery} maxHeight="12rem" />
                  </Panel>
                  <Panel title="Validation Lineage">
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <Fact label="Artifact" value={shortId(normalized?.deployment_artifact_id)} />
                      <Fact label="Workflow" value={shortId(normalized?.workflow_id)} />
                      <Fact label="Behavior" value={shortId(normalized?.behavior_id)} />
                      <Fact label="Duplicate" value={validation?.duplicate_status} />
                    </div>
                  </Panel>
                  <Panel title="ATT&CK">
                    <div className="space-y-2">
                      {(mappings ?? []).length === 0 ? <span className="text-sm text-slate-500">No ATT&CK mapping.</span> : mappings?.map((mapping) => (
                        <div className="rounded-md border border-border bg-slate-950/50 p-2 text-sm" key={`${mapping.technique_id}-${mapping.tactic_id}`}>
                          <span className="font-semibold">{String(mapping.technique_id)}</span>
                          <span className="ml-2 text-slate-500">{String(mapping.tactic_id ?? "")}</span>
                        </div>
                      ))}
                    </div>
                  </Panel>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </Shell>
  );
}

function Skeleton() {
  return <div className="space-y-2">{[0, 1, 2].map((row) => <div className="h-16 animate-pulse rounded-md border border-border bg-slate-950/70" key={row} />)}</div>;
}
