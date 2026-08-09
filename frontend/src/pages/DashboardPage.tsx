import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, HeartPulse, Shield, Sprout, AlertCircle } from "lucide-react";

import { AppLayout } from "@/layouts/AppLayout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/astitva/Card";
import { Badge } from "@/components/astitva/Badge";
import { ProgressBar } from "@/components/astitva/ProgressBar";
import { LoadingState } from "@/components/astitva/States";
import { agentApi, roadmapApi } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";

const greeting = () => {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
};

interface ProgressData {
  answer: string;
  progress_summary: {
    overall_completion_pct?: number;
    completed_tasks?: number;
    total_tasks?: number;
    pending_tasks?: number;
  };
  achievements: string[];
  pending_actions: string[];
  next_recommended_step: string;
}

interface RiskData {
  risk_level: string;
  risk_score: number;
  risk_flags: string[];
  recommended_interventions: string[];
}

interface RoadmapTask {
  id: number;
  title: string;
  sequence: number;
  status: string;
  priority: string;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [progressData, setProgressData] = useState<ProgressData | null>(null);
  const [riskData, setRiskData] = useState<RiskData | null>(null);
  const [tasks, setTasks] = useState<RoadmapTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const [progResp, riskResp, roadmapResp] = await Promise.allSettled([
          agentApi.progress("Give me a summary of my current progress and next recommended step."),
          agentApi.risk("Assess my current risk level."),
          roadmapApi.getMine(),
        ]);

