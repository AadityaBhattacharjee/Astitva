import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { agentApi, roadmapApi } from "@/api/client";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/astitva/Card";
import { Badge } from "@/components/astitva/Badge";
import { Button } from "@/components/ui/button";
import { LoadingState, ErrorState } from "@/components/astitva/States";

interface RoadmapTask {
  id: number;
  roadmap_id: number;
  title: string;
  description: string | null;
  sequence: number;
  status: string;
  priority: string;
}

interface RoadmapData {
  roadmap: {
    id: number;
    user_id: number;
    title: string;
    summary: string | null;
    status: string;
    tasks: RoadmapTask[];
  };
  progress: {
    completed_milestones: number;
    overdue_tasks: number;
  };
}

interface PlanningData {
  answer: string;
  existing_plan_summary: {
    roadmaps_count?: number;
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
  const navigate = useNavigate();
  const [roadmapData, setRoadmapData] = useState<RoadmapData | null>(null);
  const [planningData, setPlanningData] = useState<PlanningData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatingTaskId, setUpdatingTaskId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [roadmapResp, planningResp] = await Promise.all([
        roadmapApi.getMine(),
        agentApi.planning("Show me my current roadmap, all tasks, and recommend what I should work on next."),
      ]);
      setRoadmapData(roadmapResp as RoadmapData);
      setPlanningData(planningResp as unknown as PlanningData);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load roadmap.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const updateTaskStatus = async (taskId: number, status: string) => {
    setUpdatingTaskId(taskId);
    try {
      const updated = await roadmapApi.updateTask(taskId, status);
      setRoadmapData(updated as RoadmapData);
      const planningResp = await agentApi.planning("Show me my current roadmap, all tasks, and recommend what I should work on next.");
      setPlanningData(planningResp as unknown as PlanningData);
      toast.success("Roadmap updated.");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Could not update task.";
      toast.error(message);
    } finally {
      setUpdatingTaskId(null);
    }
  };

  const startTask = async (taskId: number, currentStatus: string) => {
    try {
      if (currentStatus === "PENDING") {
        const updated = await roadmapApi.updateTask(taskId, "IN_PROGRESS");
        setRoadmapData(updated as RoadmapData);
      }
      await navigate(`/chat?task_id=${taskId}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Could not open the guide.";
      toast.error(message);
    }
  };

  if (loading) {
    return (
      <AppLayout title="Your Life Roadmap">
        <LoadingState message="Loading your roadmap from the database…" />
      </AppLayout>
    );
  }

  if (error || !roadmapData) {
    return (
      <AppLayout title="Your Life Roadmap">
        <ErrorState title="Could not load roadmap" message={error} onRetry={() => void load()} />
      </AppLayout>
    );
  }

  const summary = planningData?.existing_plan_summary ?? {};

  const priorityColor = (priority: string) => {
    if (priority === "HIGH" || priority === "CRITICAL") return "berry";
    if (priority === "MEDIUM") return "sand";
    return "neutral";
  };

  return (
    <AppLayout
      title={roadmapData.roadmap.title}
      subtitle={roadmapData.roadmap.summary ?? "Your roadmap adapts as your situation changes."}
    >
      <div className="space-y-8">
        <section className="grid gap-4 sm:grid-cols-4">
          {[
            { label: "Roadmaps", value: summary.roadmaps_count ?? 1 },
            { label: "Total tasks", value: summary.total_tasks ?? roadmapData.roadmap.tasks.length },
            { label: "Completed", value: summary.completed_tasks ?? roadmapData.progress.completed_milestones ?? 0 },
            { label: "Pending", value: summary.pending_tasks ?? Math.max(roadmapData.roadmap.tasks.length - (roadmapData.progress.completed_milestones ?? 0), 0) },
          ].map((item) => (
            <Card key={item.label} className="p-4 text-center">
              <p className="text-2xl font-bold text-foreground">{item.value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{item.label}</p>
            </Card>
          ))}
        </section>

        <section>
          <h2 className="text-lg font-semibold text-foreground">Your tasks</h2>
          <div className="mt-4 space-y-3">
            {roadmapData.roadmap.tasks
              .slice()
              .sort((a, b) => a.sequence - b.sequence)
              .map((task) => (
                <article
                  key={task.id}
                  className="rounded-2xl border border-border bg-surface p-5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">
                        Step {task.sequence}
                      </p>
                      <h3 className="mt-1 text-base font-semibold text-foreground">{task.title}</h3>
                    </div>
                    <div className="flex gap-2">
                      <Badge tone={priorityColor(task.priority)}>{task.priority}</Badge>
                      <Badge tone={task.status === "COMPLETED" ? "sage" : "neutral"}>{task.status}</Badge>
                    </div>
                  </div>
                  {task.description ? (
                    <p className="mt-2 text-sm text-muted-foreground">{task.description}</p>
                  ) : null}
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={updatingTaskId === task.id}
                      onClick={() => void startTask(task.id, task.status)}
                    >
                      Start
                    </Button>
                    <Button
                      size="sm"
                      disabled={updatingTaskId === task.id || task.status === "COMPLETED"}
                      onClick={() => void updateTaskStatus(task.id, "COMPLETED")}
                    >
                      Mark complete
                    </Button>
                  </div>
                </article>
              ))}
          </div>
        </section>

        {planningData?.answer && planningData.answer !== "LLM provider placeholder response." ? (
          <Card>
            <h2 className="text-base font-semibold text-foreground">AI Planning Analysis</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
              {planningData.answer}
            </p>
          </Card>
        ) : null}

        {planningData?.recommended_next_actions?.length ? (
          <section>
            <h2 className="text-lg font-semibold text-foreground">Recommended next actions</h2>
            <div className="mt-4 space-y-3">
              {planningData.recommended_next_actions.map((action, index) => (
                <article
                  key={index}
                  className="rounded-2xl border border-border bg-surface p-5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="text-base font-semibold text-foreground">
                      {action.title ?? action.action ?? `Action ${index + 1}`}
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

        {planningData?.gaps_identified?.length ? (
          <section>
            <h2 className="text-lg font-semibold text-foreground">Gaps identified</h2>
            <ul className="mt-4 space-y-2">
              {planningData.gaps_identified.map((gap, index) => (
                <li
                  key={index}
                  className="rounded-xl border border-secondary/40 bg-secondary-soft px-4 py-3 text-sm text-foreground"
                >
                  {gap}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {planningData?.disclaimer ? (
          <p className="rounded-2xl border border-border bg-surface px-4 py-3 text-xs text-muted-foreground">
            {planningData.disclaimer}
          </p>
        ) : null}
      </div>
    </AppLayout>
  );
}
