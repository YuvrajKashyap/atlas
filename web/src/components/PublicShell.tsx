import { ArrowUpRight, Github, Menu, Radar, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { useRuntime } from "../state/runtime";

const navigation = [
  { to: "/architecture", label: "Architecture" },
  { to: "/benchmarks", label: "Benchmarks" },
  { to: "/docs", label: "Documentation" },
  { to: "/demo", label: "Demo" },
  { to: "/status", label: "Runtime" },
];

export function PublicShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { runtime, browserVerified } = useRuntime();
  const effectiveState = runtime.state === "online" && !browserVerified ? "degraded" : runtime.state;

  return (
    <div className="public-shell">
      <header className="public-header">
        <Link to="/" className="public-brand" aria-label="Atlas home">
          <span className="public-mark" aria-hidden="true">
            <Radar size={19} strokeWidth={1.6} />
          </span>
          <span>ATLAS</span>
        </Link>
        <button
          type="button"
          className="public-menu-button"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
        <nav className={`public-nav ${open ? "public-nav-open" : ""}`} aria-label="Project">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setOpen(false)}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <Link className="console-link" to="/console">
          <span className={`runtime-pin runtime-${effectiveState}`} aria-hidden="true" />
          Open console
          <ArrowUpRight size={14} />
        </Link>
      </header>
      <main className="public-main">{children}</main>
      <footer className="public-footer">
        <div>
          <span className="public-brand footer-brand">ATLAS</span>
          <p>A durable, policy-aware web corpus platform built as an operating system for crawls.</p>
        </div>
        <div className="footer-links">
          <Link to="/source">
            <Github size={14} /> Source
          </Link>
          <Link to="/docs">Runbooks</Link>
          <Link to="/status">Runtime status</Link>
        </div>
        <span className="footer-note">REAL TELEMETRY ONLY / NO SIMULATED CHARTS</span>
      </footer>
    </div>
  );
}
