import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type BadgeTone = "sage" | "berry" | "sand" | "neutral" | "outline";

const toneClass: Record<BadgeTone, string> = {
  sage: "bg-accent-soft text-accent-foreground border-accent/40",
  berry: "bg-primary-soft text-primary border-primary/30",
  sand: "bg-secondary-soft text-foreground border-secondary/50",
  neutral: "bg-muted text-muted-foreground border-border",
  outline: "bg-transparent text-foreground border-border",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        toneClass[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  return <Badge tone="sand">{category.replace(/^\w/, (c) => c.toUpperCase())}</Badge>;
}

export function SourceBadge({ sources, className }: { sources?: string[]; className?: string }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-2 text-xs", className)}>
      <Badge tone="sage">Verified source</Badge>
      <span className="text-muted-foreground">{sources.slice(0, 2).join(", ")}</span>
    </div>
  );
}
