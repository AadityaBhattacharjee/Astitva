import type { ReactNode } from "react";
import { AlertCircle, Loader2, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";

export function LoadingState({ message = "Loading your information…" }: { message?: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-surface px-6 py-14 text-center"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-6 w-6 animate-spin text-primary" aria-hidden="true" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

export function ErrorState({
  title = "Something didn't load",
  message = "Unable to load content.",
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-surface px-6 py-14 text-center"
      role="alert"
    >
      <AlertCircle className="h-6 w-6 text-primary" aria-hidden="true" />
      <div>
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{message}</p>
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border bg-surface px-6 py-14 text-center">
      <Inbox className="h-6 w-6 text-secondary" aria-hidden="true" />
      <div>
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{message}</p>
      </div>
      {action}
    </div>
  );
}
