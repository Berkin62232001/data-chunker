"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { lockWorkspace, unlockWorkspace } from "@/lib/api";

export function AccessGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(false);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function unlock(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await unlockWorkspace(key);
      setKey("");
      setUnlocked(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to unlock workspace.");
    } finally {
      setBusy(false);
    }
  }

  if (unlocked) return <>
    <div className="px-6 pt-3 text-right">
      <button onClick={() => { lockWorkspace(); setUnlocked(false); }}>Lock workspace</button>
    </div>
    {children}
  </>;

  return <main className="p-8 max-w-lg mx-auto">
    <h1 className="text-2xl font-semibold mb-4">Unlock your workspace</h1>
    <p className="mb-6">Enter your access key to view and process documents. Refreshing this page locks the workspace.</p>
    <form onSubmit={unlock} className="flex flex-col gap-4">
      <label htmlFor="access-key">Access key</label>
      <input id="access-key" type="password" autoComplete="off" required value={key}
        onChange={(event) => setKey(event.target.value)} className="border rounded p-3" />
      <button type="submit" disabled={busy} className="border rounded p-3">
        {busy ? "Unlocking…" : "Unlock"}
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  </main>;
}
