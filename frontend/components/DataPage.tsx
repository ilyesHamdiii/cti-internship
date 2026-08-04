"use client";

import { useEffect, useState } from "react";
import { ApiError, apiGet, Page } from "@/lib/api";
import { EmptyState, StatusBadge } from "@/components/Soc";

type Column = {
  key: string;
  label: string;
  render?: (item: Record<string, unknown>) => React.ReactNode;
};

export function DataPage({ title, endpoint, columns, emptyMessage }: { title: string; endpoint: string; columns: Column[]; emptyMessage: string }) {
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState<{ status?: number; message: string } | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    apiGet<Page>(endpoint)
      .then(setData)
      .catch((err: Error) => setError(err instanceof ApiError ? { status: err.status, message: err.message } : { message: err.message }));
  }, [endpoint]);

  const errorText = error?.status === 401
    ? "Authentication required. Please log in again."
    : error?.status === 403
      ? "Your account is not authorized to view this page."
      : error?.message;
  const items = data?.items.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase())) ?? [];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-slate-500">Operational view backed by live platform APIs.</p>
        </div>
        <input className="w-full max-w-72 rounded-md border border-border bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent" placeholder="Search records" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      {error ? <div className="rounded-md border border-danger bg-red-950/30 p-4 text-sm text-red-200">{errorText}</div> : null}
      {!data && !error ? <div className="grid gap-2">{[0, 1, 2].map((row) => <div className="h-12 animate-pulse rounded-md border border-border bg-panel" key={row} />)}</div> : null}
      {data ? (
        <div className="overflow-auto rounded-md border border-border">
          <table className="w-full min-w-[680px] text-left text-sm">
            <thead className="bg-slate-900 text-slate-300">
              <tr>
                {columns.map((column) => <th className="px-3 py-2" key={column.key}>{column.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td className="px-3 py-4" colSpan={columns.length}><EmptyState title="No matching operational data" detail={data.items.length === 0 ? emptyMessage : "No records match the current search filter."} /></td></tr>
              ) : (
                items.map((item, index) => (
                  <tr className="border-t border-border hover:bg-slate-900/60" key={String(item.id ?? index)}>
                    {columns.map((column) => (
                      <td className="max-w-72 truncate px-3 py-2 align-top" key={column.key}>
                        {column.render ? column.render(item) : column.key === "status" || column.key.includes("status") || column.key.includes("state") ? <StatusBadge value={item[column.key]} /> : String(item[column.key] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
