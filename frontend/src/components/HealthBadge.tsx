"use client";

import { useEffect, useState } from "react";

import { fetchHealth } from "@/lib/api";

type HealthStatus = "loading" | "ok" | "error";

export function HealthBadge() {
  const [status, setStatus] = useState<HealthStatus>("loading");
  const [info, setInfo] = useState<{ app?: string; version?: string; local_only_mode?: boolean }>({});

  useEffect(() => {
    fetchHealth()
      .then((data) => {
        setStatus("ok");
        setInfo({ app: data.app, version: data.version, local_only_mode: data.local_only_mode });
      })
      .catch(() => setStatus("error"));
  }, []);

  const colors: Record<HealthStatus, string> = {
    loading: "bg-yellow-100 text-yellow-700 border-yellow-300",
    ok: "bg-green-100 text-green-700 border-green-300",
    error: "bg-red-100 text-red-700 border-red-300",
  };

  const labels: Record<HealthStatus, string> = {
    loading: "Checking backend…",
    ok: `Backend OK — ${info.app} v${info.version}`,
    error: "Backend unreachable",
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span
        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-medium ${colors[status]}`}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            status === "ok"
              ? "bg-green-500"
              : status === "error"
              ? "bg-red-500"
              : "bg-yellow-500 animate-pulse"
          }`}
        />
        {labels[status]}
      </span>
      {status === "ok" && info.local_only_mode === true && (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-sky-200 bg-sky-100 text-sky-700 text-xs font-semibold">
          <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
          Local-only mode
        </span>
      )}
    </div>
  );
}
