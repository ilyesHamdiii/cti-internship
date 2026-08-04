"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { apiGet, Page } from "@/lib/api";
import { EmptyState, Panel, StatusBadge } from "@/components/Soc";

export default function AttackPage() {
  const [data, setData] = useState<Page | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    apiGet<Page>("/attack/coverage").then((result) => {
      setData(result);
      setSelected(result.items[0] ?? null);
    });
  }, []);

  const items = data?.items ?? [];
  const tacticOrder = ["initial-access", "execution", "persistence", "privilege-escalation", "defense-evasion", "credential-access", "discovery", "command-and-control", "exfiltration", "impact"];
  const tactics = Array.from(new Set(items.flatMap((item) => Array.isArray(item.tactics) ? item.tactics.map(String) : ["unknown"])))
    .sort((left, right) => {
      const leftIndex = tacticOrder.indexOf(left);
      const rightIndex = tacticOrder.indexOf(right);
      return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex) || left.localeCompare(right);
    });
  const covered = items.filter((item) => String(item.coverage_status) === "covered").length;
  const withPressure = items.filter((item) => Number(item.recent_behavior_count ?? 0) > 0).length;

  return (
    <Shell>
      <section className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">ATT&CK Coverage Matrix</h1>
          <p className="mt-1 text-sm text-slate-500">Technique coverage, visibility gaps, linked detections, and recent CTI pressure.</p>
        </div>
        {items.length === 0 ? <EmptyState title="ATT&CK reference data is not initialized" detail="Import or seed ATT&CK techniques before coverage can be calculated." /> : (
          <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <Panel
              title="Enterprise Technique Matrix"
              action={<StatusBadge value={`${covered}/${items.length} covered`} />}
            >
              <div className="mb-3 grid gap-2 text-sm sm:grid-cols-3">
                <Fact label="Techniques" value={items.length} />
                <Fact label="Tactics" value={tactics.length} />
                <Fact label="Recent CTI Pressure" value={withPressure} />
              </div>
              <div className="overflow-x-auto pb-2">
                <div className="flex min-w-max gap-3">
                  {tactics.map((tactic) => (
                    <div className="w-64 shrink-0 rounded-md border border-border bg-slate-950/50" key={tactic}>
                    <div className="border-b border-border px-3 py-2 text-sm font-semibold capitalize text-slate-200">{labelTactic(tactic)}</div>
                    <div className="space-y-2 p-2">
                      {items.filter((item) => Array.isArray(item.tactics) ? item.tactics.map(String).includes(tactic) : tactic === "unknown").map((technique) => {
                        const status = String(technique.coverage_status);
                        const tone = status === "covered" ? "border-accent/60 bg-accent/15" : status === "partial" ? "border-warning/60 bg-warning/15" : "border-danger/60 bg-danger/10";
                        return (
                          <button className={`w-full rounded-md border p-3 text-left ${tone}`} key={String(technique.technique_id)} onClick={() => setSelected(technique)}>
                            <div className="font-mono text-xs">{String(technique.technique_id)}</div>
                            <div className="mt-1 text-sm font-medium">{String(technique.name)}</div>
                            <div className="mt-2"><StatusBadge value={technique.coverage_status} /></div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
                </div>
              </div>
            </Panel>
            <Panel title="Technique Detail">
              {selected ? (
                <div className="space-y-4 text-sm">
                  <div>
                    <div className="font-mono text-xs text-accent">{String(selected.technique_id)}</div>
                    <h2 className="mt-1 text-lg font-semibold">{String(selected.name)}</h2>
                  </div>
                  <Fact label="Coverage" value={<StatusBadge value={selected.coverage_status} />} />
                  <Fact label="Linked Detections" value={Array.isArray(selected.linked_detection_ids) ? selected.linked_detection_ids.length : 0} />
                  <Fact label="Recent CTI Behaviors" value={String(selected.recent_behavior_count ?? 0)} />
                  <Fact label="Platforms" value={Array.isArray(selected.platforms) ? selected.platforms.join(", ") : ""} />
                  <div>
                    <div className="mb-2 text-xs uppercase text-slate-500">Detection IDs</div>
                    {Array.isArray(selected.linked_detection_ids) && selected.linked_detection_ids.length > 0 ? (
                      <div className="space-y-1 rounded-md bg-slate-950 p-3 text-xs text-slate-300">
                        {selected.linked_detection_ids.map((id) => <div className="truncate font-mono" key={String(id)}>{String(id)}</div>)}
                      </div>
                    ) : (
                      <div className="rounded-md border border-border bg-slate-950/50 p-3 text-sm text-slate-500">No linked detection yet.</div>
                    )}
                  </div>
                </div>
              ) : null}
            </Panel>
          </div>
        )}
      </section>
    </Shell>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="rounded-md border border-border bg-slate-950/50 p-3"><div className="text-xs uppercase text-slate-500">{label}</div><div className="mt-1">{value}</div></div>;
}

function labelTactic(value: string) {
  return value.replace(/-/g, " ");
}
