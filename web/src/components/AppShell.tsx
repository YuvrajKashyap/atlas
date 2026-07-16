import {
  Activity,
  BookOpenText,
  DatabaseZap,
  FileSearch,
  Globe2,
  ListTree,
  Menu,
  Orbit,
  Search,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useRunScope } from "../state/run-scope";
import { StatusChip } from "./primitives";

const navItems = [
  { to: "/", label: "Command center", icon: Activity },
  { to: "/crawls", label: "Crawl runs", icon: Orbit },
  { to: "/frontier", label: "Frontier", icon: ListTree },
  { to: "/documents", label: "Documents", icon: BookOpenText },
  { to: "/search", label: "Corpus search", icon: Search },
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
              end={to === "/"}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
            >
              <Icon size={17} strokeWidth={1.6} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="system-line">
            <DatabaseZap size={15} />
            <span>Persisted telemetry</span>
          </div>
          <div className="system-line">
            <FileSearch size={15} />
            <span>No simulated records</span>
          </div>
          <span className="build-label">BUILD / 0.1.0</span>
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
