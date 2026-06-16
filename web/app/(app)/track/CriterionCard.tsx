"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ItemForm } from "./ItemForm";
import type {
  ItemFormValues,
  LiveCriterionGroup,
  LiveEvidenceItem,
} from "./types";

interface CriterionCardProps {
  group: LiveCriterionGroup;
  onCreate: (values: ItemFormValues) => Promise<void>;
  onUpdate: (id: string, values: ItemFormValues) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onNarrative: () => Promise<string>;
}

function formatDate(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * One expandable criterion: header with satisfied state and item count,
 * the declared items list, add/edit/delete controls, and a per-criterion
 * petition-narrative drafter.
 */
export function CriterionCard({
  group,
  onCreate,
  onUpdate,
  onDelete,
  onNarrative,
}: CriterionCardProps) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [narrative, setNarrative] = useState<string | null>(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [narrativeError, setNarrativeError] = useState<string | null>(null);

  const itemCount = group.items.length;

  const handleCreate = async (values: ItemFormValues) => {
    setCreating(true);
    setError(null);
    try {
      await onCreate(values);
      setAdding(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const handleUpdate = async (id: string, values: ItemFormValues) => {
    setBusyItemId(id);
    setError(null);
    try {
      await onUpdate(id, values);
      setEditingId(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyItemId(null);
    }
  };

  const handleDelete = async (id: string) => {
    setBusyItemId(id);
    setError(null);
    try {
      await onDelete(id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyItemId(null);
    }
  };

  const handleNarrative = async () => {
    setNarrativeLoading(true);
    setNarrativeError(null);
    try {
      const text = await onNarrative();
      setNarrative(text);
    } catch (e) {
      setNarrativeError((e as Error).message);
    } finally {
      setNarrativeLoading(false);
    }
  };

  const editValues = (item: LiveEvidenceItem): Partial<ItemFormValues> => ({
    title: item.title,
    description: item.description,
    evidence_url: item.evidence_url,
    evidence_date: item.evidence_date ?? "",
  });

  return (
    <div className="overflow-hidden rounded-2xl border border-black/5 bg-surface shadow-[0_4px_24px_-8px_rgba(31,26,46,0.12)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors hover:bg-primary-50/40"
      >
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              group.satisfied ? "bg-success" : "bg-black/15"
            }`}
          />
          <span className="font-display text-base font-semibold text-ink">
            {group.label}
          </span>
          {group.satisfied ? (
            <Badge tone="success">Satisfied</Badge>
          ) : (
            <Badge tone="neutral">Building</Badge>
          )}
        </div>
        <div className="flex items-center gap-3 text-muted">
          <span className="text-sm">
            {itemCount} {itemCount === 1 ? "item" : "items"}
          </span>
          <span
            aria-hidden
            className={`text-xs transition-transform ${open ? "rotate-180" : ""}`}
          >
            v
          </span>
        </div>
      </button>

      {open ? (
        <div className="flex flex-col gap-4 border-t border-black/5 px-5 py-4">
          {error ? (
            <p className="rounded-2xl bg-danger/10 px-4 py-2.5 text-sm text-danger">
              {error}
            </p>
          ) : null}

          {itemCount === 0 && !adding ? (
            <p className="rounded-2xl border border-dashed border-black/10 px-4 py-5 text-center text-sm text-muted">
              No evidence declared for this criterion yet. Add your first item
              to start building the record.
            </p>
          ) : null}

          <ul className="flex flex-col gap-3">
            {group.items.map((item) => {
              const date = formatDate(item.evidence_date);
              const isEditing = editingId === item.id;
              const isBusy = busyItemId === item.id;
              return (
                <li
                  key={item.id}
                  className="rounded-2xl border border-black/5 bg-cream/60 p-4"
                >
                  {isEditing ? (
                    <ItemForm
                      initial={editValues(item)}
                      submitLabel="Save changes"
                      busy={isBusy}
                      onSubmit={(values) => handleUpdate(item.id, values)}
                      onCancel={() => setEditingId(null)}
                    />
                  ) : (
                    <div className="flex flex-col gap-2">
                      <div className="flex items-start justify-between gap-3">
                        <p className="font-display text-sm font-semibold text-ink">
                          {item.title}
                        </p>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setEditingId(item.id)}
                            disabled={isBusy}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(item.id)}
                            disabled={isBusy}
                            className="text-danger hover:bg-danger/10"
                          >
                            {isBusy ? <Spinner size={14} /> : "Delete"}
                          </Button>
                        </div>
                      </div>
                      {item.description ? (
                        <p className="text-sm leading-relaxed text-muted">
                          {item.description}
                        </p>
                      ) : null}
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
                        {date ? <span>{date}</span> : null}
                        {item.evidence_url ? (
                          <a
                            href={item.evidence_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary underline-offset-2 hover:underline"
                          >
                            View source
                          </a>
                        ) : null}
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          {adding ? (
            <ItemForm
              submitLabel="Add evidence"
              busy={creating}
              onSubmit={handleCreate}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setAdding(true)}
              >
                Add evidence
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNarrative}
                disabled={narrativeLoading || itemCount === 0}
              >
                {narrativeLoading ? (
                  <>
                    <Spinner size={14} /> Drafting
                  </>
                ) : (
                  "Draft narrative"
                )}
              </Button>
            </div>
          )}

          {narrativeError ? (
            <p className="rounded-2xl bg-danger/10 px-4 py-2.5 text-sm text-danger">
              {narrativeError}
            </p>
          ) : null}

          {narrative ? (
            <div className="rounded-2xl border border-primary/15 bg-primary-50/50 p-4">
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="font-display text-sm font-semibold text-primary">
                  Draft petition narrative
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setNarrative(null)}
                >
                  Dismiss
                </Button>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
                {narrative}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
