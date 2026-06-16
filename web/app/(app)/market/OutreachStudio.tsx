"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardDescription,
  CardTitle,
  Spinner,
  Textarea,
} from "@/components/ui";

/**
 * Outreach purposes accepted by the backend (OutreachGenerateRequest.purpose).
 */
const PURPOSES = [
  { id: "VISA", label: "Visa", blurb: "Build an O-1A / EB-1 evidence trail." },
  { id: "CAREER", label: "Career", blurb: "Job hunts and role conversations." },
  { id: "NETWORK", label: "Network", blurb: "Warm intros and peer outreach." },
  { id: "BRAND", label: "Brand", blurb: "Grow your public presence." },
  { id: "SERVICE", label: "Service", blurb: "Pitch consulting or services." },
] as const;

type Purpose = (typeof PURPOSES)[number]["id"];

/**
 * Live DraftCardOut shape. The shared DraftCard type is looser, so we read
 * fields defensively from the unknown-ish records the api returns.
 */
interface DraftCardView {
  channel: string;
  markdown: string;
  contentTypeId: string;
  draftId: string;
  error: string | null;
}

/** Live OutreachLogRow shape. */
interface OutreachLogView {
  id: number | string;
  ts: string | null;
  purpose: string;
  channel: string;
  contentTypeId: string;
  draftId: string;
  posted: boolean;
}

