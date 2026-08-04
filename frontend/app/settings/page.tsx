"use client";

import { useEffect, useMemo, useState } from "react";
import { Save } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Page, apiGet, apiPatch } from "@/lib/api";
import { ActionButton, CodeBlock, EmptyState, Fact, Panel, StatusBadge } from "@/components/Soc";

const editableKeys = [
  "misp.poll_interval_seconds",
  "ai.fixture_mode",
  "ai.model",
  "sigma.target",
  "validation.quality_threshold",
  "validation.max_repair_attempts",
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<Page | null>(null);
  const [health, setHealth] = useState<Page | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setError(null);
    const [settingsResult, healthResult] = await Promise.all([
      apiGet<Page>("/settings"),
      apiGet<Page>("/system-health")
    ]);
    setSettings(settingsResult);
    setHealth(healthResult);
    setDrafts(Object.fromEntries(settingsResult.items.map((item) => [String(item.key), JSON.stringify(item.value ?? "", null, 2)])));
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  const byKey = useMemo(() => new Map((settings?.items ?? []).map((item) => [String(item.key), item])), [settings]);
  const misp = health?.items.find((item) => item.component === "misp_api");
  const ai = health?.items.find((item) => item.component === "ai_provider");
  const sigma = health?.items.find((item) => item.component === "pysigma");

  async function save(key: string) {
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      const parsed = JSON.parse(drafts[key] ?? "null");
      await apiPatch(`/settings/${encodeURIComponent(key)}`, { value: parsed });
      setMessage(`${key} saved`);
      await load();
    } catch (err) {
      setError(err instanceof SyntaxError ? `${key} must be valid JSON` : err instanceof Error ? err.message : "Failed to save setting");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Shell>
      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Settings</h1>
            <p className="mt-1 text-sm text-slate-500">Runtime configuration surfaced from the platform API, with live health context for MISP, AI, and Sigma.</p>
          </div>
          <ActionButton onClick={() => void load()}>Refresh</ActionButton>
        </div>

        {message ? <div className="rounded-md border border-accent/50 bg-accent/10 p-3 text-sm text-emerald-100">{message}</div> : null}
        {error ? <div className="rounded-md border border-danger bg-red-950/30 p-3 text-sm text-red-200">{error}</div> : null}

        <div className="grid min-w-0 gap-4 lg:grid-cols-3">
          <Panel title="MISP Connectivity" action={<StatusBadge value={misp?.status ?? "unknown"} />}>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Fact label="Configured" value={(misp?.details as Record<string, unknown> | undefined)?.configured} />
              <Fact label="Reachable" value={(misp?.details as Record<string, unknown> | undefined)?.reachable} />
              <Fact label="Authenticated" value={(misp?.details as Record<string, unknown> | undefined)?.authenticated} />
              <Fact label="Polling" value={(misp?.details as Record<string, unknown> | undefined)?.polling_successful} />
            </div>
          </Panel>
          <Panel title="AI Provider" action={<StatusBadge value={ai?.status ?? "unknown"} />}>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Fact label="Model" value={(ai?.details as Record<string, unknown> | undefined)?.model} />
              <Fact label="Fixture Mode" value={(ai?.details as Record<string, unknown> | undefined)?.fixture_mode} />
            </div>
          </Panel>
          <Panel title="Sigma Pipeline" action={<StatusBadge value={sigma?.status ?? "unknown"} />}>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Fact label="Target" value={(sigma?.details as Record<string, unknown> | undefined)?.sigma_target} />
              <Fact label="Compiler" value={sigma?.status} />
            </div>
          </Panel>
        </div>

        <Panel title="Editable Platform Settings" action={<StatusBadge value={settings ? `${settings.total} settings` : "loading"} />}>
          {!settings ? <Skeleton /> : settings.items.length === 0 ? (
            <EmptyState title="No settings" detail="Settings can be created by saving one of the known keys below." />
          ) : null}
          <div className="grid min-w-0 gap-3 lg:grid-cols-2">
            {editableKeys.map((key) => {
              const item = byKey.get(key);
              const value = drafts[key] ?? JSON.stringify(item?.value ?? "", null, 2);
              return (
                <div className="min-w-0 rounded-md border border-border bg-slate-950/50 p-3" key={key}>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="truncate text-sm font-semibold">{key}</div>
                    <ActionButton disabled={busy === key} tone="good" onClick={() => void save(key)}><Save className="h-4 w-4" /></ActionButton>
                  </div>
                  <textarea className="h-24 w-full resize-none rounded-md border border-border bg-slate-950 p-2 font-mono text-xs text-slate-100 outline-none focus:border-accent" value={value} onChange={(event) => setDrafts((current) => ({ ...current, [key]: event.target.value }))} />
                  <div className="mt-2 text-xs text-slate-500">Updated {String(item?.updated_at ?? "not persisted")}</div>
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel title="All Settings">
          <CodeBlock value={settings?.items ?? []} maxHeight="18rem" />
        </Panel>
      </section>
    </Shell>
  );
}

function Skeleton() {
  return <div className="grid gap-2">{[0, 1, 2].map((row) => <div className="h-16 animate-pulse rounded-md border border-border bg-slate-950/70" key={row} />)}</div>;
}
