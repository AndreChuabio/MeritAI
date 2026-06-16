"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Textarea } from "@/components/ui/Textarea";
import { Input } from "@/components/ui/Input";
import type { ResearchSummary } from "@/lib/types";

interface SummaryEditorProps {
  summary: ResearchSummary;
  onChange: (next: ResearchSummary) => void;
  disabled?: boolean;
}

interface Field {
  key: keyof Pick<
    ResearchSummary,
    "problem" | "contribution" | "method" | "results" | "limitations"
  >;
  label: string;
  placeholder: string;
}

const FIELDS: Field[] = [
  {
    key: "problem",
    label: "Problem",
    placeholder: "What gap or pain does this work address?",
  },
  {
    key: "contribution",
    label: "Contribution",
    placeholder: "What is new here?",
  },
  {
    key: "method",
    label: "Method",
    placeholder: "How does it work?",
  },
  {
    key: "results",
    label: "Results",
    placeholder: "What did you measure or observe?",
  },
  {
    key: "limitations",
    label: "Limitations",
    placeholder: "What are the open questions or caveats?",
  },
];

/**
 * Editable research-summary cards. Every field stays editable so the user can
 * refine an ingested summary or write one by hand when ingest is unavailable.
 */
export function SummaryEditor({
  summary,
  onChange,
  disabled = false,
}: SummaryEditorProps) {
  const setField = (key: Field["key"], value: string) => {
    onChange({ ...summary, [key]: value });
  };

  const setKeywords = (value: string) => {
    const keywords = value
      .split(",")
      .map((k) => k.trim())
      .filter((k) => k.length > 0);
    onChange({ ...summary, keywords });
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {FIELDS.map((field) => (
        <Card key={field.key} className="flex flex-col gap-2">
          <Badge tone="primary">{field.label}</Badge>
          <Textarea
            value={summary[field.key] ?? ""}
            placeholder={field.placeholder}
            disabled={disabled}
            onChange={(e) => setField(field.key, e.target.value)}
            className="min-h-24"
          />
        </Card>
      ))}

      <Card className="flex flex-col gap-2 md:col-span-2">
        <Badge tone="lime">Keywords</Badge>
        <Input
          value={(summary.keywords ?? []).join(", ")}
          placeholder="comma, separated, keywords"
          disabled={disabled}
          onChange={(e) => setKeywords(e.target.value)}
        />
        {summary.keywords && summary.keywords.length > 0 ? (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {summary.keywords.map((kw) => (
              <Badge key={kw} tone="neutral">
                {kw}
              </Badge>
            ))}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
