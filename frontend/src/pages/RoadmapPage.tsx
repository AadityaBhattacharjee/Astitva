import { useEffect, useState } from "react";
import { agentApi } from "@/api/client";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/astitva/Card";
import { Badge } from "@/components/astitva/Badge";
import { LoadingState, ErrorState } from "@/components/astitva/States";

interface RoadmapTask {
  id: number;
  title: string;
  status: string;
  priority: string;
}

interface PlanningData {
  answer: string;
  existing_plan_summary: {
    total_roadmaps?: number;
    total_tasks?: number;
    completed_tasks?: number;
    pending_tasks?: number;
  };
  recommended_next_actions: Array<{
    title?: string;
    action?: string;
    reason?: string;
    priority?: string;
  }>;
  gaps_identified: string[];
  disclaimer: string;
}

export default function RoadmapPage() {
  const [data, setData] = useState<PlanningData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    agentApi
      .planning("Show me my current roadmap, all tasks, and recommend what I should work on next.")
      .then((resp) => { if (alive) setData(resp as unknown as PlanningData); })
      .catch((err: unknown) => { if (alive) setError(err instanceof Error ? err.message : "Could not load roadmap."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  if (loading) {
    return (
      <AppLayout title="Your Life Roadmap">
        <LoadingState message="Loading your roadmap from the database…" />
      </AppLayout>
    );
  }

  if (error || !data) {
    return (
      <AppLayout title="Your Life Roadmap">
        <ErrorState title="Could not load roadmap" message={error} onRetry={() => window.location.reload()} />
      </AppLayout>
    );
  }

  const priorityColor = (p: string) => {
    if (p === "HIGH" || p === "CRITICAL") return "berry";
    if (p === "MEDIUM") return "sand";
    return "neutral";
  };

  return (
    <AppLayout
      title="Your Life Roadmap"
      subtitle="Your roadmap adapts as your situation changes."
    >
      <div className="space-y-8">
        {/* Plan summary */}
        <section className="grid gap-4 sm:grid-cols-4">
          {[
            { label: "Roadmaps", value: data.existing_plan_summary.total_roadmaps ?? 0 },
            { label: "Total tasks", value: data.existing_plan_summary.total_tasks ?? 0 },
            { label: "Completed", value: data.existing_plan_summary.completed_tasks ?? 0 },
            { label: "Pending", value: data.existing_plan_summary.pending_tasks ?? 0 },
          ].map((item) => (
            <Card key={item.label} className="p-4 text-center">
              <p className="text-2xl font-bold text-foreground">{item.value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{item.label}</p>
            </Card>
          ))}
        </section>

        {/* AI planning narrative */}
        {data.answer && data.answer !== "LLM provider placeholder response." ? (
          <Card>
            <h2 className="text-base font-semibold text-foreground">AI Planning Analysis</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
              {data.answer}
            </p>
          </Card>
        ) : null}

        {/* Recommended next actions */}
        {data.recommended_next_actions.length > 0 ? (
          <section>
            <h2 className="text-lg font-semibold text-foreground">Recommended next actions</h2>
            <div className="mt-4 space-y-3">
              {data.recommended_next_actions.map((action, i) => (
                <article
                  key={i}
                  className="rounded-2xl border border-border bg-surface p-5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="text-base font-semibold text-foreground">
                      {action.title ?? action.action ?? `Action ${i + 1}`}
                    </h3>
                    {action.priority ? (
                      <Badge tone={priorityColor(action.priority)}>{action.priority}</Badge>
                    ) : null}
                  </div>
                  {action.reason ? (
                    <p className="mt-2 text-sm text-muted-foreground">{action.reason}</p>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {/* Gaps identified */}
        {data.gaps_identified.length > 0 ? (
          <section>
            <h2 className="text-lg font-semibold text-foreground">Gaps identified</h2>
            <ul className="mt-4 space-y-2">
              {data.gaps_identified.map((gap, i) => (
                <li key={i} className="rounded-xl border border-secondary/40 bg-secondary-soft px-4 py-3 text-sm text-foreground">
                  {gap}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* Disclaimer */}
        {data.disclaimer ? (
          <p className="rounded-2xl border border-border bg-surface px-4 py-3 text-xs text-muted-foreground">
            {data.disclaimer}
          </p>
        ) : null}
      </div>
    </AppLayout>
  );
}
