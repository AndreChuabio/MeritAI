"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  Citation,
  DraftDone,
  ExportResult,
  PluginResult,
  ResearchSummary,
  Venue,
} from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { StepHeader } from "./StepHeader";
import { SummaryEditor } from "./SummaryEditor";
import { VenueCard } from "./VenueCard";
import { DraftStream } from "./DraftStream";

const EMPTY_SUMMARY: ResearchSummary = {
  problem: "",
  contribution: "",
  method: "",
  results: "",
  limitations: "",
  keywords: [],
};

function summaryHasContent(summary: ResearchSummary): boolean {
  return (
    summary.problem.trim().length > 0 ||
    summary.contribution.trim().length > 0 ||
    summary.method.trim().length > 0 ||
    summary.results.trim().length > 0
  );
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function base64ToBlob(base64: string, type: string): Blob {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type });
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadText(text: string, filename: string, mime: string): void {
  downloadBlob(new Blob([text], { type: mime }), filename);
}

export default function ProductizePage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [summary, setSummary] = useState<ResearchSummary>(EMPTY_SUMMARY);
  const [summaryReady, setSummaryReady] = useState(false);
  const [ingestNotice, setIngestNotice] = useState<string | null>(null);
  const [ingestLoading, setIngestLoading] = useState(false);

  const [venues, setVenues] = useState<Venue[]>([]);
  const [selectedVenue, setSelectedVenue] = useState<Venue | null>(null);
  const [matchLoading, setMatchLoading] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);

  const [draftSections, setDraftSections] = useState<Record<string, string>>(
    {},
  );
  const [draftOrder, setDraftOrder] = useState<string[]>([]);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [draftStreaming, setDraftStreaming] = useState(false);
  const [draftStarted, setDraftStarted] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const draftAbort = useRef<AbortController | null>(null);

  const [exportResult, setExportResult] = useState<ExportResult | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const [plugin, setPlugin] = useState<PluginResult | null>(null);
  const [pluginLoading, setPluginLoading] = useState(false);
  const [pluginError, setPluginError] = useState<string | null>(null);

  const draftComplete = useMemo(
    () => draftStarted && !draftStreaming && draftOrder.length > 0,
    [draftStarted, draftStreaming, draftOrder.length],
  );

  const currentStep = useMemo(() => {
    if (draftStarted) return draftComplete ? 4 : 3;
    if (selectedVenue) return 3;
    if (summaryReady) return 2;
    return 1;
  }, [draftStarted, draftComplete, selectedVenue, summaryReady]);

  const recordSection = useCallback((name: string) => {
    if (!name) return;
    setDraftOrder((prev) => (prev.includes(name) ? prev : [...prev, name]));
  }, []);

  const handleIngest = useCallback(async () => {
    const url = repoUrl.trim();
    if (!url) return;
    setIngestLoading(true);
    setIngestNotice(null);
    try {
      const result = await api.ingest(url);
      setSummary({ ...EMPTY_SUMMARY, ...result.summary });
      setSummaryReady(true);
      if (result.notes) setIngestNotice(result.notes);
    } catch (err) {
      // Ingest can fail when the server GitHub token is unconfigured. Surface a
      // friendly note and let the user write the summary by hand.
      setIngestNotice(
        `Repo ingest is being configured (${errorMessage(err)}). You can paste or write the summary below and continue.`,
      );
      setSummary((prev) => (summaryHasContent(prev) ? prev : EMPTY_SUMMARY));
      setSummaryReady(true);
    } finally {
      setIngestLoading(false);
    }
  }, [repoUrl]);

  const handleManualStart = useCallback(() => {
    setSummaryReady(true);
    setIngestNotice(null);
  }, []);

  const handleMatch = useCallback(async () => {
    setMatchLoading(true);
    setMatchError(null);
    setSelectedVenue(null);
    try {
      const result = await api.match(summary, 6);
      setVenues(result);
      if (result.length === 0) {
        setMatchError("No venues came back. Try adding more detail above.");
      }
    } catch (err) {
      setMatchError(errorMessage(err));
    } finally {
      setMatchLoading(false);
    }
  }, [summary]);

  const handleDraft = useCallback(async () => {
    if (!selectedVenue) return;
    // Reset any previous run.
    draftAbort.current?.abort();
    const controller = new AbortController();
    draftAbort.current = controller;

    setDraftSections({});
    setDraftOrder([]);
    setActiveSection(null);
    setCitations([]);
    setDraftError(null);
    setExportResult(null);
    setDraftStarted(true);
    setDraftStreaming(true);

    await api.draft(
      summary,
      selectedVenue,
      {
        onDelta: (section, text) => {
          const name = section || "draft";
          recordSection(name);
          setActiveSection(name);
          setDraftSections((prev) => ({
            ...prev,
            [name]: (prev[name] ?? "") + text,
          }));
        },
        onSection: (section) => {
          recordSection(section);
          setActiveSection(section);
        },
        onDone: (done: DraftDone) => {
          if (done.sections) {
            setDraftSections((prev) => ({ ...prev, ...done.sections }));
            setDraftOrder((prev) => {
              const merged = [...prev];
              for (const key of Object.keys(done.sections)) {
                if (!merged.includes(key)) merged.push(key);
              }
              return merged;
            });
          }
          if (done.citations) setCitations(done.citations);
          setActiveSection(null);
          setDraftStreaming(false);
        },
        onError: (message) => {
          setDraftError(message);
          setActiveSection(null);
          setDraftStreaming(false);
        },
      },
      controller.signal,
    );

    // Guard: if the stream ended without a done event.
    setDraftStreaming(false);
    setActiveSection(null);
  }, [selectedVenue, summary, recordSection]);

  const handleExport = useCallback(async () => {
    if (!selectedVenue) return;
    setExportLoading(true);
    setExportError(null);
    try {
      const result = await api.exportPaper(
        summary,
        selectedVenue,
        draftSections,
        citations.length > 0 ? citations : undefined,
      );
      setExportResult(result);
    } catch (err) {
      setExportError(errorMessage(err));
    } finally {
      setExportLoading(false);
    }
  }, [selectedVenue, summary, draftSections, citations]);

  const handleExtractPlugin = useCallback(async () => {
    const url = repoUrl.trim();
    if (!url) {
      setPluginError("Add a repo URL at the top to extract a plugin.");
      return;
    }
    setPluginLoading(true);
    setPluginError(null);
    try {
      const result = await api.extractPlugin(url);
      setPlugin(result);
    } catch (err) {
      setPluginError(errorMessage(err));
    } finally {
      setPluginLoading(false);
    }
  }, [repoUrl]);

  const downloadPlugin = useCallback(() => {
    if (!plugin) return;
    const blob = base64ToBlob(plugin.zip_base64, "application/zip");
    downloadBlob(blob, `${plugin.plugin_name || "plugin"}.zip`);
  }, [plugin]);

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <Badge tone="pink">Productize</Badge>
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          Turn a repo into a paper
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-muted">
          Point us at a GitHub repo. We distill the research story, match it to
          venues, draft the paper live, then hand you the LaTeX and a packaged
          plugin.
        </p>
        <StepHeader current={currentStep} />
      </header>

      {/* Step 1: Ingest */}
      <section className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Badge tone="primary">1</Badge>
          <CardTitle>Ingest a repo</CardTitle>
        </div>
        <Card className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input
                label="GitHub repository URL"
                placeholder="https://github.com/owner/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !ingestLoading) handleIngest();
                }}
              />
            </div>
            <Button
              onClick={handleIngest}
              disabled={ingestLoading || repoUrl.trim().length === 0}
            >
              {ingestLoading ? <Spinner size={16} /> : null}
              {ingestLoading ? "Ingesting" : "Ingest repo"}
            </Button>
            {!summaryReady ? (
              <Button variant="ghost" onClick={handleManualStart}>
                Skip, write it myself
              </Button>
            ) : null}
          </div>
          {ingestNotice ? (
            <p className="rounded-2xl bg-warning/10 px-4 py-3 text-sm text-ink">
              {ingestNotice}
            </p>
          ) : null}
        </Card>
      </section>

      {/* Claude plugin: available as soon as there is a repo, independent of
          the paper flow. Only needs the repo URL. */}
      {repoUrl.trim().length > 0 ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Badge tone="lime">Also</Badge>
            <CardTitle>Package this repo as a Claude plugin</CardTitle>
          </div>
          <Card className="flex flex-col gap-3">
            <CardDescription>
              Extract a ready-to-install Claude Code plugin from the same repo:
              skills, slash commands, subagents, hooks, and MCP build prompts,
              bundled with a plugin.json. A shippable tool counts as an original
              contribution.
            </CardDescription>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Button
                variant="lime"
                onClick={handleExtractPlugin}
                disabled={pluginLoading}
              >
                {pluginLoading ? <Spinner size={16} /> : null}
                {pluginLoading
                  ? "Extracting"
                  : plugin
                    ? "Re-extract plugin"
                    : "Create Claude plugin"}
              </Button>
              {plugin ? (
                <Button variant="secondary" onClick={downloadPlugin}>
                  Download {plugin.plugin_name || "plugin"}.zip
                </Button>
              ) : null}
            </div>
            {plugin ? (
              <p className="text-xs text-muted">
                {plugin.manifest?.description ??
                  `Manifest: ${plugin.manifest?.name ?? plugin.plugin_name}`}
              </p>
            ) : null}
            {pluginError ? (
              <p className="text-sm text-danger">{pluginError}</p>
            ) : null}
          </Card>
        </section>
      ) : null}

      {/* Step 1b: Editable summary */}
      {summaryReady ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Badge tone="primary">1</Badge>
            <CardTitle>Research summary</CardTitle>
            <span className="text-sm text-muted">edit anything before matching</span>
          </div>
          <SummaryEditor
            summary={summary}
            onChange={setSummary}
            disabled={ingestLoading}
          />
          <div>
            <Button
              onClick={handleMatch}
              disabled={matchLoading || !summaryHasContent(summary)}
            >
              {matchLoading ? <Spinner size={16} /> : null}
              {matchLoading ? "Matching venues" : "Match venues"}
            </Button>
            {!summaryHasContent(summary) ? (
              <p className="mt-2 text-xs text-muted">
                Fill in at least the problem or contribution to match venues.
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      {/* Step 2: Venues */}
      {(venues.length > 0 || matchError) && summaryReady ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Badge tone="primary">2</Badge>
            <CardTitle>Pick a venue</CardTitle>
          </div>
          {matchError ? (
            <Card className="bg-danger/5">
              <CardDescription className="text-danger">
                {matchError}
              </CardDescription>
            </Card>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2">
            {venues.map((venue) => (
              <VenueCard
                key={`${venue.name}-${venue.type}`}
                venue={venue}
                selected={selectedVenue?.name === venue.name}
                onSelect={() => setSelectedVenue(venue)}
              />
            ))}
          </div>
          {selectedVenue ? (
            <div>
              <Button onClick={handleDraft} disabled={draftStreaming}>
                {draftStreaming ? <Spinner size={16} /> : null}
                {draftStreaming
                  ? "Drafting"
                  : draftStarted
                    ? `Redraft for ${selectedVenue.name}`
                    : `Draft for ${selectedVenue.name}`}
              </Button>
            </div>
          ) : null}
        </section>
      ) : null}

      {/* Step 3: Draft stream */}
      {draftStarted ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Badge tone="primary">3</Badge>
            <CardTitle>Live draft</CardTitle>
            {draftStreaming ? (
              <Badge tone="pink">streaming</Badge>
            ) : draftError ? (
              <Badge tone="danger">stopped</Badge>
            ) : (
              <Badge tone="success">complete</Badge>
            )}
          </div>
          {draftError ? (
            <Card className="bg-danger/5">
              <CardDescription className="text-danger">
                {draftError}
              </CardDescription>
            </Card>
          ) : null}
          <DraftStream
            order={draftOrder}
            sections={draftSections}
            activeSection={activeSection}
            streaming={draftStreaming}
          />
        </section>
      ) : null}

      {/* Step 4: Export + plugin */}
      {draftComplete ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Badge tone="primary">4</Badge>
            <CardTitle>Export</CardTitle>
          </div>
          <Card className="flex flex-col gap-3">
            <CardTitle>LaTeX paper</CardTitle>
            <CardDescription>
              Generate a .tex manuscript and matching .bib bibliography from the
              streamed draft, ready for Overleaf.
            </CardDescription>
            <div className="mt-auto flex flex-wrap gap-2 pt-2">
              <Button onClick={handleExport} disabled={exportLoading}>
                {exportLoading ? <Spinner size={16} /> : null}
                {exportLoading
                  ? "Building"
                  : exportResult
                    ? "Rebuild"
                    : "Build LaTeX"}
              </Button>
              {exportResult ? (
                <>
                  <Button
                    variant="secondary"
                    onClick={() =>
                      downloadText(
                        exportResult.tex,
                        "paper.tex",
                        "application/x-tex",
                      )
                    }
                  >
                    Download .tex
                  </Button>
                  <Button
                    variant="lime"
                    onClick={() =>
                      downloadText(
                        exportResult.bib,
                        "paper.bib",
                        "application/x-bibtex",
                      )
                    }
                  >
                    Download .bib
                  </Button>
                </>
              ) : null}
            </div>
            {exportError ? (
              <p className="text-sm text-danger">{exportError}</p>
            ) : null}
          </Card>
        </section>
      ) : null}
    </div>
  );
}
