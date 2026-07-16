import { ExternalLink, FileText, Search, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";

import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/primitives";
import { formatDate, formatNumber, formatPercent } from "../lib/format";
import { useRunScope } from "../state/run-scope";

export function Documents() {
  const { selectedRunId, selectedRun } = useRunScope();
  const [query, setQuery] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const deferredQuery = useDeferredValue(query);
  const documentsQuery = useQuery({
    queryKey: ["documents", selectedRunId, deferredQuery],
    queryFn: () => api.documents(selectedRunId!, deferredQuery),
    enabled: Boolean(selectedRunId),
    refetchInterval: selectedRun?.status === "running" ? 5_000 : 20_000,
  });

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="EXTRACTED CORPUS"
        title="Document explorer"
        description="Trace parsed documents back to their frontier entries, extraction quality, and canonical source."
      />
      {!selectedRunId ? (
        <EmptyState
          title="No active survey"
          detail="Create or select a crawl run before exploring extracted documents."
          action={{ label: "Open crawl registry", to: "/crawls" }}
        />
      ) : (
        <>
          <div className="filter-bar">
            <label className="search-field">
              <Search size={16} />
              <span className="sr-only">Filter documents</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filter by title or URL"
              />
            </label>
            <span className="record-count">
              {documentsQuery.data ? `${formatNumber(documentsQuery.data.total)} documents` : "— documents"}
            </span>
          </div>
          {documentsQuery.isLoading ? <LoadingState label="Reading document corpus" /> : null}
          {documentsQuery.error ? <ErrorState error={documentsQuery.error} /> : null}
          {documentsQuery.data?.items.length === 0 ? (
            <EmptyState title="No documents found" detail="Documents appear after HTML has been fetched and extracted." />
          ) : null}
          {documentsQuery.data && documentsQuery.data.items.length > 0 ? (
            <div className="document-grid">
              {documentsQuery.data.items.map((document) => (
                <button
                  type="button"
                  className="document-card"
                  key={document.id}
                  onClick={() => setSelectedDocumentId(document.id)}
                >
                  <div className="document-card-top">
                    <FileText size={18} />
                    <span>{document.language?.toUpperCase() ?? "—"}</span>
                  </div>
                  <h2>{document.title ?? "Untitled document"}</h2>
                  <p>{document.description ?? document.url}</p>
                  <dl>
                    <div><dt>Text</dt><dd>{formatNumber(document.text_length)} chars</dd></div>
                    <div><dt>Confidence</dt><dd>{formatPercent(document.extraction_confidence)}</dd></div>
                  </dl>
                  <footer>
                    <span>{document.host}</span>
                    <time dateTime={document.extracted_at}>{formatDate(document.extracted_at)}</time>
                  </footer>
                </button>
              ))}
            </div>
          ) : null}
        </>
      )}
      {selectedDocumentId ? (
        <DocumentDrawer documentId={selectedDocumentId} onClose={() => setSelectedDocumentId(null)} />
      ) : null}
    </div>
  );
}

function DocumentDrawer({ documentId, onClose }: { documentId: string; onClose: () => void }) {
  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.document(documentId),
  });

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="document-drawer"
        aria-label="Document details"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <span className="eyebrow">DOCUMENT RECORD</span>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close details">
            <X size={18} />
          </button>
        </header>
        {documentQuery.isLoading ? <LoadingState /> : null}
        {documentQuery.error ? <ErrorState error={documentQuery.error} /> : null}
        {documentQuery.data ? (
          <article className="drawer-content">
            <h2>{documentQuery.data.title ?? "Untitled document"}</h2>
            <a href={documentQuery.data.url} target="_blank" rel="noreferrer">
              {documentQuery.data.url} <ExternalLink size={13} />
            </a>
            <dl className="definition-grid">
              <div><dt>Language</dt><dd>{documentQuery.data.language ?? "—"}</dd></div>
              <div><dt>Confidence</dt><dd>{formatPercent(documentQuery.data.extraction_confidence)}</dd></div>
              <div><dt>Parser</dt><dd>{documentQuery.data.parser_name}</dd></div>
              <div><dt>Hash</dt><dd className="hash-value">{documentQuery.data.content_hash.slice(0, 12)}</dd></div>
            </dl>
            {documentQuery.data.headings.length ? (
              <section>
                <h3>Outline</h3>
                <ol className="heading-list">
                  {documentQuery.data.headings.map((heading, index) => (
                    <li key={`${heading}-${index}`}>{heading}</li>
                  ))}
                </ol>
              </section>
            ) : null}
            <section>
              <h3>Extracted main text</h3>
              <p className="main-text">{documentQuery.data.main_text}</p>
            </section>
          </article>
        ) : null}
      </aside>
    </div>
  );
}
