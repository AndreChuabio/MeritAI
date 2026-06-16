"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { EvidenceInput, EvidenceLedger } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { CriterionCard } from "./CriterionCard";
import type {
  ItemFormValues,
  LiveCriterionGroup,
  LiveEvidenceInput,
  LiveLedger,
} from "./types";

/**
 * Adapt the form values to the live POST/PATCH body. The shared api client
 * types its parameter as EvidenceInput (lib/types.ts) but the live API reads
 * snake_case fields (evidence_url, evidence_date). We build the real body and
 * cast only at this boundary; lib/* is never modified.
 */
function toEvidenceInput(
  criterion: string,
  values: ItemFormValues,
): EvidenceInput {
  const body: LiveEvidenceInput = {
    criterion,
    title: values.title,
    description: values.description,
    evidence_url: values.evidence_url,
    evidence_date: values.evidence_date ? values.evidence_date : null,
  };
  return body as unknown as EvidenceInput;
}

/** The live ledger is returned by api.evidence.list(); cast the cast-only JSON. */
function asLiveLedger(ledger: EvidenceLedger): LiveLedger {
  return ledger as unknown as LiveLedger;
}

export default function TrackPage() {
  const [ledger, setLedger] = useState<LiveLedger | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.evidence.list();
      setLedger(asLiveLedger(data));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const data = await api.evidence.list();
        if (active) {
          setLedger(asLiveLedger(data));
          setError(null);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const handleCreate = useCallback(
    async (criterion: string, values: ItemFormValues) => {
      await api.evidence.create(toEvidenceInput(criterion, values));
      await refresh();
    },
    [refresh],
  );

  const handleUpdate = useCallback(
    async (criterion: string, id: string, values: ItemFormValues) => {
      await api.evidence.update(
        id,
        toEvidenceInput(criterion, values) as Partial<EvidenceInput>,
      );
      await refresh();
    },
    [refresh],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      await api.evidence.remove(id);
      await refresh();
    },
    [refresh],
  );

  const handleNarrative = useCallback(async (criterion: string) => {
    const { narrative } = await api.evidence.narrative(criterion);
    return narrative;
  }, []);

  const handleDossier = useCallback(async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const blob = await api.dossier();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "o1a-evidence-dossier.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDownloadError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  }, []);

  const satisfied = ledger?.satisfied_count ?? 0;
  const total = ledger?.total ?? 8;
  const criteria: LiveCriterionGroup[] = ledger?.criteria ?? [];

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <Badge tone="primary">O-1A Evidence Ledger</Badge>
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink">
          Track your extraordinary-ability record
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-muted">
          Declare evidence against each of the eight O-1A criteria, draft
          petition-quality narratives, and export a complete dossier. Your
          records stay organized and audit-ready.
        </p>
      </header>

      {loading ? (
        <div className="flex items-center gap-3 rounded-2xl border border-black/5 bg-surface px-5 py-8 text-muted shadow-[0_4px_24px_-8px_rgba(31,26,46,0.12)]">
          <Spinner size={20} />
          <span className="text-sm">Loading your evidence ledger.</span>
        </div>
      ) : error ? (
        <div className="flex flex-col items-start gap-3 rounded-2xl border border-danger/20 bg-danger/5 px-5 py-6">
          <p className="text-sm text-danger">{error}</p>
          <Button variant="secondary" size="sm" onClick={() => refresh()}>
            Try again
          </Button>
        </div>
      ) : (
        <>
          <section className="flex flex-col gap-5 rounded-2xl border border-black/5 bg-surface p-6 shadow-[0_4px_24px_-8px_rgba(31,26,46,0.12)]">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-sm text-muted">Criteria satisfied</p>
                <p className="font-display text-2xl font-bold text-ink">
                  <span className="text-primary">{satisfied}</span> of {total}
                </p>
              </div>
              <Button
                variant="lime"
                onClick={handleDossier}
                disabled={downloading}
              >
                {downloading ? (
                  <>
                    <Spinner size={16} /> Preparing dossier
                  </>
                ) : (
                  "Download dossier (PDF)"
                )}
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              {criteria.map((group) => (
                <Badge
                  key={group.criterion}
                  tone={group.satisfied ? "success" : "neutral"}
                >
                  {group.label}
                </Badge>
              ))}
            </div>

            {downloadError ? (
              <p className="rounded-2xl bg-danger/10 px-4 py-2.5 text-sm text-danger">
                {downloadError}
              </p>
            ) : null}
          </section>

          <section className="flex flex-col gap-4">
            {criteria.map((group) => (
              <CriterionCard
                key={group.criterion}
                group={group}
                onCreate={(values) => handleCreate(group.criterion, values)}
                onUpdate={(id, values) =>
                  handleUpdate(group.criterion, id, values)
                }
                onDelete={handleDelete}
                onNarrative={() => handleNarrative(group.criterion)}
              />
            ))}
          </section>
        </>
      )}
    </div>
  );
}
