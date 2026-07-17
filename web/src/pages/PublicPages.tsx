import {
  ArrowRight,
  ArrowUpRight,
  Braces,
  Check,
  CircleOff,
  Clock3,
  Database,
  FileArchive,
  Gauge,
  GitBranch,
  Github,
  KeyRound,
  Network,
  Play,
  RefreshCcw,
  Search,
  ServerCog,
  ShieldCheck,
  TimerReset,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { PublicShell } from "../components/PublicShell";
import { useRuntime } from "../state/runtime";

const stages = [
  { index: "01", name: "Discover", detail: "Normalize, scope, deduplicate, and schedule URLs." },
  { index: "02", name: "Fetch", detail: "Enforce robots, DNS pins, byte limits, and politeness." },
  { index: "03", name: "Extract", detail: "Version parsers, classify change, and preserve source HTML." },
  { index: "04", name: "Index", detail: "Commit through a durable outbox into versioned search indexes." },
];

export function ProductHome() {
  const { runtime, browserVerified } = useRuntime();
  return (
    <PublicShell>
      <section className="hero-section">
        <div className="hero-copy">
          <span className="public-eyebrow">DISTRIBUTED CRAWL &amp; CORPUS SYSTEM</span>
          <h1>The web changes.<br />Atlas keeps the receipts.</h1>
          <p>
            A durable crawl, extraction, versioning, and search platform where PostgreSQL owns the
            truth, workers may disappear, and every operational claim is traceable to persisted evidence.
          </p>
          <div className="hero-actions">
            <Link className="public-primary" to="/architecture">
              Explore the system <ArrowRight size={15} />
            </Link>
            <Link className="public-secondary" to="/console">
              Inspect console <ArrowUpRight size={15} />
            </Link>
          </div>
        </div>
        <div className="hero-instrument" aria-label="Atlas runtime state">
          <div className="instrument-topline">
            <span>RUNTIME / PUBLIC SIGNAL</span>
            <RuntimeBadge state={runtime.state} verified={browserVerified} />
          </div>
          <div className="orbit-field" aria-hidden="true">
            <div className="orbit orbit-a"><span /></div>
            <div className="orbit orbit-b"><span /></div>
            <div className="orbit orbit-c"><span /></div>
            <div className="orbit-core">A</div>
          </div>
          <div className="instrument-readout">
            <div><span>ENVIRONMENT</span><strong>{runtime.environmentId ?? "PARKED"}</strong></div>
            <div><span>LIVE ACTIONS</span><strong>{browserVerified ? "ENABLED" : "LOCKED"}</strong></div>
          </div>
          <p>{runtime.message}</p>
        </div>
      </section>

      <section className="manifesto-strip" aria-label="System guarantees">
        <span><Database size={15} /> PostgreSQL is authoritative</span>
        <span><RefreshCcw size={15} /> Every stage is replayable</span>
        <span><ShieldCheck size={15} /> Public-address fetch policy</span>
        <span><Gauge size={15} /> Persisted telemetry only</span>
      </section>

      <section className="public-section stage-section">
        <div className="section-intro">
          <span className="public-eyebrow">THE DATA PLANE</span>
          <h2>Four stages. One recoverable record.</h2>
          <p>Redis wakes workers. It never decides what work exists.</p>
        </div>
        <div className="stage-grid">
          {stages.map((stage) => (
            <article key={stage.index}>
              <span>{stage.index}</span>
              <h3>{stage.name}</h3>
              <p>{stage.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="public-section split-feature">
        <div className="section-intro">
          <span className="public-eyebrow">FAILURE IS AN INPUT</span>
          <h2>Designed for the moment a worker vanishes.</h2>
        </div>
        <div className="guarantee-list">
          <Guarantee number="01" title="Transactional leases" text="Opaque lease tokens prevent stale workers from committing a superseded result." />
          <Guarantee number="02" title="Durable indexing outbox" text="Search outages retry the index operation, never the network fetch." />
          <Guarantee number="03" title="Immutable crawl executions" text="Reusable definitions produce distinct runs with frozen configuration snapshots." />
          <Guarantee number="04" title="Fail-closed showcase" text="When AWS is absent, the site makes zero crawler requests and invents zero metrics." />
        </div>
      </section>

      <section className="closing-callout">
        <span className="public-eyebrow">READ THE ENGINEERING RECORD</span>
        <h2>Architecture, threat boundaries, runbooks, and measured evidence.</h2>
        <Link to="/docs">Open documentation <ArrowRight size={15} /></Link>
      </section>
    </PublicShell>
  );
}

function Guarantee({ number, title, text }: { number: string; title: string; text: string }) {
  return (
    <article className="guarantee-row">
      <span>{number}</span>
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

export function ArchitecturePage() {
  const components = [
    { icon: Network, title: "FastAPI control plane", text: "OIDC-protected APIs, role checks, audit events, rate limits, and cursor-based inspection." },
    { icon: Database, title: "PostgreSQL state machine", text: "Runs, frontier records, stage tasks, leases, observations, versions, incidents, and metric samples." },
    { icon: ServerCog, title: "Disposable workers", text: "Fetch, extract, and index consumers heartbeat while processing recoverable leased work." },
    { icon: Search, title: "Versioned OpenSearch", text: "Stable relevance rules, filters, facets, aliases, and rebuilds driven by a durable outbox." },
    { icon: FileArchive, title: "Encrypted object archive", text: "Raw HTML remains available for parser comparison and reprocessing without refetching." },
    { icon: KeyRound, title: "Cognito trust boundary", text: "Viewer and administrator roles are verified at the API, not trusted from browser state." },
  ];
  return (
    <PublicShell>
      <PageLead eyebrow="SYSTEM DESIGN" title="The database remembers. The fleet executes." description="Atlas separates durable intent from disposable compute. Queue delivery can be lost or duplicated without losing crawl work or repeating completed stages." />
      <section className="architecture-flow" aria-label="Atlas request flow">
        <FlowNode label="VITE / VERCEL" detail="Permanent interface" />
        <span className="flow-arrow">→</span>
        <FlowNode label="FASTAPI / ECS" detail="Authenticated control" />
        <span className="flow-arrow">→</span>
        <FlowNode label="POSTGRES / RDS" detail="Authoritative state" emphasis />
        <span className="flow-arrow">↔</span>
        <FlowNode label="WORKERS / ECS" detail="Leased execution" />
        <span className="flow-arrow">→</span>
        <FlowNode label="S3 + OPENSEARCH" detail="Evidence and retrieval" />
      </section>
      <section className="public-section component-grid">
        {components.map(({ icon: Icon, title, text }) => (
          <article key={title}>
            <Icon size={21} strokeWidth={1.5} />
            <h2>{title}</h2>
            <p>{text}</p>
          </article>
        ))}
      </section>
      <section className="public-section failure-table">
        <div className="section-intro">
          <span className="public-eyebrow">RECOVERY CONTRACT</span>
          <h2>What happens when infrastructure fails?</h2>
        </div>
        <div className="architecture-table" role="table" aria-label="Failure recovery behavior">
          <div className="architecture-row table-heading" role="row"><span>Failure</span><span>Detection</span><span>Recovery</span></div>
          <RecoveryRow failure="Worker termination" detection="Lease heartbeat expires" recovery="Scheduler releases the task with a new token" />
          <RecoveryRow failure="Redis loss" detection="Notification delivery stops" recovery="PostgreSQL scan republishes eligible tasks" />
          <RecoveryRow failure="OpenSearch outage" detection="Outbox operation fails" recovery="Index stage retries without refetching" />
          <RecoveryRow failure="Stale worker commit" detection="Lease token mismatch" recovery="Commit is rejected; current owner remains authoritative" />
          <RecoveryRow failure="Invalid public runtime" detection="Schema validation fails" recovery="Vercel endpoint returns intentional offline state" />
        </div>
      </section>
    </PublicShell>
  );
}

function FlowNode({ label, detail, emphasis = false }: { label: string; detail: string; emphasis?: boolean }) {
  return <div className={`flow-node ${emphasis ? "flow-emphasis" : ""}`}><strong>{label}</strong><span>{detail}</span></div>;
}

function RecoveryRow({ failure, detection, recovery }: { failure: string; detection: string; recovery: string }) {
  return <div className="architecture-row" role="row"><strong>{failure}</strong><span>{detection}</span><span>{recovery}</span></div>;
}

const requiredFaultScenarios = [
  "duplicate-delivery",
  "expired-leases",
  "malformed-html",
  "opensearch-outage",
  "oversized-response",
  "postgres-reconnect",
  "redirects",
  "redis-loss",
  "robots-exclusion",
  "worker-termination",
] as const;

interface BenchmarkReport {
  schemaVersion: number;
  runId: string;
  verifiedAt: string;
  gitCommit: string;
  corpusSize: number;
  corpusVersion: number;
  crawlTargetCount: number;
  frontierCount: number;
  elapsedSeconds: number;
  indexedDocuments: number;
  terminalStates: Record<string, number>;
  invariants: {
    allEligibleUrlsTerminal: boolean;
    countersConsistent: boolean;
    indexMatchesPostgres: boolean;
    noStaleLeases: boolean;
    oneCurrentVersionPerResource: boolean;
    politenessRespected: boolean;
  };
  faultScenarios: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isBenchmarkReport(value: unknown): value is BenchmarkReport {
  if (!isRecord(value) || !isRecord(value.invariants) || !isRecord(value.terminalStates)) return false;

  const numericFields = [
    value.schemaVersion,
    value.corpusSize,
    value.corpusVersion,
    value.crawlTargetCount,
    value.frontierCount,
    value.elapsedSeconds,
    value.indexedDocuments,
  ];
  const invariantFields = [
    value.invariants.allEligibleUrlsTerminal,
    value.invariants.countersConsistent,
    value.invariants.indexMatchesPostgres,
    value.invariants.noStaleLeases,
    value.invariants.oneCurrentVersionPerResource,
    value.invariants.politenessRespected,
  ];
  const terminalCounts = Object.values(value.terminalStates);
  const faultScenarios = Array.isArray(value.faultScenarios) ? value.faultScenarios : [];

  return (
    value.schemaVersion === 1 &&
    numericFields.every((field) => typeof field === "number" && Number.isFinite(field) && field >= 0) &&
    typeof value.runId === "string" && value.runId.length > 0 &&
    typeof value.verifiedAt === "string" &&
    typeof value.gitCommit === "string" && /^[0-9a-f]{40}$/i.test(value.gitCommit) &&
    invariantFields.every((field) => field === true) &&
    terminalCounts.length > 0 &&
    terminalCounts.every((count) => typeof count === "number" && Number.isInteger(count) && count >= 0) &&
    terminalCounts.reduce<number>((total, count) => total + (count as number), 0) === value.frontierCount &&
    value.terminalStates.indexed === value.indexedDocuments &&
    faultScenarios.length === requiredFaultScenarios.length &&
    faultScenarios.every((scenario) => typeof scenario === "string") &&
    requiredFaultScenarios.every((scenario) => faultScenarios.includes(scenario))
  );
}

async function fetchBenchmark(): Promise<BenchmarkReport | null> {
  const response = await fetch("/benchmarks/latest.json", { headers: { Accept: "application/json" } });
  if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) return null;
  const report: unknown = await response.json();
  return isBenchmarkReport(report) ? report : null;
}

export function BenchmarksPage() {
  const report = useQuery({ queryKey: ["benchmark-report"], queryFn: fetchBenchmark, retry: false });
  return (
    <PublicShell>
      <PageLead eyebrow="VERIFIED EVIDENCE" title="Measured runs, or an honest blank." description="This page renders only checked-in artifacts emitted by the deterministic benchmark harness. There are no seeded charts and no estimated throughput numbers." />
      {report.isLoading ? <div className="evidence-empty">Reading the signed benchmark artifact…</div> : null}
      {!report.isLoading && !report.data ? (
        <div className="evidence-empty">
          <CircleOff size={28} />
          <h2>No release benchmark has been published yet.</h2>
          <p>The production gate stays incomplete until the 10,000-page corpus and failure matrix pass.</p>
        </div>
      ) : null}
      {report.data ? <BenchmarkEvidence report={report.data} /> : null}
    </PublicShell>
  );
}

function BenchmarkEvidence({ report }: { report: BenchmarkReport }) {
  const terminalUrls = Object.values(report.terminalStates).reduce((total, count) => total + count, 0);
  const cards = [
    ["Corpus", report.corpusSize.toLocaleString()],
    ["Crawl targets", report.crawlTargetCount.toLocaleString()],
    ["Frontier URLs", report.frontierCount.toLocaleString()],
    ["Indexed", report.indexedDocuments.toLocaleString()],
    ["Terminal URLs", terminalUrls.toLocaleString()],
    ["Elapsed", `${report.elapsedSeconds.toFixed(1)}s`],
  ];
  const invariants: [string, boolean][] = [
    ["All eligible URLs terminal", report.invariants.allEligibleUrlsTerminal],
    ["Counters consistent", report.invariants.countersConsistent],
    ["Index matches PostgreSQL", report.invariants.indexMatchesPostgres],
    ["No stale leases", report.invariants.noStaleLeases],
    ["One current version per resource", report.invariants.oneCurrentVersionPerResource],
    ["Politeness respected", report.invariants.politenessRespected],
  ];
  return (
    <section className="benchmark-evidence">
      <div className="evidence-meta">
        <span>VERIFIED {new Date(report.verifiedAt).toLocaleString()}</span>
        <code>{report.gitCommit}</code>
      </div>
      <div className="evidence-grid">{cards.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <div className="scenario-list">
        {invariants.map(([name, passed]) => <div key={name}><Check size={15} /><span>{name}</span><strong>{passed ? "PASS" : "FAIL"}</strong></div>)}
        {report.faultScenarios.map((scenario) => <div key={scenario}><Check size={15} /><span>{scenario}</span><strong>PASS</strong></div>)}
      </div>
    </section>
  );
}

export function DocumentationPage() {
  return (
    <PublicShell>
      <PageLead eyebrow="ENGINEERING RECORD" title="Operate Atlas from a clean checkout." description="The repository is organized around reproducibility: architecture decisions, threat boundaries, service runbooks, infrastructure profiles, migrations, and release evidence live beside the code." />
      <section className="docs-layout">
        <aside className="docs-index">
          <span>ON THIS PAGE</span>
          <a href="#principles">Operating principles</a><a href="#interfaces">Interfaces</a><a href="#release">Release sequence</a><a href="#artifacts">Repository artifacts</a>
        </aside>
        <div className="docs-content">
          <DocSection id="principles" icon={<ShieldCheck size={18} />} title="Operating principles">
            <ul><li>PostgreSQL is the source of truth for work and state transitions.</li><li>External writes are idempotent and separated from network fetches.</li><li>Every crawl execution freezes configuration and remains independently inspectable.</li><li>Public fetches resolve to pinned public addresses and revalidate every redirect.</li></ul>
          </DocSection>
          <DocSection id="interfaces" icon={<Braces size={18} />} title="API surface">
            <CodeLine value="POST /api/v1/crawl-definitions" detail="Create reusable policy and schedule" />
            <CodeLine value="POST /api/v1/crawl-definitions/{id}/trigger" detail="Create immutable execution" />
            <CodeLine value="GET  /api/v1/operations/tasks" detail="Inspect stage state and leases" />
            <CodeLine value="GET  /api/v1/documents/{id}/versions" detail="Read document history" />
            <CodeLine value="POST /api/v1/operations/index-builds" detail="Build and verify a new index" />
          </DocSection>
          <DocSection id="release" icon={<GitBranch size={18} />} title="On-demand release">
            <ol><li>Publish <code>starting</code> to Edge Config.</li><li>Apply the expiring Terraform environment.</li><li>Migrate, authenticate, and execute a controlled crawl.</li><li>Publish <code>online</code> only after browser-independent verification.</li><li>Drain, export evidence, publish <code>offline</code>, and prove teardown is clean.</li></ol>
          </DocSection>
          <DocSection id="artifacts" icon={<FileArchive size={18} />} title="Repository artifacts">
            <p>ADRs explain consequential choices. The threat model captures SSRF and tenant boundaries. Runbooks cover launch, incidents, recovery, and teardown. Benchmark JSON and screenshots are release artifacts, never hand-authored telemetry.</p>
          </DocSection>
        </div>
      </section>
    </PublicShell>
  );
}

function DocSection({ id, icon, title, children }: { id: string; icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return <section id={id} className="doc-section"><header>{icon}<h2>{title}</h2></header>{children}</section>;
}

function CodeLine({ value, detail }: { value: string; detail: string }) {
  return <div className="code-line"><code>{value}</code><span>{detail}</span></div>;
}

export function DemoPage() {
  const recording = import.meta.env.VITE_DEMO_RECORDING_URL as string | undefined;
  return (
    <PublicShell>
      <PageLead eyebrow="PRODUCT WALKTHROUGH" title="Watch a real crawl move through the system." description="The recording is published only after the same release candidate completes the controlled live workflow and teardown verification." />
      {recording ? (
        <div className="video-frame"><iframe src={recording} title="Atlas product demonstration" allowFullScreen /></div>
      ) : (
        <div className="evidence-empty demo-empty"><Play size={30} /><h2>Release recording pending.</h2><p>No placeholder video is being presented as a working demonstration.</p></div>
      )}
      <section className="demo-sequence">
        <span>01 / CREATE DEFINITION</span><span>02 / MONITOR FRONTIER</span><span>03 / INSPECT VERSION DIFF</span><span>04 / RECOVER DEAD LETTER</span><span>05 / REBUILD INDEX</span>
      </section>
    </PublicShell>
  );
}

export function RuntimeStatusPage() {
  const { runtime, browserVerified, isLoading, refresh } = useRuntime();
  const state = runtime.state === "online" && !browserVerified && !isLoading ? "degraded" : runtime.state;
  return (
    <PublicShell>
      <PageLead eyebrow="PUBLIC RUNTIME SIGNAL" title="The interface stays up. Compute does not have to." description="Atlas publishes a small, fail-closed state document from Vercel. The browser separately probes the advertised backend before it unlocks the console." />
      <section className="runtime-card-large">
        <div className="runtime-state-line"><RuntimeBadge state={state} verified={browserVerified} /><button type="button" onClick={refresh}><RefreshCcw size={14} /> Recheck</button></div>
        <h2>{runtime.message}</h2>
        <dl>
          <div><dt>Environment</dt><dd>{runtime.environmentId ?? "None"}</dd></div>
          <div><dt>Control plane verified</dt><dd>{browserVerified ? "Yes" : "No"}</dd></div>
          <div><dt>Last release verification</dt><dd>{runtime.lastVerifiedAt.startsWith("1970") ? "Never" : new Date(runtime.lastVerifiedAt).toLocaleString()}</dd></div>
          <div><dt>Automatic expiration</dt><dd>{runtime.demoExpiresAt ? new Date(runtime.demoExpiresAt).toLocaleString() : "Not running"}</dd></div>
        </dl>
      </section>
      <section className="public-section status-explainer">
        <article><Clock3 size={18} /><h2>Offline by design</h2><p>The cost-bearing AWS environment is destroyed between demonstrations. Documentation and evidence remain public.</p></article>
        <article><ShieldCheck size={18} /><h2>Fail closed</h2><p>Missing, malformed, stale, or unreachable runtime configuration never enables product actions.</p></article>
        <article><TimerReset size={18} /><h2>Expiring environments</h2><p>Every launch declares an expiration and receives a scheduled cleanup backstop.</p></article>
      </section>
    </PublicShell>
  );
}

export function SourcePage() {
  const repository = import.meta.env.VITE_GITHUB_REPOSITORY_URL as string | undefined;
  return (
    <PublicShell>
      <PageLead eyebrow="SOURCE & RELEASES" title="The implementation is part of the evidence." description="CI, infrastructure, migrations, security decisions, benchmark artifacts, and operating procedures are designed to be reviewed together." />
      <div className="source-card"><Github size={34} />{repository ? <><h2>Atlas on GitHub</h2><a href={repository} target="_blank" rel="noreferrer">Open repository <ArrowUpRight size={15} /></a></> : <><h2>Public repository publication pending.</h2><p>The link will appear only after CI and secret scanning pass on the public history.</p></>}</div>
    </PublicShell>
  );
}

function PageLead({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <header className="public-page-lead"><span className="public-eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></header>;
}

export function RuntimeBadge({ state, verified }: { state: string; verified: boolean }) {
  const label = state === "online" && !verified ? "verifying" : state;
  return <span className={`runtime-badge runtime-badge-${label}`}><span />{label}</span>;
}
