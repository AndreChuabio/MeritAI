"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PersonLead } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  CardDescription,
  CardTitle,
  Input,
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

interface DraftCardView {
  channel: string;
  markdown: string;
  contentTypeId: string;
  draftId: string;
  error: string | null;
}

interface OutreachLogView {
  id: number | string;
  ts: string | null;
  purpose: string;
  channel: string;
  recipientName: string;
  recipientContact: string;
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
    recipientName: str(r, "recipient_name"),
    recipientContact: str(r, "recipient_contact"),
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

/** Pull a subject line out of a draft body, or fall back to a sensible default. */
function deriveSubject(body: string, purpose: string): string {
  for (const line of body.split("\n").slice(0, 6)) {
    const match = line.match(/subject[:\-]\s*(.+)/i);
    if (match) {
      return match[1].replace(/[*#]/g, "").trim();
    }
  }
  return `${purposeLabel(purpose)} outreach`;
}

export function OutreachStudio() {
  const [purpose, setPurpose] = useState<Purpose>("VISA");
  const [context, setContext] = useState("");
  const [cards, setCards] = useState<DraftCardView[]>([]);
  const [edited, setEdited] = useState<Record<string, string>>({});
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [hasGenerated, setHasGenerated] = useState(false);

  // Shared recipient for the generated drafts.
  const [toName, setToName] = useState("");
  const [toEmail, setToEmail] = useState("");

  // People discovery.
  const [people, setPeople] = useState<PersonLead[]>([]);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [peopleError, setPeopleError] = useState<string | null>(null);
  const [peopleConfigured, setPeopleConfigured] = useState(true);
  const [searchedPeople, setSearchedPeople] = useState(false);

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
    Promise.resolve().then(loadLog);
  }, [loadLog]);

  async function handleGenerate(event: React.FormEvent) {
    event.preventDefault();
    setGenerating(true);
    setGenError(null);
    try {
      const result = await api.market.generateOutreach(purpose, context);
      const views = (result as unknown[]).map(toCardView);
      setCards(views);
      setEdited({});
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

  async function handleFindPeople() {
    setPeopleLoading(true);
    setPeopleError(null);
    setSearchedPeople(true);
    try {
      const res = await api.market.suggestPeople(purpose, context);
      setPeopleConfigured(res.configured);
      setPeople(res.people ?? []);
    } catch (err: unknown) {
      setPeopleError(
        err instanceof Error ? err.message : "Could not find people right now.",
      );
    } finally {
      setPeopleLoading(false);
    }
  }

  function selectLead(lead: PersonLead) {
    setToName(lead.name);
    if (lead.email) setToEmail(lead.email);
  }

  function bodyFor(card: DraftCardView, key: string): string {
    return edited[key] ?? card.markdown;
  }

  async function handleSend(card: DraftCardView, key: string) {
    const body = bodyFor(card, key);
    const subject = deriveSubject(body, purpose);
    const mailto = `mailto:${toEmail}?subject=${encodeURIComponent(
      subject,
    )}&body=${encodeURIComponent(body)}`;
    // Open the user's mail client with the draft pre-filled.
    window.location.href = mailto;
    try {
      await api.market.logSent({
        purpose,
        channel: card.channel,
        recipient_name: toName,
        recipient_contact: toEmail,
        draft_id: card.draftId,
      });
      void loadLog();
    } catch {
      // Logging is best-effort; the email still opened.
    }
  }

  const [copiedId, setCopiedId] = useState<string | null>(null);

  async function copyCard(key: string, body: string) {
    try {
      await navigator.clipboard.writeText(body);
      setCopiedId(key);
      window.setTimeout(() => {
        setCopiedId((current) => (current === key ? null : current));
      }, 1600);
    } catch {
      // Clipboard may be blocked; ignore silently.
    }
  }

  const hasDrafts = cards.some((c) => !c.error && c.markdown);

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

      {hasDrafts ? (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>Who are you reaching?</CardTitle>
              <CardDescription>
                Find people from the web, or enter a recipient. Each draft sends
                from your own email so you can review before it goes.
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => void handleFindPeople()}
              disabled={peopleLoading}
            >
              {peopleLoading ? (
                <>
                  <Spinner size={16} />
                  Searching
                </>
              ) : (
                "Find people to reach"
              )}
            </Button>
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Input
              name="to_name"
              label="Recipient name"
              placeholder="Dr. Ada Lovelace"
              value={toName}
              onChange={(e) => setToName(e.target.value)}
            />
            <Input
              name="to_email"
              label="Recipient email"
              type="text"
              inputMode="email"
              placeholder="ada@example.com"
              value={toEmail}
              onChange={(e) => setToEmail(e.target.value)}
            />
          </div>

          {searchedPeople ? (
            <div className="mt-4">
              {peopleError ? (
                <p className="text-sm text-danger">{peopleError}</p>
              ) : !peopleConfigured ? (
                <p className="text-sm text-muted">
                  People search is not configured (Nimble). Enter a recipient
                  manually above.
                </p>
              ) : peopleLoading ? null : people.length === 0 ? (
                <p className="text-sm text-muted">
                  No leads found. Try broader context, or enter a recipient
                  manually.
                </p>
              ) : (
                <>
                  <p className="mb-2 text-xs text-muted">
                    Leads from the web. Open one to find a contact, then select
                    it as the recipient. Vet before reaching out.
                  </p>
                  <ul className="flex flex-col divide-y divide-black/5">
                    {people.map((lead, i) => (
                      <li
                        key={`${lead.url}-${i}`}
                        className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-ink">
                            {lead.name}
                          </p>
                          {lead.detail ? (
                            <p className="line-clamp-2 text-xs text-muted">
                              {lead.detail}
                            </p>
                          ) : null}
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            {lead.email ? (
                              <Badge tone="success">{lead.email}</Badge>
                            ) : (
                              <Badge tone="neutral">no email found</Badge>
                            )}
                            {lead.url ? (
                              <a
                                href={lead.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs font-medium text-primary underline-offset-2 hover:underline"
                              >
                                Open
                              </a>
                            ) : null}
                          </div>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => selectLead(lead)}
                        >
                          Select
                        </Button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          ) : null}
        </Card>
      ) : null}

      {cards.length > 0 ? (
        <div className="grid gap-5 lg:grid-cols-2">
          {cards.map((card, index) => {
            const key = card.draftId || `${card.channel}-${index}`;
            const body = bodyFor(card, key);
            return (
              <Card key={key} interactive>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="primary">{card.channel || "Draft"}</Badge>
                    {card.contentTypeId ? (
                      <Badge tone="neutral">{card.contentTypeId}</Badge>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => void copyCard(key, body)}
                    disabled={!body}
                  >
                    {copiedId === key ? "Copied" : "Copy"}
                  </Button>
                </div>
                {card.error ? (
                  <p className="text-sm text-danger">{card.error}</p>
                ) : (
                  <>
                    <Textarea
                      name={`draft-${key}`}
                      label="Edit before sending"
                      className="min-h-56 font-sans text-sm leading-relaxed"
                      value={body}
                      onChange={(e) =>
                        setEdited((prev) => ({ ...prev, [key]: e.target.value }))
                      }
                    />
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => void handleSend(card, key)}
                        disabled={!toEmail.trim() || !body.trim()}
                      >
                        Open in email
                      </Button>
                      {!toEmail.trim() ? (
                        <span className="text-xs text-muted">
                          Add a recipient email above to send.
                        </span>
                      ) : (
                        <span className="text-xs text-muted">
                          Opens your mail app to {toEmail}. You review and send.
                        </span>
                      )}
                    </div>
                  </>
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
            <CardDescription>
              Who you reached and when. Sent drafts show the recipient.
            </CardDescription>
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
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <Badge tone="pink">{purposeLabel(row.purpose)}</Badge>
                  {row.channel ? (
                    <Badge tone="neutral">{row.channel}</Badge>
                  ) : null}
                  {row.posted ? (
                    <Badge tone="success">Sent</Badge>
                  ) : (
                    <Badge tone="neutral">Drafted</Badge>
                  )}
                  {row.recipientName || row.recipientContact ? (
                    <span className="truncate text-sm text-ink">
                      to{" "}
                      <span className="font-medium">
                        {row.recipientName || row.recipientContact}
                      </span>
                      {row.recipientName && row.recipientContact ? (
                        <span className="text-muted">
                          {" "}
                          ({row.recipientContact})
                        </span>
                      ) : null}
                    </span>
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
