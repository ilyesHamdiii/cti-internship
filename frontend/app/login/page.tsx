"use client";

import { FormEvent, useState } from "react";
import { apiPost } from "@/lib/api";

export default function Login() {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const tokens = await apiPost<{ access_token: string; refresh_token: string }>("/auth/login", { email, password });
      window.localStorage.setItem("access_token", tokens.access_token);
      window.localStorage.setItem("refresh_token", tokens.refresh_token);
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <form onSubmit={submit} className="w-full max-w-sm rounded-md border border-border bg-panel p-6">
        <h1 className="mb-5 text-xl font-semibold text-white">SOC Login</h1>
        <label className="mb-3 block text-sm text-slate-300">
          Email
          <input className="mt-1 w-full rounded-md border border-border bg-slate-950 px-3 py-2 text-white" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="mb-4 block text-sm text-slate-300">
          Password
          <input className="mt-1 w-full rounded-md border border-border bg-slate-950 px-3 py-2 text-white" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error ? <div className="mb-3 text-sm text-danger">{error}</div> : null}
        <button className="w-full rounded-md bg-accent px-3 py-2 font-semibold text-slate-950">Sign in</button>
      </form>
    </main>
  );
}
