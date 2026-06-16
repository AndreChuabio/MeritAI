import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ label, error, className = "", id, ...props }, ref) {
    const textareaId = id ?? props.name;
    return (
      <div className="flex flex-col gap-1.5">
        {label ? (
          <label
            htmlFor={textareaId}
            className="font-display text-sm font-medium text-ink"
          >
            {label}
          </label>
        ) : null}
        <textarea
          ref={ref}
          id={textareaId}
          className={`min-h-28 rounded-2xl border bg-surface px-4 py-3 text-sm leading-relaxed text-ink placeholder:text-muted/70 shadow-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30 ${
            error ? "border-danger" : "border-black/10"
          } ${className}`}
          {...props}
        />
        {error ? <span className="text-xs text-danger">{error}</span> : null}
      </div>
    );
  },
);
