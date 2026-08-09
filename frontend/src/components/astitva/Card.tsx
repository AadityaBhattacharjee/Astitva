import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone = "surface" | "sand" | "sage" | "berry" | "plain";

const toneClass: Record<Tone, string> = {
  surface: "bg-surface border-border",
  sand: "bg-secondary-soft border-secondary/40",
  sage: "bg-accent-soft border-accent/40",
  berry: "bg-primary-soft border-primary/25",
  plain: "bg-transparent border-border",
};

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  tone?: Tone;
  interactive?: boolean;
}

export function Card({ tone = "surface", interactive, className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border p-5 transition-shadow",
        toneClass[tone],
        interactive && "hover:shadow-[0_10px_30px_-18px_rgba(43,23,36,0.45)]",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
      <div className="flex min-w-0 items-start gap-3">
        {icon ? <div className="mt-0.5 shrink-0 text-primary">{icon}</div> : null}
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          {description ? (
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
          ) : null}
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
