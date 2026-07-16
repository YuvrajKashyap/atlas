/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import type { CrawlRun } from "../types";

interface RunScopeValue {
  runs: CrawlRun[];
  selectedRun: CrawlRun | null;
  selectedRunId: string | null;
  setSelectedRunId: (runId: string) => void;
  isLoading: boolean;
  error: Error | null;
}

const RunScopeContext = createContext<RunScopeValue | null>(null);
const STORAGE_KEY = "atlas:selected-run";
const EMPTY_RUNS: CrawlRun[] = [];

export function RunScopeProvider({ children }: { children: ReactNode }) {
  const [selectedRunId, setSelectedRunIdState] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY),
  );
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: api.listRuns,
    refetchInterval: 4_000,
  });
  const runs = runsQuery.data ?? EMPTY_RUNS;
  const effectiveRunId = runs.some((run) => run.id === selectedRunId)
    ? selectedRunId
    : (runs[0]?.id ?? null);

  const setSelectedRunId = (runId: string) => {
    setSelectedRunIdState(runId);
    localStorage.setItem(STORAGE_KEY, runId);
  };

  const value = useMemo<RunScopeValue>(
    () => ({
      runs,
      selectedRun: runs.find((run) => run.id === effectiveRunId) ?? null,
      selectedRunId: effectiveRunId,
      setSelectedRunId,
      isLoading: runsQuery.isLoading,
      error: runsQuery.error,
    }),
    [runs, effectiveRunId, runsQuery.isLoading, runsQuery.error],
  );

  return <RunScopeContext.Provider value={value}>{children}</RunScopeContext.Provider>;
}

export function useRunScope(): RunScopeValue {
  const context = useContext(RunScopeContext);
  if (!context) throw new Error("useRunScope must be used inside RunScopeProvider");
  return context;
}