function str(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function toCardView(raw: unknown): DraftCardView {
  const r = (raw ?? {}) as Record<string, unknown>;
  const errorValue = r["error"];
  return {
    channel: str(r, "channel"),
    markdown: str(r, "markdown") || str(r, "body"),
    contentTypeId: str(r, "content_type_id"),
    draftId: str(r, "draft_id"),
    error: typeof errorValue === "string" ? errorValue : null,
  };
}

function toLogView(raw: unknown): OutreachLogView {
  const r = (raw ?? {}) as Record<string, unknown>;
  const id = r["id"];
  return {
    id: typeof id === "number" || typeof id === "string" ? id : "",
    ts: str(r, "ts") || str(r, "created_at") || null,
    purpose: str(r, "purpose"),
    channel: str(r, "channel"),
    contentTypeId: str(r, "content_type_id"),
    draftId: str(r, "draft_id"),
    posted: r["posted"] === true,
  };
}

function formatTs(ts: string | null): string {
  if (!ts) return "";
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return ts;
  return parsed.toLocaleString();
}

function purposeLabel(id: string): string {
  return PURPOSES.find((p) => p.id === id)?.label ?? id;
}

export function OutreachStudio() {
  const [purpose, setPurpose] = useState<Purpose>("VISA");
  const [context, setContext] = useState("");
  const [cards, setCards] = useState<DraftCardView[]>([]);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [hasGenerated, setHasGenerated] = useState(false);

  const [log, setLog] = useState<OutreachLogView[]>([]);
  const [logLoading, setLogLoading] = useState(true);
  const [logError, setLogError] = useState<string | null>(null);

  const loadLog = useCallback(async () => {
    setLogLoading(true);
    try {
      const rows = await api.market.outreachLog();
      setLog((rows as unknown[]).map(toLogView));
      setLogError(null);
    } catch (err: unknown) {
      setLogError(
        err instanceof Error ? err.message : "Could not load outreach history.",
      );
    } finally {
      setLogLoading(false);
    }
  }, []);

  useEffect(() => {
    // Run inside a promise callback so the first setState happens off the
    // synchronous effect body (avoids cascading-render lint + behavior).
    Promise.resolve().then(loadLog);
  }, [loadLog]);

  async function handleGenerate(event: React.FormEvent) {
    event.preventDefault();
    setGenerating(true);
    setGenError(null);
    try {
      const result = await api.market.generateOutreach(purpose, context);
      setCards((result as unknown[]).map(toCardView));
      setHasGenerated(true);
      void loadLog();
    } catch (err: unknown) {
      setGenError(
        err instanceof Error
          ? err.message
          : "Outreach generation is unavailable right now.",
      );
    } finally {
      setGenerating(false);
    }
  }

  const [copiedId, setCopiedId] = useState<string | null>(null);

  async function copyCard(card: DraftCardView, key: string) {
    try {
      await navigator.clipboard.writeText(card.markdown);
      setCopiedId(key);
      window.setTimeout(() => {
        setCopiedId((current) => (current === key ? null : current));
      }, 1600);
    } catch {
      // Clipboard may be blocked; ignore silently.
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardTitle>Outreach studio</CardTitle>
        <CardDescription>
          Pick a purpose, add context, and generate channel-ready drafts in your
          voice.
        </CardDescription>

        <form onSubmit={handleGenerate} className="mt-5 flex flex-col gap-5">
          <fieldset className="flex flex-col gap-2">
            <legend className="font-display text-sm font-medium text-ink">
              Purpose
            </legend>
            <div className="flex flex-wrap gap-2.5">
              {PURPOSES.map((option) => {
                const active = option.id === purpose;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setPurpose(option.id)}
                    aria-pressed={active}
                    title={option.blurb}
                    className={`rounded-2xl border px-4 py-2 text-sm font-display font-semibold transition-transform duration-150 ease-out hover:scale-[1.03] active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-cream ${
                      active
                        ? "border-primary bg-primary text-white shadow-[0_10px_30px_-12px_rgba(109,74,255,0.5)]"
                        : "border-black/10 bg-surface text-ink hover:bg-primary-50"
                    }`}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-muted">
              {PURPOSES.find((p) => p.id === purpose)?.blurb}
            </p>
          </fieldset>

          <Textarea
            name="context"
            label="Context"
            placeholder="Who are you reaching, and what is the ask? Add specifics for sharper drafts."
            className="min-h-32"
            value={context}
            onChange={(e) => setContext(e.target.value)}
          />

          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={generating}>
              {generating ? (
                <>
                  <Spinner
                    size={16}
                    className="border-white/40 border-t-white"
                  />
                  Generating
                </>
              ) : (
                "Generate drafts"
              )}
            </Button>
          </div>
        </form>

        {genError ? (
          <div className="mt-5 rounded-2xl bg-danger/10 px-4 py-3 text-sm text-ink">
            <span className="font-medium text-danger">
              Outreach is unavailable.
            </span>{" "}
            {genError}
            <p className="mt-1 text-xs text-muted">
              The drafting service (Senso) may not be configured yet. Your
              profile still saves normally.
            </p>
          </div>
        ) : null}
      </Card>

      {cards.length > 0 ? (
        <div className="grid gap-5 lg:grid-cols-2">
          {cards.map((card, index) => {
            const key = card.draftId || `${card.channel}-${index}`;
            return (
              <Card key={key} interactive>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="primary">
                      {card.channel || "Draft"}
                    </Badge>
                    {card.contentTypeId ? (
                      <Badge tone="neutral">{card.contentTypeId}</Badge>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => copyCard(card, key)}
                    disabled={!card.markdown}
                  >
                    {copiedId === key ? "Copied" : "Copy"}
                  </Button>
                </div>
                {card.error ? (
                  <p className="text-sm text-danger">{card.error}</p>
                ) : (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
                    {card.markdown || "No content returned for this channel."}
                  </p>
                )}
              </Card>
            );
          })}
        </div>
      ) : hasGenerated && !genError ? (
        <Card>
          <p className="text-sm text-muted">
            No drafts came back for that purpose. Try adding more context.
          </p>
        </Card>
      ) : null}

      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Recent outreach</CardTitle>
            <CardDescription>Your latest generation events.</CardDescription>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void loadLog()}
            disabled={logLoading}
          >
            Refresh
          </Button>
        </div>

        {logLoading ? (
          <div className="flex items-center gap-3 text-muted">
            <Spinner size={18} />
            <span className="text-sm">Loading history</span>
          </div>
        ) : logError ? (
          <p className="text-sm text-danger">{logError}</p>
        ) : log.length === 0 ? (
          <p className="text-sm text-muted">
            No outreach yet. Generate your first batch above.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-black/5">
            {log.map((row) => (
              <li
                key={String(row.id)}
                className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="pink">{purposeLabel(row.purpose)}</Badge>
                  {row.channel ? (
                    <Badge tone="neutral">{row.channel}</Badge>
                  ) : null}
                  {row.posted ? (
                    <Badge tone="success">Posted</Badge>
                  ) : null}
                </div>
                <span className="text-xs text-muted">{formatTs(row.ts)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
