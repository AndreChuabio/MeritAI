import { Badge } from "@/components/ui/Badge";
import type { Cfp } from "@/lib/types";

export interface CfpRowProps {
  cfp: Cfp;
}

function formatDeadline(deadline: string | null): string {
  if (!deadline) return "TBD";
  const date = new Date(`${deadline}T00:00:00`);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function isPast(deadline: string | null): boolean {
  if (!deadline) return false;
  return new Date(`${deadline}T00:00:00`) < new Date(new Date().toDateString());
}

export function CfpRow({ cfp }: CfpRowProps) {
  const past = isPast(cfp.deadline);

  return (
    <div className="flex flex-col gap-3 border-b border-black/5 py-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {cfp.url ? (
            <a
              href={cfp.url}
              target="_blank"
              rel="noreferrer"
              className="font-display text-base font-semibold text-ink hover:text-primary"
            >
              {cfp.name}
            </a>
          ) : (
            <span className="font-display text-base font-semibold text-ink">
              {cfp.name}
            </span>
          )}
        </div>
        <p className="mt-1 line-clamp-2 text-sm text-muted">{cfp.scope}</p>
      </div>

      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 sm:justify-end">
        <Badge tone={past ? "neutral" : "primary"}>
          {formatDeadline(cfp.deadline)}
        </Badge>
        {cfp.format ? <Badge tone="neutral">{cfp.format}</Badge> : null}
        {past ? <Badge tone="neutral">Past</Badge> : <Badge tone="success">Open</Badge>}
      </div>
    </div>
  );
}
