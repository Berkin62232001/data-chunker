"use client";

import { useEffect, useMemo, useState } from "react";
import { listRecentAudit, type AuditEventItem } from "@/lib/api";

const EVENT_COLORS: Record<string, string> = {
  upload:    "bg-blue-100 text-blue-700",
  profile:   "bg-indigo-100 text-indigo-700",
  pipeline:  "bg-purple-100 text-purple-700",
  convert:   "bg-amber-100 text-amber-700",
  chunk:     "bg-green-100 text-green-700",
  integrity: "bg-teal-100 text-teal-700",
  llm_call:  "bg-emerald-100 text-emerald-700",
  security:  "bg-slate-100 text-slate-700",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString();
}

const ALL_EVENTS = "all";

export default function ActivityPage() {
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventTypeFilter, setEventTypeFilter] = useState(ALL_EVENTS);
  const [limit, setLimit] = useState(100);

  useEffect(() => {
    listRecentAudit(200)
      .then((data) => {
        setEvents(data.events);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load activity");
        setLoading(false);
      });
  }, []);

  const eventTypes = useMemo(() => {
    const types = new Set(events.map((e) => e.event_type));
    return [ALL_EVENTS, ...Array.from(types).sort()];
  }, [events]);

  const filtered = useMemo(() => {
    let list = events;
    if (eventTypeFilter !== ALL_EVENTS) {
      list = list.filter((e) => e.event_type === eventTypeFilter);
    }
    return list.slice(0, limit);
  }, [events, eventTypeFilter, limit]);

  return (
    <main className="max-w-3xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Activity</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Audit log of all pipeline events.
        </p>
      </div>

      {/* Filters */}
      {!loading && !error && events.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          <select
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            {eventTypes.map((t) => (
              <option key={t} value={t}>
                {t === ALL_EVENTS ? "All event types" : t}
              </option>
            ))}
          </select>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            {[50, 100, 200].map((n) => (
              <option key={n} value={n}>Show {n}</option>
            ))}
          </select>
          <p className="text-xs text-gray-400 self-center">
            {filtered.length} event{filtered.length !== 1 ? "s" : ""}
            {filtered.length !== events.length ? ` (of ${events.length})` : ""}
          </p>
        </div>
      )}

      {loading && (
        <div className="space-y-1">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="rounded-lg border border-gray-200 bg-white p-3 animate-pulse h-10" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {!loading && !error && events.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 px-6 py-16 text-center text-sm text-gray-400">
          No activity yet. Upload and process a document to see events here.
        </div>
      )}

      {!loading && !error && events.length > 0 && filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-200 px-6 py-10 text-center text-sm text-gray-400">
          No events match the current filter.
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-50">
          {filtered.map((e) => {
            const color = EVENT_COLORS[e.event_type] ?? "bg-gray-100 text-gray-600";
            return (
              <div key={e.id} className="flex items-center gap-3 px-4 py-3">
                <span className={`px-2 py-0.5 rounded text-xs font-semibold shrink-0 ${color}`}>
                  {e.event_type}
                </span>
                <div className="flex-1 min-w-0">
                  {e.document_id && (
                    <a
                      href={`/documents/${e.document_id}`}
                      className="text-xs font-mono text-indigo-600 hover:text-indigo-800 truncate block"
                    >
                      doc:{e.document_id.slice(0, 24)}…
                    </a>
                  )}
                  {e.project_id && !e.document_id && (
                    <span className="text-xs font-mono text-gray-500 truncate block">
                      proj:{e.project_id.slice(0, 24)}…
                    </span>
                  )}
                  {!e.document_id && !e.project_id && (
                    <span className="text-xs text-gray-400">—</span>
                  )}
                </div>
                <span className="text-xs text-gray-400 shrink-0">{formatDate(e.created_at)}</span>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
