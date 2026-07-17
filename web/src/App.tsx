import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { AuthCallback, ConsoleGate } from "./components/ConsoleGate";
import { CrawlRuns } from "./pages/CrawlRuns";
import { CommandCenter } from "./pages/CommandCenter";
import { Documents } from "./pages/Documents";
import { Frontier } from "./pages/Frontier";
import {
  CrawlDefinitions,
  DomainHealthPage,
  IncidentsPage,
  IndexFreshnessPage,
  ParserDebugger,
  TaskOperations,
  WorkerFleet,
} from "./pages/Operations";
import {
  ArchitecturePage,
  BenchmarksPage,
  DemoPage,
  DocumentationPage,
  ProductHome,
  RuntimeStatusPage,
  SourcePage,
} from "./pages/PublicPages";
import { SearchCorpus } from "./pages/SearchCorpus";
import { AuthProvider } from "./state/auth";
import { RunScopeProvider } from "./state/run-scope";
import { RuntimeProvider } from "./state/runtime";

export function App() {
  return (
    <RuntimeProvider>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<ProductHome />} />
          <Route path="/architecture" element={<ArchitecturePage />} />
          <Route path="/benchmarks" element={<BenchmarksPage />} />
          <Route path="/docs" element={<DocumentationPage />} />
          <Route path="/demo" element={<DemoPage />} />
          <Route path="/status" element={<RuntimeStatusPage />} />
          <Route path="/source" element={<SourcePage />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/console/*" element={<ConsoleApplication />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </RuntimeProvider>
  );
}

function ConsoleApplication() {
  return (
    <ConsoleGate>
      <RunScopeProvider>
        <AppShell>
          <Routes>
            <Route path="/console" element={<CommandCenter />} />
            <Route path="/console/crawls" element={<CrawlRuns />} />
            <Route path="/console/definitions" element={<CrawlDefinitions />} />
            <Route path="/console/frontier" element={<Frontier />} />
            <Route path="/console/documents" element={<Documents />} />
            <Route path="/console/search" element={<SearchCorpus />} />
            <Route path="/console/parsers" element={<ParserDebugger />} />
            <Route path="/console/domains" element={<DomainHealthPage />} />
            <Route path="/console/tasks" element={<TaskOperations />} />
            <Route path="/console/workers" element={<WorkerFleet />} />
            <Route path="/console/index" element={<IndexFreshnessPage />} />
            <Route path="/console/incidents" element={<IncidentsPage />} />
            <Route path="*" element={<Navigate to="/console" replace />} />
          </Routes>
        </AppShell>
      </RunScopeProvider>
    </ConsoleGate>
  );
}
