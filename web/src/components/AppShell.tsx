import {
  Activity,
  AlertTriangle,
  BookOpenText,
  CalendarClock,
  DatabaseZap,
  FileCode2,
  FileSearch,
  Globe2,
  HardDrive,
  House,
  ListTree,
  Menu,
  Orbit,
  PanelsTopLeft,
  Search,
  ServerCog,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useRunScope } from "../state/run-scope";
import { StatusChip } from "./primitives";

const navItems = [
  { to: "/console", label: "Command center", icon: Activity },
  { to: "/console/crawls", label: "Crawl runs", icon: Orbit },
  { to: "/console/definitions", label: "Definitions", icon: CalendarClock },
  { to: "/console/frontier", label: "Frontier", icon: ListTree },
  { to: "/console/documents", label: "Documents", icon: BookOpenText },
  { to: "/console/search", label: "Corpus search", icon: Search },
  { to: "/console/parsers", label: "Parser debugger", icon: FileCode2 },
  { to: "/console/domains", label: "Domain health", icon: Globe2 },
  { to: "/console/tasks", label: "Tasks & dead letters", icon: PanelsTopLeft },
  { to: "/console/workers", label: "Workers", icon: ServerCog },
  { to: "/console/index", label: "Index & freshness", icon: HardDrive },
  { to: "/console/incidents", label: "Incidents", icon: AlertTriangle },
];

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { runs, selectedRun, selectedRunId, setSelectedRunId } = useRunScope();

  return (
    <div className="app-shell">
      <button
        className="mobile-menu"
        type="button"
        aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
        onClick={() => setMobileOpen((open) => !open)}
      >
        {mobileOpen ? <X size={19} /> : <Menu size={19} />}
      </button>
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="brand-lockup">
          <div className="atlas-mark" aria-hidden="true">
            <Globe2 size={23} strokeWidth={1.4} />
          </div>
          <div>
            <span className="brand-name">ATLAS</span>
            <span className="brand-subtitle">CRAWL OPERATIONS</span>
          </div>
        </div>

        <div className="run-scope">
          <label htmlFor="run-scope">ACTIVE SURVEY</label>
          <div className="select-wrap">
            <select
              id="run-scope"
              value={selectedRunId ?? ""}
              onChange={(event) => setSelectedRunId(event.target.value)}
              disabled={runs.length === 0}
            >
              {runs.length === 0 ? <option value="">No crawl runs</option> : null}
              {runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.name}
                </option>
              ))}
            </select>
          </div>
          {selectedRun ? <StatusChip status={selectedRun.status} /> : null}
        </div>

        <nav className="primary-nav" aria-label="Atlas navigation">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/console"}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
            >
              <Icon size={17} strokeWidth={1.6} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <NavLink className="system-line console-home-link" to="/">
            <House size={15} />
            <span>Project overview</span>
          </NavLink>
          <div className="system-line">
            <DatabaseZap size={15} />
            <span>Persisted telemetry</span>
          </div>
          <div className="system-line">
            <FileSearch size={15} />
            <span>No simulated records</span>
          </div>
          <span className="build-label">BUILD / 0.2.0-PRODUCTION</span>
        </div>
      </aside>
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Close navigation"
          className="sidebar-scrim"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
      <main className="main-content">{children}</main>
    </div>
  );
}
