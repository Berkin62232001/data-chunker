"use client";

import { usePathname } from "next/navigation";

// Inline stroke icon set — no external library
function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    upload: '<path d="M12 16V4m0 0l-4 4m4-4l4 4"/><path d="M5 16v2a2 2 0 002 2h10a2 2 0 002-2v-2"/>',
    documents: '<path d="M8 3h6l5 5v11a2 2 0 01-2 2H8a2 2 0 01-2-2V5a2 2 0 012-2z"/><path d="M14 3v5h5"/><path d="M9.5 13h6M9.5 16.5h4"/>',
    projects: '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
    jobs: '<path d="M3 12h4l2 5 4-12 2 7h6"/>',
    activity: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    cube: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 3v18M4 7.5l8 4.5 8-4.5"/>',
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      dangerouslySetInnerHTML={{ __html: paths[name] ?? "" }}
    />
  );
}

const NAV = [
  { href: "/",          label: "Dashboard", icon: "dashboard", group: "workspace" },
  { href: "/upload",    label: "Upload",    icon: "upload",    group: "workspace" },
  { href: "/documents", label: "Documents", icon: "documents", group: "workspace" },
  { href: "/projects",  label: "Projects",  icon: "projects",  group: "organize" },
  { href: "/jobs",      label: "Jobs",      icon: "jobs",      group: "organize" },
  { href: "/activity",  label: "Activity",  icon: "activity",  group: "organize" },
];

export function Sidebar() {
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");

  return (
    <aside className="side w-[248px] shrink-0 flex flex-col h-screen sticky top-0">
      {/* Brand mark */}
      <div
        className="px-5 py-5 flex items-center gap-3"
        style={{ borderBottom: "1px solid var(--side-border)" }}
      >
        <div
          className="w-[34px] h-[34px] rounded-[10px] flex items-center justify-center shrink-0"
          style={{
            background: "linear-gradient(135deg, #7a4ff7, #3f6bf6)",
            boxShadow: "0 4px 14px -4px rgba(91,80,240,0.7)",
          }}
        >
          <Icon name="cube" size={19} />
        </div>
        <div>
          <p className="text-sm font-[680] text-white tracking-tight leading-tight">
            File Analyzer
          </p>
          <p className="text-[11px] mt-0.5" style={{ color: "var(--side-text-dim)" }}>
            RAG document pipeline
          </p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-3.5 flex flex-col gap-0.5 overflow-y-auto">
        {/* Workspace group */}
        <p
          className="text-[10px] font-semibold uppercase tracking-[0.1em] px-3 pt-2 pb-1.5"
          style={{ color: "var(--side-text-dim)" }}
        >
          Workspace
        </p>
        {NAV.filter((n) => n.group === "workspace").map(({ href, label, icon }) => {
          const active = isActive(href);
          return (
            <a
              key={href}
              href={href}
              className={[
                "flex items-center gap-2.5 px-3 py-2.5 rounded-[10px] text-[13.5px] font-medium transition-all",
                active ? "nav-active" : "hover:bg-[var(--side-hover)] hover:text-white",
              ].join(" ")}
              style={{ color: active ? "#fff" : "var(--side-text)" }}
            >
              <Icon name={icon} size={17} />
              {label}
            </a>
          );
        })}

        {/* Organize group */}
        <p
          className="text-[10px] font-semibold uppercase tracking-[0.1em] px-3 pt-4 pb-1.5"
          style={{ color: "var(--side-text-dim)" }}
        >
          Organize
        </p>
        {NAV.filter((n) => n.group === "organize").map(({ href, label, icon }) => {
          const active = isActive(href);
          return (
            <a
              key={href}
              href={href}
              className={[
                "flex items-center gap-2.5 px-3 py-2.5 rounded-[10px] text-[13.5px] font-medium transition-all",
                active ? "nav-active" : "hover:bg-[var(--side-hover)] hover:text-white",
              ].join(" ")}
              style={{ color: active ? "#fff" : "var(--side-text)" }}
            >
              <Icon name={icon} size={17} />
              {label}
            </a>
          );
        })}
      </nav>

      {/* Footer */}
      <div
        className="px-4 py-3.5 flex items-center justify-between"
        style={{ borderTop: "1px solid var(--side-border)" }}
      >
        <span
          className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold"
          style={{ background: "rgba(22,163,74,0.18)", color: "#4ade80" }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
          Local-only
        </span>
        <span className="font-mono text-[11px]" style={{ color: "var(--side-text-dim)" }}>
          v31
        </span>
      </div>
    </aside>
  );
}
