export interface SpinnerProps {
  size?: number;
  className?: string;
  label?: string;
}

export function Spinner({
  size = 20,
  className = "",
  label = "Loading",
}: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label={label}
      className={`inline-block animate-spin rounded-full border-2 border-primary/25 border-t-primary ${className}`}
      style={{ width: size, height: size }}
    />
  );
}
