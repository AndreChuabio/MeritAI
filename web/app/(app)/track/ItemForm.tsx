"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import type { CriterionGuide, ItemFormValues } from "./types";

interface ItemFormProps {
  initial?: Partial<ItemFormValues>;
  submitLabel: string;
  busy?: boolean;
  guide?: CriterionGuide;
  onSubmit: (values: ItemFormValues) => void;
  onCancel: () => void;
}

const EMPTY: ItemFormValues = {
  title: "",
  description: "",
  evidence_url: "",
  evidence_date: "",
};

/**
 * Shared add/edit form for a single evidence item. Title is required;
 * everything else is optional. Calm, single-column layout to suit the
 * sensitive nature of immigration evidence.
 */
export function ItemForm({
  initial,
  submitLabel,
  busy = false,
  guide,
  onSubmit,
  onCancel,
}: ItemFormProps) {
  const [values, setValues] = useState<ItemFormValues>({
    ...EMPTY,
    ...initial,
  });
  const [touched, setTouched] = useState(false);

  const titleError =
    touched && values.title.trim().length === 0
      ? "A title is required."
      : undefined;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (values.title.trim().length === 0) return;
    onSubmit({
      title: values.title.trim(),
      description: values.description.trim(),
      evidence_url: values.evidence_url.trim(),
      evidence_date: values.evidence_date.trim(),
    });
  };

  const set = (key: keyof ItemFormValues) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => setValues((prev) => ({ ...prev, [key]: e.target.value }));

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 rounded-2xl border border-primary/15 bg-primary-50/40 p-4"
    >
      <Input
        name="title"
        label="Title"
        placeholder="e.g. Best Paper Award, NeurIPS 2025"
        value={values.title}
        onChange={set("title")}
        error={titleError}
        autoFocus
      />
      <div className="flex flex-col gap-1.5">
        <Textarea
          name="description"
          label="Description (optional)"
          placeholder="What this evidence shows and why it matters."
          value={values.description}
          onChange={set("description")}
        />
        {guide ? (
          <p className="text-xs leading-relaxed text-muted">
            For example: {guide.examples.join("; ")}.
          </p>
        ) : null}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          name="evidence_url"
          label="Evidence URL (optional)"
          placeholder="https://"
          type="url"
          value={values.evidence_url}
          onChange={set("evidence_url")}
        />
        <Input
          name="evidence_date"
          label="Date (optional)"
          type="date"
          value={values.evidence_date}
          onChange={set("evidence_date")}
        />
      </div>
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={busy}>
          {submitLabel}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
