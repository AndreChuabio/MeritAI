"use client";

import type { ReactNode } from "react";

export type StepState = "done" | "active" | "todo";

interface Step {
  id: number;
  label: string;
}

const STEPS: Step[] = [
  { id: 1, label: "Ingest" },
  { id: 2, label: "Match" },
  { id: 3, label: "Draft" },
  { id: 4, label: "Export" },
];

interface StepHeaderProps {
  current: number;
}

/**
 * Horizontal step indicator for the repo -> paper flow.
 * `current` is the 1-based index of the active step.
 */
export function StepHeader({ current }: StepHeaderProps): ReactNode {
  return (
    <ol className="flex flex-wrap items-center gap-2 sm:gap-3">
      {STEPS.map((step, index) => {
        const state: StepState =
          step.id < current ? "done" : step.id === current ? "active" : "todo";
        return (
          <li key={step.id} className="flex items-center gap-2 sm:gap-3">
            <div className="flex items-center gap-2">
              <span
                className={[
                  "flex h-8 w-8 items-center justify-center rounded-full font-display text-sm font-semibold transition-colors",
                  state === "done"
                    ? "bg-accent-lime text-ink"
                    : state === "active"
                      ? "bg-primary text-white shadow-[0_8px_20px_-8px_rgba(109,74,255,0.7)]"
                      : "bg-black/5 text-muted",
                ].join(" ")}
              >
                {state === "done" ? (
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <path d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  step.id
                )}
              </span>
              <span
                className={[
                  "font-display text-sm font-medium",
                  state === "todo" ? "text-muted" : "text-ink",
                ].join(" ")}
              >
                {step.label}
              </span>
            </div>
            {index < STEPS.length - 1 ? (
              <span
                className={[
                  "hidden h-0.5 w-8 rounded-full sm:block",
                  step.id < current ? "bg-accent-lime" : "bg-black/10",
                ].join(" ")}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
