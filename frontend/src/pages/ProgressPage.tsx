import { useEffect, useState } from "react";
import { agentApi } from "@/api/client";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/astitva/Card";
import { ProgressBar } from "@/components/astitva/ProgressBar";
import { LoadingState, ErrorState } from "@/components/astitva/States";

interface ProgressSummary {
  overall_completion_pct?: number;
  completed_tasks?: number;
  total_tasks?: number;
  pending_tasks?: number;
  overdue_tasks?: number;
}

interface ProgressData {
  answer: string;
  progress_summary: ProgressSummary;
  achievements: string[];
  pending_actions: string[];
  next_recommended_step: string;
}

export default function ProgressPage() {
  const [data, setData] = useState<ProgressData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    agentApi
      .progress("Give me a comprehensive summary of my progress across all stages.")
      .then((resp) => {
        if (alive) setData(resp as unknown as ProgressData);
      })
      .catch((err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : "Could not load progress.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => { alive = false; };
  }, []);

  if (loading) {
    return (
      <AppLayout title="Your Progress">
        <LoadingState message="Computing your progress from roadmap data…" />
      </AppLayout>
    );
  }

  if (error || !data) {
    return (
      <AppLayout title="Your Progress">
        <ErrorState title="Could not load progress" message={error} onRetry={() => window.location.reload()} />
      </AppLayout>
    );
  }

  const pct = (data.progress_summary.overall_completion_pct ?? 0) * 100;

  return (
    <AppLayout
      title="Your Progress"
      subtitle="Progress measured in meaningful steps toward independence."
    >
      <div className="space-y-8">
        {/* Overall */}
        <Card tone="sage">
          <ProgressBar label="Overall" value={pct} tone="accent" />
          <div className="mt-4 grid grid-cols-3 gap-3 text-center text-sm">
            <div>
              <p className="text-2xl font-bold text-foreground">
                {data.progress_summary.completed_tasks ?? 0}
              </p>
              <p className="text-xs text-muted-foreground">Completed</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">
                {data.progress_summary.pending_tasks ?? 0}
              </p>
              <p className="text-xs text-muted-foreground">Pending</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">
                {data.progress_summary.overdue_tasks ?? 0}
              </p>
              <p className="text-xs text-muted-foreground">Overdue</p>
            </div>
          </div>
        </Card>

        {/* AI interpretation */}
        {data.answer && data.answer !== "LLM provider placeholder response." ? (
          <Card>
            <h2 className="text-base font-semibold text-foreground">AI Progress Analysis</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
              {data.answer}
            </p>
          </Card>
        ) : null}

        {/* Next step */}
        {data.next_recommended_step ? (
          <Card tone="berry">
            <h2 className="text-base font-semibold text-foreground">Next recommended step</h2>
            <p className="mt-2 text-sm text-muted-foreground">{data.next_recommended_step}</p>
          </Card>
        ) : null}

        {/* Achievements */}
        {data.achievements.length > 0 ? (
          <section>
            <h2 className="text-lg font-semibold text-foreground">Achievements</h2>
            <ul className="mt-4 space-y-2">
              {data.achievements.map((a, i) => (
                <li
                  key={i}
                  className="rounded-xl border border-accent/40 bg-accent-soft px-4 py-3 text-sm text-foreground"
                >
                  ✓ {a}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* Pending actions */}
        {data.pending_actions.length > 0 ? (
          <section>
            <h2 className="text-lg font-semibold text-foreground">Pending actions</h2>
            <ul className="mt-4 space-y-2">
              {data.pending_actions.map((a, i) => (
                <li
                  key={i}
                  className="rounded-xl border border-border bg-surface px-4 py-3 text-sm text-foreground"
                >
                  ○ {a}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </AppLayout>
  );
}
