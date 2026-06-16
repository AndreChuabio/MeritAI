import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "lime";
type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-2xl font-display font-semibold " +
  "transition-transform duration-150 ease-out hover:scale-[1.03] active:scale-[0.98] " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 " +
  "focus-visible:ring-offset-cream disabled:opacity-50 disabled:pointer-events-none";

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-white shadow-[0_10px_30px_-12px_rgba(109,74,255,0.5)] hover:bg-primary-600",
  secondary:
    "bg-primary-50 text-primary hover:bg-accent-pink-50 hover:text-accent-pink",
  ghost: "bg-transparent text-ink hover:bg-primary-50",
  danger: "bg-danger text-white hover:opacity-90",
  lime: "bg-accent-lime text-ink hover:brightness-105",
};

const sizes: Record<ButtonSize, string> = {
  sm: "text-sm px-3.5 py-2",
  md: "text-sm px-5 py-2.5",
  lg: "text-base px-6 py-3",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { variant = "primary", size = "md", className = "", children, ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
        {...props}
      >
        {children}
      </button>
    );
  },
);
