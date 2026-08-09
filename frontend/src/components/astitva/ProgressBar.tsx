import { cn } from "@/lib/utils";

export function ProgressBar({
  value,
  label,
  tone = "primary",
  className,
}: {
  value: number;
  label?: string;
  tone?: "primary" | "accent" | "secondary";
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const barTone =
    tone === "accent" ? "bg-accent" : tone === "secondary" ? "bg-secondary" : "bg-primary";

  return (
    <div className={className}>
      {label ? (
        <div className="mb-1.5 flex items-center justify-between text-xs text-muted-foreground">
          <span>{label}</span>
          <span className="font-semibold text-foreground">{clamped}%</span>
        </div>
      ) : null}
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? "Progress"}
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-700 ease-out", barTone)}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
