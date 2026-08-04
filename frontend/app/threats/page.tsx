"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Clock, ExternalLink, Play, RefreshCw, RotateCcw, UploadCloud } from "lucide-react";
import { Shell } from "@/components/Shell";
import { ApiError, Page, apiGet, apiPost } from "@/lib/api";
import { ActionButton, EmptyState, Fact, Panel, SeverityBadge, StatusBadge, shortId } from "@/components/Soc";

type Row = Record<string, unknown>;
type MispFilter = "actionable" | "all";
type ScheduleMode = "disabled" | "interval" | "hourly" | "daily" | "weekly" | "once";

export default function ThreatsPage() {
  const [cti, setCti] = useState<Page | null>(null);
  const [misp, setMisp] = useState<Page | null>(null);
  const [mispFilter, setMispFilter] = useState<MispFilter>("actionable");
  const [selectedMisp, setSelectedMisp] = useState<string | null>(null);
  const [selectedCti, setSelectedCti] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<Row | null>(null);
  const [scheduleMode, setScheduleMode] = useState<ScheduleMode>("disabled");
  const [scheduleTime, setScheduleTime] = useState("09:00");
  const [scheduleWeekday, setScheduleWeekday] = useState("0");
  const [scheduleOnceAt, setScheduleOnceAt] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [ctiResult, mispResult] = await Promise.all([
        apiGet<Page>("/cti-events"),
        apiGet<Page>("/misp/events?status=all")
      ]);
      setCti(ctiResult);
      setMisp(mispResult);
      setSelectedMisp((current) => {
        if (current && mispResult.items.some((item) => mispId(item) === current)) return current;
        return mispId(mispResult.items.find(isActionableMisp) ?? mispResult.items[0]);
      });
      setSelectedCti((current) => current ?? String(ctiResult.items[0]?.id ?? ""));
    } catch (err) {
      setError(formatError(err, "Failed to load threat queues"));
    }
  }, []);

  const loadSchedule = useCallback(async () => {
    const result = await apiGet<Row>("/misp/ingestion-schedule");
    setSchedule(result);
    const mode = String(result.mode ?? "interval") as ScheduleMode;
    setScheduleMode(["disabled", "interval", "hourly", "daily", "weekly", "once"].includes(mode) ? mode : "interval");
    setScheduleTime(String(result.time_of_day ?? "09:00"));
    setScheduleWeekday(String(result.weekday ?? "0"));
  }, []);

  useEffect(() => {
    void load();
    void loadSchedule().catch(() => undefined);
  }, [load, loadSchedule]);

  const selectedMispRow = useMemo(() => misp?.items.find((item) => mispId(item) === selectedMisp), [misp, selectedMisp]);
  const selectedCtiRow = useMemo(() => cti?.items.find((item) => String(item.id) === selectedCti), [cti, selectedCti]);
  const mispItems = useMemo(() => misp?.items ?? [], [misp]);
  const actionableMispCount = mispItems.filter(isActionableMisp).length;
  const visibleMispItems = useMemo(
    () => mispFilter === "actionable" ? mispItems.filter(isActionableMisp) : mispItems,
    [mispFilter, mispItems]
  );
  const selectedCanIngest = Boolean(selectedMispRow?.can_ingest);
  const selectedCanReprocess = !selectedCanIngest && String(selectedMispRow?.ingestion_status ?? "") === "failed" && Boolean(selectedMispRow?.cti_event_id);
  const selectedCanProcess = selectedCanIngest || selectedCanReprocess;

  async function runAction(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    setMessage(null);
    setError(null);
    try {
      const result = await action();
      setMessage(`${label}: ${summary(result)}`);
      await load();
    } catch (err) {
      setError(formatError(err, `${label} failed`));
    } finally {
      setBusy(null);
    }
  }

  async function refreshQueues() {
    await runAction("Refresh", async () => {
      await load();
      return { status: `updated ${new Date().toLocaleTimeString()}` };
    });
  }

  async function ingestSelected() {
    if (!selectedMispRow || !selectedCanProcess) return;
    if (selectedCanReprocess) {
      await runAction("MISP reprocess", () => apiPost(`/cti-events/${selectedMispRow.cti_event_id}/reprocess`, {}));
      return;
    }
    await runAction("MISP ingest", () => apiPost(`/misp/events/${mispId(selectedMispRow)}/ingest`, {}));
  }

  async function ingestAll() {
    await runAction("Bulk MISP ingest", () => apiPost("/misp/events/ingest-all-new", {}));
  }

  async function saveSchedule() {
    const payload: Record<string, unknown> = {
      enabled: scheduleMode !== "disabled",
      mode: scheduleMode,
      timezone_offset_minutes: -new Date().getTimezoneOffset()
    };
    if (scheduleMode === "daily" || scheduleMode === "weekly") {
      payload.time_of_day = scheduleTime;
    }
    if (scheduleMode === "weekly") {
      payload.weekday = Number(scheduleWeekday);
    }
    if (scheduleMode === "once") {
      if (!scheduleOnceAt) {
        setError("Schedule ingestion failed: choose a date and time.");
        return;
      }
      payload.run_at = new Date(scheduleOnceAt).toISOString();
    }
    await runAction("Schedule ingestion", async () => {
      const result = await apiPost<Row>("/misp/ingestion-schedule", payload);
      setSchedule(result);
      return result;
    });
  }

  async function runWorkflow(eventId: unknown) {
    await runAction("Run detection workflow", () => apiPost(`/cti-events/${eventId}/run-workflow`, {}));
  }

  async function reprocess(eventId: unknown) {
    await runAction("Reprocess CTI", () => apiPost(`/cti-events/${eventId}/reprocess`, {}));
  }

  return (
    <Shell>
      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Threat Queue</h1>
            <p className="mt-1 text-sm text-slate-500">Real MISP events, ingestion status, and authoritative graph execution controls.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <ActionButton disabled={busy != null} onClick={() => void refreshQueues()}><RefreshCw className="mr-2 inline h-4 w-4" />Refresh</ActionButton>
            <ActionButton disabled={busy != null || !selectedCanProcess} tone="good" onClick={() => void ingestSelected()}><UploadCloud className="mr-2 inline h-4 w-4" />Ingest Selected</ActionButton>
            <ActionButton disabled={busy != null} tone="good" onClick={() => void ingestAll()}>Ingest All New</ActionButton>
          </div>
        </div>

        {message ? <div className="rounded-md border border-accent/50 bg-accent/10 p-3 text-sm text-emerald-100">{message}</div> : null}
        {error ? <div className="rounded-md border border-danger bg-red-950/30 p-3 text-sm text-red-200">{error}</div> : null}

        <div className="grid min-w-0 gap-4 xl:grid-cols-[0.95fr_1.35fr]">
          <Panel title="MISP Inbox" action={<StatusBadge value={misp ? `${actionableMispCount} needs action / ${misp.total} total` : "loading"} />}>
            <div className="mb-3 flex flex-wrap gap-2">
              <button onClick={() => setMispFilter("actionable")} className={`rounded-md border px-3 py-1 text-xs font-semibold ${mispFilter === "actionable" ? "border-accent bg-accent/15 text-emerald-100" : "border-border text-slate-400 hover:bg-slate-900"}`}>Needs Action</button>
              <button onClick={() => setMispFilter("all")} className={`rounded-md border px-3 py-1 text-xs font-semibold ${mispFilter === "all" ? "border-accent bg-accent/15 text-emerald-100" : "border-border text-slate-400 hover:bg-slate-900"}`}>All MISP</button>
            </div>
            {!misp ? <Skeleton /> : misp.items.length === 0 ? (
              <EmptyState title="No MISP events returned" detail="Check MISP connectivity on System Health, then create or publish a test event in the MISP web UI." />
            ) : visibleMispItems.length === 0 ? (
              <EmptyState title="No MISP events need action" detail="All returned MISP events are already represented in the CTI queue. Use All MISP to inspect processed test events." />
            ) : (
              <div className="max-h-[34rem] space-y-2 overflow-auto pr-1">
                {visibleMispItems.map((item) => (
                  <button key={mispId(item)} onClick={() => setSelectedMisp(mispId(item))} className={`w-full rounded-md border p-3 text-left ${selectedMisp === mispId(item) ? "border-accent bg-accent/10" : "border-border bg-slate-950/50 hover:bg-slate-900"}`}>
                    <div className="flex min-w-0 items-center justify-between gap-3">
                      <span className="truncate text-sm font-semibold">{String(item.info ?? item.title ?? `MISP ${mispId(item)}`)}</span>
                      <div className="flex shrink-0 items-center gap-2">
                        {Number(item.duplicate_count ?? 1) > 1 ? <StatusBadge value={`merged ${item.duplicate_count}`} /> : null}
                        <StatusBadge value={item.ingestion_status ?? item.status} />
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-4 gap-2 text-xs text-slate-500">
                      <span>MISP {mispId(item)}</span>
                      <span>org {String(item.orgc ?? item.org ?? "-")}</span>
                      <span>attrs {String(item.attribute_count ?? item.attributes_count ?? 0)}</span>
                      <span>CTI {shortId(item.cti_event_id)}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Ingested CTI Events" action={<StatusBadge value={cti ? `${cti.total} records` : "loading"} />}>
            {!cti ? <Skeleton /> : cti.items.length === 0 ? (
              <EmptyState title="No CTI ingested yet" detail="Select a MISP event and use Ingest Selected. The event will enter this queue through the MISP API path." />
            ) : (
              <div className="overflow-auto">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead className="border-b border-border bg-slate-950/70 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-2 py-2">Severity</th>
                      <th className="px-2 py-2">Event</th>
                      <th className="px-2 py-2">Workflow</th>
                      <th className="px-2 py-2">Policy</th>
                      <th className="px-2 py-2">Proposal</th>
                      <th className="px-2 py-2">Graph</th>
                      <th className="px-2 py-2">ATT&CK</th>
                      <th className="px-2 py-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cti.items.map((item) => (
                      <tr key={String(item.id)} onClick={() => setSelectedCti(String(item.id))} className={`cursor-pointer border-b border-border hover:bg-slate-900/60 ${selectedCti === String(item.id) ? "bg-accent/10" : ""}`}>
                        <td className="px-2 py-2"><SeverityBadge value={item.severity} /></td>
                        <td className="min-w-0 px-2 py-2">
                          <div className="max-w-72 truncate font-medium">{String(item.title ?? "-")}</div>
                          <div className="text-xs text-slate-500">MISP {String(item.misp_event_id ?? "-")} / {shortId(item.id)}</div>
                        </td>
                        <td className="px-2 py-2"><StatusBadge value={item.workflow_status ?? item.status} /></td>
                        <td className="px-2 py-2"><StatusBadge value={item.final_policy_outcome ?? "none"} /></td>
                        <td className="px-2 py-2"><StatusBadge value={item.proposal_state ?? "none"} /></td>
                        <td className="px-2 py-2"><StatusBadge value={item.graph_status ?? "none"} /></td>
                        <td className="max-w-32 truncate px-2 py-2 text-xs text-slate-300">{Array.isArray(item.attack_techniques) ? item.attack_techniques.join(", ") : "-"}</td>
                        <td className="px-2 py-2">
                          <div className="flex flex-wrap gap-2">
                            <ActionButton disabled={busy != null} tone="good" onClick={() => void runWorkflow(item.id)}><Play className="h-4 w-4" /></ActionButton>
                            <ActionButton disabled={busy != null} onClick={() => void reprocess(item.id)}><RotateCcw className="h-4 w-4" /></ActionButton>
                            {item.current_graph_run_id ? <a className="rounded-md border border-border px-2 py-1 text-xs text-slate-300 hover:bg-slate-900" href="/graph">Graph</a> : null}
                            {item.proposal_id ? <a className="rounded-md border border-border px-2 py-1 text-xs text-slate-300 hover:bg-slate-900" href="/reviews">Proposal</a> : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>

        <div className="grid min-w-0 gap-4 lg:grid-cols-2">
          <Panel title="Selected MISP Event">
            <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
              <Fact label="MISP ID" value={mispId(selectedMispRow)} />
              <Fact label="Ingestion" value={selectedMispRow?.ingestion_status ?? selectedMispRow?.status} />
              <Fact label="Action" value={selectedCanIngest ? "ingest" : selectedCanReprocess ? "reprocess" : "none"} />
              <Fact label="Merged Events" value={selectedMispRow?.duplicate_count ?? 1} />
              <Fact label="CTI Event" value={shortId(selectedMispRow?.cti_event_id)} />
              <Fact label="Workflow" value={shortId(selectedMispRow?.workflow_id)} />
            </div>
            {mispId(selectedMispRow) ? (
              <a className="mt-3 inline-flex items-center text-sm text-accent hover:underline" href={`https://localhost:8443/events/view/${mispId(selectedMispRow)}`} target="_blank" rel="noreferrer">
                <ExternalLink className="mr-2 h-4 w-4" />Open in MISP
              </a>
            ) : null}
          </Panel>
          <Panel title="Scheduled MISP Ingestion" action={<StatusBadge value={scheduleStatus(schedule)} />}>
            <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
              <label className="text-xs uppercase text-slate-500">
                Mode
                <select value={scheduleMode} onChange={(event) => setScheduleMode(event.target.value as ScheduleMode)} className="mt-1 w-full rounded-md border border-border bg-slate-950 px-3 py-2 text-sm text-slate-100">
                  <option value="disabled">Disabled</option>
                  <option value="interval">Default interval</option>
                  <option value="hourly">Hourly</option>
                  <option value="daily">Daily at time</option>
                  <option value="weekly">Weekly at time</option>
                  <option value="once">Specific date/time</option>
                </select>
              </label>
              {scheduleMode === "daily" || scheduleMode === "weekly" ? (
                <label className="text-xs uppercase text-slate-500">
                  Time
                  <input type="time" value={scheduleTime} onChange={(event) => setScheduleTime(event.target.value)} className="mt-1 w-full rounded-md border border-border bg-slate-950 px-3 py-2 text-sm text-slate-100" />
                </label>
              ) : scheduleMode === "once" ? (
                <label className="text-xs uppercase text-slate-500">
                  Run At
                  <input type="datetime-local" value={scheduleOnceAt} onChange={(event) => setScheduleOnceAt(event.target.value)} className="mt-1 w-full rounded-md border border-border bg-slate-950 px-3 py-2 text-sm text-slate-100" />
                </label>
              ) : (
                <div />
              )}
              {scheduleMode === "weekly" ? (
                <label className="text-xs uppercase text-slate-500">
                  Day
                  <select value={scheduleWeekday} onChange={(event) => setScheduleWeekday(event.target.value)} className="mt-1 w-full rounded-md border border-border bg-slate-950 px-3 py-2 text-sm text-slate-100">
                    <option value="0">Monday</option>
                    <option value="1">Tuesday</option>
                    <option value="2">Wednesday</option>
                    <option value="3">Thursday</option>
                    <option value="4">Friday</option>
                    <option value="5">Saturday</option>
                    <option value="6">Sunday</option>
                  </select>
                </label>
              ) : null}
              <div className="flex items-end">
                <ActionButton disabled={busy != null} tone="good" onClick={() => void saveSchedule()}><Clock className="mr-2 inline h-4 w-4" />Save Schedule</ActionButton>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
              <Fact label="Mode" value={schedule?.mode ?? "loading"} />
              <Fact label="Next Run" value={formatDate(schedule?.next_run_at)} />
              <Fact label="Last Triggered" value={formatDate(schedule?.last_triggered_at)} />
              <Fact label="Scheduler" value={schedule?.enabled === false ? "disabled" : "enabled"} />
            </div>
          </Panel>
          <Panel title="Selected CTI Event">
            <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
              <Fact label="CTI ID" value={shortId(selectedCtiRow?.id)} />
              <Fact label="Behaviors" value={selectedCtiRow?.behavior_count} />
              <Fact label="Policy" value={selectedCtiRow?.final_policy_outcome ?? "-"} />
              <Fact label="IOCs" value={selectedCtiRow?.ioc_count} />
              <Fact label="Graph Run" value={shortId(selectedCtiRow?.current_graph_run_id)} />
            </div>
          </Panel>
        </div>
      </section>
    </Shell>
  );
}

function scheduleStatus(schedule: Row | null) {
  if (!schedule) return "loading";
  if (schedule.enabled === false || schedule.mode === "disabled") return "disabled";
  return `${String(schedule.mode ?? "scheduled")}`;
}

function formatDate(value: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function Skeleton() {
  return <div className="space-y-2">{[0, 1, 2].map((row) => <div className="h-14 animate-pulse rounded-md border border-border bg-slate-950/70" key={row} />)}</div>;
}

function summary(result: unknown) {
  if (!result || typeof result !== "object") return "completed";
  const data = result as Record<string, unknown>;
  return [
    data.status,
    numberText(data.created, "created"),
    numberText(data.existing, "existing"),
    numberText(data.skipped, "skipped"),
    Array.isArray(data.graph_task_ids) ? `${data.graph_task_ids.length} graph tasks queued` : null,
    data.graph_task_id ? `graph task ${shortId(data.graph_task_id)}` : null,
    data.graph_run_id ? `graph ${shortId(data.graph_run_id)}` : null,
    data.cti_event_id ? `cti ${shortId(data.cti_event_id)}` : null
  ]
    .filter(Boolean)
    .join(" / ");
}

function mispId(item: Record<string, unknown> | undefined) {
  return String(item?.misp_event_id ?? item?.id ?? "");
}

function isActionableMisp(item: Row) {
  return item.actionable === true || item.can_ingest === true || ["new", "failed"].includes(String(item.ingestion_status ?? item.status));
}

function numberText(value: unknown, label: string) {
  return typeof value === "number" ? `${value} ${label}` : null;
}

function formatError(err: unknown, fallback: string) {
  if (err instanceof ApiError && err.status === 401) return "Authentication required. Please log in again.";
  if (err instanceof Error) return `${fallback}: ${err.message}`;
  return fallback;
}
