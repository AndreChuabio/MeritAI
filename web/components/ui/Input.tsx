import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";

export interface InputProps
  extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, className = "", id, ...props },
  ref,
) {
  const inputId = id ?? props.name;
  return (
    <div className="flex flex-col gap-1.5">
      {label ? (
        <label
          htmlFor={inputId}
          className="font-display text-sm font-medium text-ink"
        >
          {label}
        </label>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        className={`rounded-2xl border bg-surface px-4 py-2.5 text-sm text-ink placeholder:text-muted/70 shadow-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30 ${
          error ? "border-danger" : "border-black/10"
        } ${className}`}
        {...props}
      />
      {error ? <span className="text-xs text-danger">{error}</span> : null}
    </div>
  );
});
