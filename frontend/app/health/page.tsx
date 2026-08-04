"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Page, apiGet } from "@/lib/api";
import { ActionButton, EmptyState, Fact, Panel, StatusBadge, displayValue, humanize } from "@/components/Soc";

export default function HealthPage() {
  const [data, setData] = useState<Page | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    const result = await apiGet<Page>("/system-health");
    setData(result);
    setSelected(result.items.find((item) => item.component === "misp_api") ?? result.items[0] ?? null);
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  const misp = data?.items.find((item) => item.component === "misp_api");
  const ai = data?.items.find((item) => item.component === "ai_provider");
  const sigma = data?.items.find((item) => item.component === "pysigma");
  const details = misp?.details as Record<string, unknown> | undefined;
  const aiDetails = ai?.details as Record<string, unknown> | undefined;
  const sigmaDetails = sigma?.details as Record<string, unknown> | undefined;

  return (
    <Shell>
      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">System Health</h1>
            <p className="mt-1 text-sm text-slate-500">Operational checks for the demo stack: API, database, broker, MISP, provider mode, and Sigma compilation.</p>
          </div>
          <ActionButton onClick={() => void load()}><RefreshCw className="mr-2 inline h-4 w-4" />Refresh</ActionButton>
        </div>

        {error ? <div className="rounded-md border border-danger bg-red-950/30 p-3 text-sm text-red-200">{error}</div> : null}

        <Panel title="MISP API Connectivity" action={<StatusBadge value={misp?.status ?? "unknown"} />}>
          <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
            <Fact label="Configured" value={details?.configured} />
            <Fact label="Reachable" value={details?.reachable} />
            <Fact label="Authenticated" value={details?.authenticated} />
            <Fact label="Polling" value={details?.polling_successfully} />
          </div>
          <div className="mt-3 text-sm text-slate-400">
            Status values distinguish not configured, unreachable, authentication failed, and healthy based on the backend connectivity check.
          </div>
        </Panel>

        <div className="grid min-w-0 gap-4 lg:grid-cols-2">
          <Panel title="AI Provider Mode" action={<StatusBadge value={ai?.status ?? "unknown"} />}>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Fact label="Fixture Provider" value={String(aiDetails?.fixture_mode ?? false)} />
              <Fact label="Model" value={aiDetails?.model} />
            </div>
            {aiDetails?.fixture_mode ? (
              <div className="mt-3 rounded-md border border-warning/60 bg-warning/10 p-3 text-sm text-amber-100">
                Deterministic AI fixture provider - used for repeatable demonstrations.
              </div>
            ) : (
              <div className="mt-3 text-sm text-slate-400">Live DeepSeek mode is enabled only when credentials are configured.</div>
            )}
          </Panel>
          <Panel title="pySigma Probe" action={<StatusBadge value={sigma?.status ?? "unknown"} />}>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Fact label="Target" value={sigmaDetails?.sigma_target} />
              <Fact label="Compiler" value={sigmaDetails?.compiler} />
              <Fact label="Version" value={sigmaDetails?.compiler_version} />
              <Fact label="Probe Query" value={sigmaDetails?.query} />
            </div>
          </Panel>
        </div>

        <div className="grid min-w-0 gap-4 xl:grid-cols-[1fr_24rem]">
          <Panel title="Components" action={<StatusBadge value={data ? `${data.total} checks` : "loading"} />}>
            {!data ? <Skeleton /> : data.items.length === 0 ? (
              <EmptyState title="No health data" detail="The API returned no component health records." />
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {data.items.map((item, index) => (
                  <button key={`${item.component}-${index}`} onClick={() => setSelected(item)} className="min-h-28 rounded-md border border-border bg-slate-950/50 p-3 text-left hover:bg-slate-900/80">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium">{humanize(item.component)}</span>
                      <StatusBadge value={item.status} />
                    </div>
                    <div className="mt-3 space-y-1 text-xs text-slate-400">
                      {friendlyDetails(item.details).slice(0, 3).map(([key, value]) => (
                        <div className="flex justify-between gap-3" key={key}>
                          <span>{humanize(key)}</span>
                          <span className="truncate text-slate-300">{displayValue(value)}</span>
                        </div>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Selected Details">
            {!selected ? <div className="text-sm text-slate-500">Select a component.</div> : (
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-slate-950/50 p-2">
                  <span className="font-medium">{humanize(selected.component)}</span>
                  <StatusBadge value={selected.status} />
                </div>
                {friendlyDetails(selected.details).map(([key, value]) => (
                  <div className="flex justify-between gap-3 rounded-md border border-border bg-slate-950/50 p-2" key={key}>
                    <span className="text-slate-400">{humanize(key)}</span>
                    <span className="max-w-[16rem] truncate text-right text-slate-100" title={displayValue(value)}>{displayValue(value)}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </section>
    </Shell>
  );
}

function Skeleton() {
  return <div className="space-y-2">{[0, 1, 2].map((row) => <div className="h-12 animate-pulse rounded-md border border-border bg-slate-950/70" key={row} />)}</div>;
}

function friendlyDetails(value: unknown): [string, unknown][] {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>).filter(([, nested]) => typeof nested !== "object" || nested == null || Array.isArray(nested));
}
