/* eslint-disable react-refresh/only-export-components */
import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";

import { configureApiBase } from "../api";

export type RuntimeState = "offline" | "starting" | "online" | "degraded" | "stopping";

export interface RuntimeRecord {
  state: RuntimeState;
  apiBaseUrl: string | null;
  environmentId: string | null;
  lastVerifiedAt: string;
  demoExpiresAt: string | null;
  message: string;
}

interface RuntimeValue {
  runtime: RuntimeRecord;
  authConfig: RuntimeAuthConfig | null;
  browserVerified: boolean;
  isLoading: boolean;
  refresh: () => void;
}

export interface RuntimeAuthConfig {
  mode: "oidc" | "disabled";
  domain: string;
  clientId: string;
}

const NEVER = "1970-01-01T00:00:00.000Z";
const OFFLINE: RuntimeRecord = {
  state: "offline",
  apiBaseUrl: null,
  environmentId: null,
  lastVerifiedAt: NEVER,
  demoExpiresAt: null,
  message: "The live crawler is parked. The permanent project record remains available.",
};

const RuntimeContext = createContext<RuntimeValue | null>(null);
const runtimeStates = new Set<RuntimeState>([
  "offline",
  "starting",
  "online",
  "degraded",
  "stopping",
]);

function parseRuntime(value: unknown): RuntimeRecord {
  if (!value || typeof value !== "object") return OFFLINE;
  const item = value as Partial<RuntimeRecord>;
  if (
    !item.state ||
    !runtimeStates.has(item.state) ||
    typeof item.message !== "string" ||
    typeof item.lastVerifiedAt !== "string" ||
    Number.isNaN(Date.parse(item.lastVerifiedAt)) ||
    (item.state === "online" && !item.apiBaseUrl)
  ) {
    return OFFLINE;
  }
  return {
    state: item.state,
    apiBaseUrl: typeof item.apiBaseUrl === "string" ? item.apiBaseUrl : null,
    environmentId: typeof item.environmentId === "string" ? item.environmentId : null,
    lastVerifiedAt: item.lastVerifiedAt,
    demoExpiresAt:
      typeof item.demoExpiresAt === "string" && !Number.isNaN(Date.parse(item.demoExpiresAt))
        ? item.demoExpiresAt
        : null,
    message: item.message,
  };
}

function developmentRuntime(): RuntimeRecord | null {
  const localUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (!import.meta.env.DEV || !localUrl) return null;
  const apiBaseUrl = localUrl.replace(/\/api\/v1\/?$/, "");
  return {
    state: "online",
    apiBaseUrl,
    environmentId: "local-development",
    lastVerifiedAt: new Date().toISOString(),
    demoExpiresAt: null,
    message: "Using the explicitly configured local Atlas runtime.",
  };
}

async function readRuntime(): Promise<RuntimeRecord> {
  const local = developmentRuntime();
  if (local) return local;
  const response = await fetch("/api/runtime", { headers: { Accept: "application/json" } });
  if (!response.ok) return OFFLINE;
  return parseRuntime(await response.json());
}

async function probeRuntime(apiBaseUrl: string): Promise<boolean> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/health`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) return false;
    const body = (await response.json()) as { status?: string; service?: string };
    return body.status === "ok" && body.service === "atlas-api";
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function readAuthConfig(apiBaseUrl: string): Promise<RuntimeAuthConfig | null> {
  try {
    const response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/auth/config`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    const value = (await response.json()) as Partial<RuntimeAuthConfig>;
    if (
      value.mode !== "oidc" ||
      typeof value.domain !== "string" ||
      !value.domain.startsWith("https://") ||
      typeof value.clientId !== "string" ||
      !value.clientId
    ) {
      return null;
    }
    return { mode: "oidc", domain: value.domain.replace(/\/$/, ""), clientId: value.clientId };
  } catch {
    return null;
  }
}

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const runtimeQuery = useQuery({
    queryKey: ["public-runtime"],
    queryFn: readRuntime,
    retry: false,
    refetchInterval: 15_000,
    staleTime: 5_000,
  });
  const runtime = runtimeQuery.data ?? OFFLINE;
  const healthQuery = useQuery({
    queryKey: ["runtime-health", runtime.apiBaseUrl],
    queryFn: () => probeRuntime(runtime.apiBaseUrl!),
    enabled: runtime.state === "online" && Boolean(runtime.apiBaseUrl),
    retry: false,
    refetchInterval: 10_000,
    staleTime: 3_000,
  });
  const browserVerified = runtime.state === "online" && healthQuery.data === true;
  const authQuery = useQuery({
    queryKey: ["runtime-auth", runtime.apiBaseUrl],
    queryFn: () => readAuthConfig(runtime.apiBaseUrl!),
    enabled: browserVerified && Boolean(runtime.apiBaseUrl),
    retry: false,
    staleTime: 30_000,
  });

  useEffect(() => {
    configureApiBase(browserVerified ? runtime.apiBaseUrl : null);
  }, [browserVerified, runtime.apiBaseUrl]);

  const value = useMemo<RuntimeValue>(
    () => ({
      runtime,
      authConfig: authQuery.data ?? null,
      browserVerified,
      isLoading:
        runtimeQuery.isLoading ||
        (runtime.state === "online" && healthQuery.isLoading) ||
        (browserVerified && authQuery.isLoading),
      refresh: () => {
        void runtimeQuery.refetch();
        if (runtime.apiBaseUrl) void healthQuery.refetch();
      },
    }),
    [runtime, authQuery.data, authQuery.isLoading, browserVerified, runtimeQuery, healthQuery],
  );

  return <RuntimeContext.Provider value={value}>{children}</RuntimeContext.Provider>;
}

export function useRuntime(): RuntimeValue {
  const context = useContext(RuntimeContext);
  if (!context) throw new Error("useRuntime must be used inside RuntimeProvider");
  return context;
}
