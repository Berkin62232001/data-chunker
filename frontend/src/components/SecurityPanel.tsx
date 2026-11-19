"use client";

import { useCallback, useState } from "react";
import {
  fetchSecurityReport,
  type InjectionWarning,
  type SecurityReport,
  type UploadSecurityInfo,
} from "@/lib/api";

type AsyncState = "idle" | "loading" | "success" | "error";

function Spinner({ className = "" }: { className?: string }) {
  return <div className={`border-2 border-t-transparent rounded-full animate-spin ${className}`} />;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
      {children}
    </p>
  );
}

function CheckRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={`shrink-0 font-bold ${ok ? "text-green-600" : "text-red-500"}`}>
        {ok ? "✓" : "✕"}
      </span>
      <span className="text-gray-600 w-36 shrink-0">{label}</span>
      {detail && <span className="text-gray-400 truncate">{detail}</span>}
    </div>
  );
}

function UploadSection({ info }: { info: UploadSecurityInfo }) {
  const formatBytes = (b: number) =>
    b < 1024 ? `${b} B` : b < 1024 * 1024 ? `${(b / 1024).toFixed(1)} KB` : `${(b / (1024 * 1024)).toFixed(1)} MB`;

  return (
    <div className="space-y-1">
      <SectionLabel>Upload Security</SectionLabel>
      <CheckRow label="Extension allowed" ok={info.extension_allowed} detail={info.extension} />
      <CheckRow label="Size within limit" ok={info.size_within_limit} detail={formatBytes(info.size_bytes)} />
      <CheckRow label="MIME allowed" ok={info.mime_allowed} detail={info.mime_type ?? "unknown"} />
    </div>
  );
}

function InjectionSection({ warnings, complete }: { warnings: InjectionWarning[]; complete: boolean }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <SectionLabel>Prompt Injection Scan</SectionLabel>
        {!complete && (
          <span className="text-xs text-gray-400">Scan unavailable — chunk first</span>
        )}
      </div>
      {complete && warnings.length === 0 && (
        <p className="text-xs text-green-600 font-medium">✓ No injection patterns detected</p>
      )}
      {complete && warnings.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-amber-700 font-semibold">
            ⚠ {warnings.length} suspicious chunk{warnings.length !== 1 ? "s" : ""} detected — content preserved for review
          </p>
          {warnings.map((w) => (
            <div key={w.chunk_id} className="rounded-lg border border-amber-200 bg-amber-50 p-2.5 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono text-gray-500 truncate">{w.chunk_id.slice(0, 20)}…</span>
                <span className="text-xs text-amber-700 font-medium">chunk #{w.chunk_index}</span>
              </div>
              <p className="text-xs text-gray-500">
                Pattern: <span className="font-mono text-amber-700">{w.matched_pattern}</span>
              </p>
              <p className="text-xs text-gray-600 line-clamp-2 font-mono whitespace-pre-wrap">
                {w.text_excerpt}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface SecurityPanelProps {
  documentId: string;
}

export function SecurityPanel({ documentId }: SecurityPanelProps) {
  const [state, setState] = useState<AsyncState>("idle");
  const [report, setReport] = useState<SecurityReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFetch = useCallback(async () => {
    setState("loading");
    setReport(null);
    setError(null);
    try {
      const data = await fetchSecurityReport(documentId);
      setReport(data);
      setState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report");
      setState("error");
    }
  }, [documentId]);

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <SectionLabel>Security Report</SectionLabel>
        {report && (
          <span className={[
            "px-2 py-0.5 rounded border text-xs font-semibold",
            report.local_only_mode
              ? "bg-sky-100 border-sky-200 text-sky-700"
              : "bg-gray-100 border-gray-200 text-gray-600",
          ].join(" ")}>
            {report.local_only_mode ? "Local-only mode ON" : "External calls enabled"}
          </span>
        )}
      </div>

      {state === "idle" && (
        <button
          onClick={handleFetch}
          className="w-full py-2 rounded-lg text-sm font-semibold bg-slate-700 text-white hover:bg-slate-600 transition-colors"
        >
          Run Security Report
        </button>
      )}

      {state === "loading" && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Spinner className="w-3 h-3 border-slate-400" /> Scanning…
        </div>
      )}

      {state === "error" && error && (
        <p className="text-xs text-red-600">{error}</p>
      )}

      {state === "success" && report && (
        <div className="space-y-4">
          <UploadSection info={report.upload} />

          <InjectionSection
            warnings={report.injection_warnings}
            complete={report.injection_scan_complete}
          />

          {/* Payload safety */}
          <div className="space-y-1">
            <SectionLabel>Payload Safety</SectionLabel>
            <CheckRow
              label="Safety notice present"
              ok={report.payload_safety.safety_instruction_present}
            />
            <p className="text-xs text-gray-400">
              {report.payload_safety.payloads_generated} payload{report.payload_safety.payloads_generated !== 1 ? "s" : ""} generated
            </p>
          </div>

          {/* Audit trail */}
          {report.recent_audit_entries.length > 0 && (
            <div className="space-y-1.5">
              <SectionLabel>Audit Trail ({report.recent_audit_entries.length} entries)</SectionLabel>
              <div className="space-y-1">
                {report.recent_audit_entries.map((entry, i) => {
                  const ts = typeof entry.timestamp === "string"
                    ? new Date(entry.timestamp).toLocaleTimeString()
                    : "";
                  return (
                    <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
                      <span className="shrink-0 w-16 text-gray-400 font-mono">{ts}</span>
                      <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 font-mono shrink-0">
                        {String(entry.event)}
                      </span>
                      {entry.provider != null && (
                        <span className="text-gray-400">{String(entry.provider)}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <button
            onClick={handleFetch}
            className="text-xs text-slate-500 hover:text-slate-700"
          >
            Refresh
          </button>
        </div>
      )}
    </div>
  );
}
