import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { CrawlRuns } from "./pages/CrawlRuns";
import { CommandCenter } from "./pages/CommandCenter";
import { Documents } from "./pages/Documents";
import { Frontier } from "./pages/Frontier";
import { SearchCorpus } from "./pages/SearchCorpus";
import { RunScopeProvider } from "./state/run-scope";

export function App() {
  return (
    <RunScopeProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<CommandCenter />} />
          <Route path="/crawls" element={<CrawlRuns />} />
          <Route path="/frontier" element={<Frontier />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/search" element={<SearchCorpus />} />
        </Routes>
      </AppShell>
    </RunScopeProvider>
  );
}
