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

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function polarToCartesian(cx: number, cy: number, radius: number, angleDeg: number) {
  const angle = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  };
}

function RadarChart({
  overall,
  completed,
  total,
  pending,
  overdue,
  achievements,
}: {
  overall: number;
  completed: number;
  total: number;
  pending: number;
  overdue: number;
  achievements: number;
}) {
  const normalizedTotal = Math.max(total, 1);
  const completedRatio = completed / normalizedTotal;
  const pendingRatio = pending / normalizedTotal;
  const overdueRatio = overdue / normalizedTotal;
  const achievementBoost = Math.min(achievements * 6, 24);

  // Deterministic mapping until the backend exposes dimension-specific progress metrics.
  const dimensions = [
    { label: "Safety", value: clampPercent(100 - overdueRatio * 100) },
    { label: "Stability", value: clampPercent(100 - pendingRatio * 100) },
    { label: "Finance", value: clampPercent(overall) },
    { label: "Career", value: clampPercent(completedRatio * 100 + achievementBoost) },
    { label: "Growth", value: clampPercent(overall + achievementBoost - overdueRatio * 20) },
  ];

  const size = 320;
  const center = size / 2;
  const radius = 108;
  const levels = 4;

  const polygonPoints = dimensions
    .map((dimension, index) => {
      const point = polarToCartesian(
        center,
        center,
        (radius * dimension.value) / 100,
        (360 / dimensions.length) * index,
      );
      return `${point.x},${point.y}`;
    })
    .join(" ");

  return (
    <Card>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_16rem] lg:items-center">
        <div className="mx-auto w-full max-w-[22rem]">
          <svg
            viewBox={`0 0 ${size} ${size}`}
            className="h-auto w-full overflow-visible"
            role="img"
            aria-label="Radar chart showing progress across Safety, Stability, Finance, Career, and Growth"
          >
            <defs>
              <linearGradient id="progress-radar-fill" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgba(168,58,91,0.32)" />
                <stop offset="100%" stopColor="rgba(80,132,104,0.2)" />
              </linearGradient>
            </defs>

            {Array.from({ length: levels }, (_, levelIndex) => {
              const levelRadius = (radius / levels) * (levelIndex + 1);
              const points = dimensions
                .map((_, index) => {
                  const point = polarToCartesian(
                    center,
                    center,
                    levelRadius,
                    (360 / dimensions.length) * index,
                  );
                  return `${point.x},${point.y}`;
                })
                .join(" ");
              return (
                <polygon
                  key={levelRadius}
                  points={points}
                  fill="none"
                  stroke="rgba(109, 104, 117, 0.18)"
                  strokeWidth="1"
                />
              );
            })}

            {dimensions.map((dimension, index) => {
              const axis = polarToCartesian(
                center,
                center,
                radius + 18,
                (360 / dimensions.length) * index,
              );
              const label = polarToCartesian(
                center,
                center,
                radius + 34,
                (360 / dimensions.length) * index,
              );
              return (
                <g key={dimension.label}>
                  <line
                    x1={center}
                    y1={center}
                    x2={axis.x}
                    y2={axis.y}
                    stroke="rgba(109, 104, 117, 0.22)"
                    strokeWidth="1"
                  />
                  <text
                    x={label.x}
                    y={label.y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="fill-muted-foreground text-[11px] font-medium"
                  >
                    {dimension.label}
                  </text>
                </g>
              );
            })}

            <polygon
              points={polygonPoints}
              fill="url(#progress-radar-fill)"
              stroke="rgba(168,58,91,0.95)"
              strokeWidth="2.5"
            />

            {dimensions.map((dimension, index) => {
              const point = polarToCartesian(
                center,
                center,
                (radius * dimension.value) / 100,
                (360 / dimensions.length) * index,
              );
              return (
                <circle
                  key={dimension.label}
                  cx={point.x}
                  cy={point.y}
                  r="4.5"
                  fill="rgb(168,58,91)"
                  stroke="rgb(255,248,242)"
                  strokeWidth="2"
                />
              );
            })}

            <circle
              cx={center}
              cy={center}
              r="42"
              fill="rgb(255,248,242)"
              stroke="rgba(168,58,91,0.18)"
              strokeWidth="1.5"
            />
            <text
              x={center}
              y={center - 4}
              textAnchor="middle"
              className="fill-foreground text-[28px] font-semibold"
            >
              {Math.round(overall)}%
            </text>
            <text
              x={center}
              y={center + 16}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px] font-medium uppercase tracking-[0.18em]"
            >
              Overall
            </text>
          </svg>
        </div>

        <div className="space-y-3">
          <div>
            <h2 className="text-base font-semibold text-foreground">Progress dimensions</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Derived from your real completion, pending, overdue, and achievement data.
            </p>
          </div>
          <ul className="space-y-3">
            {dimensions.map((dimension) => (
              <li key={dimension.label}>
                <div className="mb-1 flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-foreground">{dimension.label}</span>
                  <span className="text-muted-foreground">{Math.round(dimension.value)}%</span>
                </div>
                <ProgressBar value={dimension.value} tone="accent" />
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
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

  const pct = data.progress_summary.overall_completion_pct ?? 0;
  const completed = data.progress_summary.completed_tasks ?? 0;
  const total = data.progress_summary.total_tasks ?? 0;
  const pending = data.progress_summary.pending_tasks ?? 0;
  const overdue = data.progress_summary.overdue_tasks ?? 0;

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
                {completed}
              </p>
              <p className="text-xs text-muted-foreground">Completed</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">
                {pending}
              </p>
              <p className="text-xs text-muted-foreground">Pending</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">
                {overdue}
              </p>
              <p className="text-xs text-muted-foreground">Overdue</p>
            </div>
          </div>
        </Card>

        <RadarChart
          overall={pct}
          completed={completed}
          total={total}
          pending={pending}
          overdue={overdue}
          achievements={data.achievements.length}
        />

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
