"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, BrainCircuit, Database, FileCheck, Gauge, GitBranch, HeartPulse, LayoutDashboard, Network, RadioTower, Settings, ShieldCheck } from "lucide-react";
import { apiGet, getToken } from "@/lib/api";

const nav = [
  ["Dashboard", "/dashboard", LayoutDashboard],
  ["AI Dashboard", "/ai", BrainCircuit],
  ["AI Workflow", "/ai-workflow", Network],
  ["Live AI Graph", "/graph", GitBranch],
  ["Threat Queue", "/threats", RadioTower],
  ["Review Queue", "/reviews", FileCheck],
  ["Telemetry", "/telemetry", Database],
  ["ATT&CK Coverage", "/attack", ShieldCheck],
  ["Detections", "/detections", Activity],
  ["Automation Runs", "/runs", Gauge],
  ["System Health", "/health", HeartPulse],
  ["Settings", "/settings", Settings]
];

export function Shell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<{ display_name: string; role: string } | null>(null);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    apiGet<{ display_name: string; role: string }>("/auth/me")
      .then(setUser)
      .catch(() => {
        window.localStorage.removeItem("access_token");
        window.localStorage.removeItem("refresh_token");
        window.location.href = "/login";
      });
  }, []);

  function logout() {
    window.localStorage.removeItem("access_token");
    window.localStorage.removeItem("refresh_token");
    window.location.href = "/login";
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-background text-slate-100">
      <aside className="fixed inset-y-0 left-0 hidden w-56 border-r border-border bg-[#0b1119] px-3 py-4 md:block">
        <div className="mb-5 px-2">
          <div className="text-xs font-semibold uppercase text-accent">CTI Platform</div>
          <div className="mt-1 text-base font-semibold">Detection Engineering</div>
          <div className="mt-2 text-xs text-slate-500">MISP to reviewed Sigma</div>
        </div>
        <nav className="space-y-1">
          {nav.map(([label, href, Icon]) => (
            <Link key={href as string} href={href as string} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-300 hover:bg-slate-800/80 hover:text-white">
              <Icon className="h-4 w-4" />
              {label as string}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="min-h-screen min-w-0 md:ml-56">
        <header className="flex min-h-12 flex-wrap items-center justify-between gap-2 border-b border-border bg-[#0b1119]/95 px-4 py-2">
          <span className="text-sm text-slate-400">MISP ingestion {"->"} LangGraph workflow {"->"} pySigma validation {"->"} analyst review</span>
          <div className="flex min-w-0 items-center gap-3 text-sm">
            {user ? <span className="text-slate-300">{user.display_name} / {user.role}</span> : <span className="text-warning">Checking session</span>}
            <button className="rounded-md border border-border px-3 py-1.5 text-slate-200 hover:bg-slate-800" onClick={logout}>Logout</button>
          </div>
        </header>
        <div className="min-w-0 p-3 sm:p-4">{children}</div>
      </main>
    </div>
  );
}
