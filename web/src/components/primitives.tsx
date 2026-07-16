import { AlertTriangle, ArrowRight, LoaderCircle, Radar } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { FrontierStatus, RunStatus } from "../types";

type Status = FrontierStatus | RunStatus | "ok" | "degraded" | "offline";

export function StatusChip({ status }: { status: Status }) {
  return (
    <span className={`status-chip status-${status}`}>
      <span className="status-dot" aria-hidden="true" />
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function LoadingState({ label = "Reading telemetry" }: { label?: string }) {
  return (
    <div className="center-state" role="status">
      <LoaderCircle className="spin" size={22} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ error }: { error: Error }) {
  return (
    <div className="center-state error-state" role="alert">
      <AlertTriangle size={22} />
      <div>
        <strong>Telemetry unavailable</strong>
        <p>{error.message}</p>
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: { label: string; to: string };
}) {
  return (
    <div className="empty-state">
      <Radar size={30} strokeWidth={1.4} />
      <h3>{title}</h3>
      <p>{detail}</p>
      {action ? (
        <Link className="text-link" to={action.to}>
          {action.label} <ArrowRight size={14} />
        </Link>
      ) : null}
    </div>
  );
}

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <div>
          {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
          <h2>{title}</h2>
        </div>
        {action}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}
