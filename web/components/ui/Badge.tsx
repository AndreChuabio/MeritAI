import type { ReactNode } from "react";

type BadgeTone =
  | "primary"
  | "pink"
  | "lime"
  | "neutral"
  | "success"
  | "warning"
  | "danger";

export interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}

const tones: Record<BadgeTone, string> = {
  primary: "bg-primary-50 text-primary",
  pink: "bg-accent-pink-50 text-accent-pink",
  lime: "bg-accent-lime-50 text-ink",
  neutral: "bg-black/5 text-muted",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-danger/15 text-danger",
};

export function Badge({
  children,
  tone = "primary",
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-display font-medium ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