        if (alive) {
          if (progResp.status === "fulfilled") {
            setProgressData(progResp.value as ProgressData);
          }
          if (riskResp.status === "fulfilled") {
            setRiskData(riskResp.value as RiskData);
          }
          if (roadmapResp?.status === "fulfilled") {
            setTasks(
              ((roadmapResp.value as { roadmap: { tasks: RoadmapTask[] } }).roadmap.tasks ?? [])
                .slice()
                .sort((a, b) => a.sequence - b.sequence)
                .slice(0, 5),
            );
          }
        }
      } catch (err: unknown) {
        if (alive) {
          setError(err instanceof Error ? err.message : "Could not load dashboard.");
        }
      } finally {
        if (alive) setLoading(false);
      }
    }

    void load();
    return () => { alive = false; };
  }, []);

  const overallPct = progressData?.progress_summary.overall_completion_pct ?? 0;

  const riskColor =
    riskData?.risk_level === "HIGH"
      ? "berry"
      : riskData?.risk_level === "MEDIUM"
        ? "sand"
        : "sage";

  return (
    <AppLayout
      title={`${greeting()}, ${user?.email?.split("@")[0] ?? "there"}`}
      subtitle="Here's your path forward."
    >
      <div className="space-y-8">
        {/* Next best action banner */}
        <section className="animate-pop rounded-3xl border border-primary/30 bg-surface p-6 shadow-[0_18px_46px_-32px_rgba(168,58,91,0.75)]">
          <p className="text-xs font-semibold tracking-[0.14em] text-primary uppercase">
            Next recommended step
          </p>
          {loading ? (
            <p className="mt-3 text-sm text-muted-foreground">Loading your recommendations…</p>
          ) : error ? (
            <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
              <AlertCircle className="h-4 w-4 text-destructive" />
              {error}
            </p>
          ) : (
            <>
              <h2 className="mt-3 text-xl font-semibold text-foreground">
                {progressData?.next_recommended_step || "Complete your onboarding to see your next step."}
              </h2>
              <div className="mt-4 flex gap-3">
                <Button asChild>
                  <Link to="/roadmap">View Roadmap <ArrowRight className="h-4 w-4" /></Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link to="/chat">Ask AI Guide</Link>
                </Button>
              </div>
            </>
          )}
        </section>

        {/* Summary cards */}
        <section className="grid gap-4 md:grid-cols-3">
          <Card tone="berry">
            <Shield className="h-5 w-5 text-primary" aria-hidden="true" />
            <p className="mt-3 text-xs font-semibold tracking-wide text-primary uppercase">Risk level</p>
            {loading ? (
              <p className="mt-1 text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="mt-1 flex items-center gap-2">
                <p className="text-sm font-semibold text-foreground">
                  {riskData?.risk_level ?? "—"}
                </p>
                {riskData ? (
                  <Badge tone={riskColor}>{(riskData.risk_score * 100).toFixed(0)}%</Badge>
                ) : null}
              </div>
            )}
          </Card>

          <Card tone="sage">
            <HeartPulse className="h-5 w-5 text-accent" aria-hidden="true" />
            <p className="mt-3 text-xs font-semibold tracking-wide uppercase text-muted-foreground">
              Completed tasks
            </p>
            <p className="mt-1 text-sm font-semibold text-foreground">
              {loading
                ? "—"
                : `${progressData?.progress_summary.completed_tasks ?? 0} done`}
            </p>
          </Card>

          <Card tone="sand">
            <Sprout className="h-5 w-5 text-secondary-foreground" aria-hidden="true" />
            <p className="mt-3 text-xs font-semibold tracking-wide uppercase text-muted-foreground">
              Overall progress
            </p>
            {loading ? (
              <p className="mt-1 text-sm text-muted-foreground">Loading…</p>
            ) : (
              <ProgressBar className="mt-2" value={overallPct} tone="accent" />
            )}
          </Card>
        </section>

        {/* Roadmap preview */}
        <section aria-labelledby="roadmap-preview">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-3">
            <h2 id="roadmap-preview" className="text-lg font-semibold text-foreground">
              Roadmap preview
            </h2>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/roadmap">
                Open roadmap <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-5">
            {tasks.map((task) => (
              <Card key={task.id} className="p-4">
                <p className="text-xs font-semibold text-primary">S{task.sequence}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{task.title}</p>
                <ProgressBar
                  className="mt-3"
                  value={task.status === "COMPLETED" ? 100 : task.status === "IN_PROGRESS" ? 50 : 0}
                  tone="accent"
                />
              </Card>
            ))}
          </div>
        </section>

        {/* Recent achievements */}
        {!loading && progressData?.achievements && progressData.achievements.length > 0 ? (
          <section aria-labelledby="achievements-heading">
            <h2 id="achievements-heading" className="text-lg font-semibold text-foreground">
              Recent achievements
            </h2>
            <ul className="mt-4 space-y-2">
              {progressData.achievements.slice(0, 5).map((a, i) => (
                <li
                  key={i}
                  className="rounded-xl border border-accent/40 bg-accent-soft px-4 py-3 text-sm text-foreground"
                >
                  {a}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* Risk flags */}
        {!loading && riskData?.risk_flags && riskData.risk_flags.length > 0 ? (
          <section aria-labelledby="risk-flags-heading">
            <h2 id="risk-flags-heading" className="text-lg font-semibold text-foreground">
              Risk flags
            </h2>
            <ul className="mt-4 space-y-2">
              {riskData.risk_flags.map((flag, i) => (
                <li
                  key={i}
                  className="rounded-xl border border-primary/25 bg-primary-soft px-4 py-3 text-sm text-foreground"
                >
                  {flag}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* Quick links to all agents */}
        <section aria-labelledby="agents-heading">
          <h2 id="agents-heading" className="text-lg font-semibold text-foreground">
            Specialist agents
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Ask any specialist agent directly via the Guide tab.
          </p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {[
              "Government schemes",
              "Legal information",
              "Healthcare access",
              "Financial guidance",
              "Employment support",
              "Mentor matching",
              "Planning",
              "Case worker",
              "Document guidance",
            ].map((label) => (
              <Link
                key={label}
                to="/chat"
                className="rounded-xl border border-border bg-surface px-4 py-3 text-sm font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary-soft"
              >
                {label} →
              </Link>
            ))}
          </div>
        </section>

        {loading ? <LoadingState message="Loading your dashboard data…" /> : null}
      </div>
    </AppLayout>
  );
}
