import { AlertTriangle, ArrowLeft, KeyRound, LoaderCircle, RadioTower } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../state/auth";
import { useRuntime } from "../state/runtime";

export function ConsoleGate({ children }: { children: ReactNode }) {
  const { runtime, browserVerified, isLoading } = useRuntime();
  const { accessToken, configured, signIn } = useAuth();
  const [authError, setAuthError] = useState<string | null>(null);
  const developmentBypass = import.meta.env.DEV && !configured;

  if (isLoading) return <ConsoleBoundary icon={<LoaderCircle className="spin" />} title="Verifying the control plane" detail="Atlas is checking the public runtime record and probing backend health." />;
  if (runtime.state !== "online" || !browserVerified) {
    return <ConsoleBoundary icon={<RadioTower />} title="The live console is parked" detail={runtime.message}><Link className="public-secondary" to="/status">View runtime status</Link></ConsoleBoundary>;
  }
  if (!configured && !developmentBypass) {
    return <ConsoleBoundary icon={<AlertTriangle />} title="Authentication is not configured" detail="The backend is live, but Atlas will not expose an unauthenticated production console." />;
  }
  if (!accessToken && !developmentBypass) {
    return (
      <ConsoleBoundary icon={<KeyRound />} title="Authenticate to enter the console" detail="Cognito issues the access token; the API independently enforces viewer and administrator roles.">
        <button className="public-primary" type="button" onClick={() => { setAuthError(null); void signIn().catch((error: unknown) => setAuthError(error instanceof Error ? error.message : "Unable to start login")); }}>Sign in with Cognito</button>
        {authError ? <p className="boundary-error">{authError}</p> : null}
      </ConsoleBoundary>
    );
  }
  return children;
}

function ConsoleBoundary({ icon, title, detail, children }: { icon: ReactNode; title: string; detail: string; children?: ReactNode }) {
  return <main className="console-boundary"><Link className="boundary-back" to="/"><ArrowLeft size={14} /> Project overview</Link><div className="boundary-card"><span className="boundary-icon">{icon}</span><span className="public-eyebrow">OPERATIONAL CONSOLE</span><h1>{title}</h1><p>{detail}</p>{children ? <div className="boundary-actions">{children}</div> : null}</div></main>;
}

export function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { completeCallback } = useAuth();
  const started = useRef(false);
  const [exchangeError, setExchangeError] = useState<string | null>(null);
  const code = params.get("code");
  const state = params.get("state");
  const responseError =
    !code || !state
      ? (params.get("error_description") ?? "The authorization response is incomplete")
      : null;

  useEffect(() => {
    if (started.current || !code || !state) return;
    started.current = true;
    void completeCallback(code, state).then(() => navigate("/console", { replace: true })).catch((reason: unknown) => setExchangeError(reason instanceof Error ? reason.message : "Authentication failed"));
  }, [code, completeCallback, navigate, state]);

  const error = responseError ?? exchangeError;

  return error ? <ConsoleBoundary icon={<AlertTriangle />} title="Authentication failed" detail={error}><Link className="public-secondary" to="/console">Return to console</Link></ConsoleBoundary> : <ConsoleBoundary icon={<LoaderCircle className="spin" />} title="Completing authentication" detail="Atlas is exchanging the one-time authorization code." />;
}
