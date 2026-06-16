import type { HTMLAttributes, ReactNode } from "react";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  interactive?: boolean;
}

export function Card({
  children,
  interactive = false,
  className = "",
  ...props
}: CardProps) {
  const hover = interactive
    ? "transition-transform duration-200 ease-out hover:scale-[1.01] hover:shadow-[0_18px_40px_-16px_rgba(31,26,46,0.22)]"
    : "";
  return (
    <div
      className={`rounded-2xl border border-black/5 bg-surface p-6 shadow-[0_4px_24px_-8px_rgba(31,26,46,0.12)] ${hover} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h3 className={`font-display text-lg font-semibold text-ink ${className}`}>
      {children}
    </h3>
  );
}

export function CardDescription({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p className={`mt-1 text-sm text-muted ${className}`}>{children}</p>
  );
}
