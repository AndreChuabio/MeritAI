"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";

interface DraftStreamProps {
  order: string[];
  sections: Record<string, string>;
  activeSection: string | null;
  streaming: boolean;
}

function prettyName(name: string): string {
  return name
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

/**
 * Live view of the streamed draft. Sections appear in arrival order and fill in
 * token-by-token; the section currently receiving deltas gets a caret + spinner.
 */
export function DraftStream({
  order,
  sections,
  activeSection,
  streaming,
}: DraftStreamProps) {
  if (order.length === 0) {
    return (
      <Card className="flex items-center gap-3">
        <Spinner size={18} />
        <span className="text-sm text-muted">
          Warming up the writer, sections will appear here as they stream in.
        </span>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {order.map((name) => {
        const isActive = streaming && name === activeSection;
        return (
          <Card key={name} className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <h4 className="font-display text-base font-semibold text-ink">
                {prettyName(name)}
              </h4>
              {isActive ? (
                <span className="flex items-center gap-2">
                  <Spinner size={14} />
                  <Badge tone="pink">writing</Badge>
                </span>
              ) : (
                <Badge tone="success">ready</Badge>
              )}
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink/90">
              {sections[name] ?? ""}
              {isActive ? (
                <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-primary align-middle" />
              ) : null}
            </p>
          </Card>
        );
      })}
    </div>
  );
}
