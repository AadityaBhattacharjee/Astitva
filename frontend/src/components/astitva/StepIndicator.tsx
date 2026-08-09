import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export function StepIndicator({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div>
      <p className="text-sm font-medium text-muted-foreground">
        Step {current + 1} of {steps.length}
        <span className="mx-2 text-border">|</span>
        <span className="text-foreground">{steps[current]}</span>
      </p>
      <ol className="mt-3 flex items-center gap-2" aria-label="Onboarding progress">
        {steps.map((step, index) => {
          const isComplete = index < current;
          const isCurrent = index === current;
          return (
            <li key={step} className="flex flex-1 items-center gap-2">
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                  isComplete && "border-accent bg-accent text-accent-foreground",
                  isCurrent && "border-primary bg-primary text-primary-foreground",
                  !isComplete && !isCurrent && "border-border bg-surface text-muted-foreground",
                )}
                aria-current={isCurrent ? "step" : undefined}
              >
                {isComplete ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : index + 1}
                <span className="sr-only">{step}</span>
              </span>
              {index < steps.length - 1 ? (
                <span
                  className={cn(
                    "h-0.5 flex-1 rounded-full transition-colors",
                    isComplete ? "bg-accent" : "bg-border",
                  )}
                />
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
