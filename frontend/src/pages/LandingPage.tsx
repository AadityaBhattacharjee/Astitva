import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowRight,
  BadgeCheck,
  Brain,
  Compass,
  Languages,
  Map,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";

const flow = [
  "Create Account",
  "Answer a Few Questions",
  "AI Life Profile",
  "Verified Support",
  "Prioritized Actions",
];

const features = [
  {
    icon: Map,
    title: "Personalized Life Roadmap",
    body: "One clear path through safety, stability and growth — not a directory of links.",
    tone: "bg-surface",
  },
  {
    icon: BadgeCheck,
    title: "Verified Support",
    body: "Every recommendation carries the organization and source behind it.",
    tone: "bg-accent-soft",
  },
  {
    icon: Brain,
    title: "AI Decision Intelligence",
    body: "Granite 3.3 8B running locally ranks what matters now by urgency and eligibility.",
    tone: "bg-surface",
  },
  {
    icon: Compass,
    title: "12 Specialist Agents",
    body: "Government, legal, health, finance, employment, planning, risk and more.",
    tone: "bg-secondary-soft",
  },
  {
    icon: TrendingUp,
    title: "Real Progress Tracking",
    body: "Progress computed from your actual roadmap and task data — no estimates.",
    tone: "bg-surface",
  },
  {
    icon: Languages,
    title: "Multilingual & Accessible",
    body: "Readable typography, keyboard navigation and low-bandwidth support.",
    tone: "bg-accent-soft",
  },
];

export default function LandingPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [loadingDemo, setLoadingDemo] = useState(false);

  const goToDashboard = async () => {
    setLoadingDemo(true);
    if (isAuthenticated) {
      await navigate("/dashboard");
    } else {
      toast.info("Please create an account or log in to get started.");
      await navigate("/register");
    }
    setLoadingDemo(false);
  };

  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <Link to="/" className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-sm font-bold text-primary-foreground">
              A
            </span>
            <span className="font-display text-lg font-bold tracking-tight">ASTITVA</span>
          </Link>
          <nav className="hidden items-center gap-7 text-sm font-medium text-muted-foreground md:flex">
            <a className="hover:text-foreground" href="#how">How it works</a>
            <a className="hover:text-foreground" href="#features">Features</a>
            <a className="hover:text-foreground" href="#privacy">Privacy</a>
          </nav>
          <div className="flex items-center gap-2">
            {isAuthenticated ? (
              <Button size="sm" asChild>
                <Link to="/dashboard">Dashboard</Link>
              </Button>
            ) : (
              <>
                <Button variant="outline" size="sm" asChild>
                  <Link to="/login">Log in</Link>
                </Button>
                <Button size="sm" asChild>
                  <Link to="/register">Get started</Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section id="hero" className="mx-auto max-w-6xl px-5 pt-14 pb-16 lg:pt-20">
          <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-1.5 text-xs font-medium text-muted-foreground">
                <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                AI Life Orchestration · IBM Granite 3.3 8B · Local MLX
              </p>

              <h1 className="mt-6 text-4xl leading-[1.08] font-bold tracking-tight text-balance text-foreground sm:text-5xl lg:text-6xl">
                Rebuilding Lives.
                <br />
                <span className="text-primary">Restoring Identity.</span>
              </h1>

              <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
                Astitva brings fragmented support together into one personalized path toward safety,
                stability and independence.
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                <Button size="lg" asChild>
                  <Link to="/register">
                    Build My Life Roadmap
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
                <Button size="lg" variant="outline" onClick={goToDashboard} loading={loadingDemo}>
                  {isAuthenticated ? "Go to Dashboard" : "Get Started"}
                </Button>
              </div>

              <p className="mt-6 text-sm text-muted-foreground">
                Astitva does not replace government, legal, health or financial services. It helps
                you navigate the ones that already exist.
              </p>
            </div>

            <JourneyVisual />
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="border-y border-border bg-surface/70">
          <div className="mx-auto max-w-6xl px-5 py-16">
            <h2 className="text-3xl font-bold tracking-tight text-foreground">
              Support Exists. <span className="text-primary">Navigation Doesn't.</span>
            </h2>
            <p className="mt-3 max-w-2xl text-muted-foreground">
              Schemes, NGOs, legal aid and employment programmes already exist. What's missing is a
              way to know which one matters today, and what to do next.
            </p>

            <ol className="mt-10 grid gap-3 md:grid-cols-5">
              {flow.map((step, index) => (
                <li
                  key={step}
                  className="relative rounded-2xl border border-border bg-background p-4"
                >
                  <span className="text-xs font-semibold text-primary">0{index + 1}</span>
                  <p className="mt-2 text-sm font-semibold text-foreground">{step}</p>
                  {index < flow.length - 1 ? (
                    <span
                      aria-hidden="true"
                      className="absolute top-1/2 -right-2 hidden h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-secondary md:block"
                    />
                  ) : null}
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="mx-auto max-w-6xl px-5 py-16">
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Built around one question: what should I do next?
          </h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <div
                key={feature.title}
                className={`rounded-2xl border border-border p-5 ${feature.tone}`}
              >
                <feature.icon className="h-5 w-5 text-primary" aria-hidden="true" />
                <h3 className="mt-4 text-base font-semibold text-foreground">{feature.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{feature.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Privacy */}
        <section id="privacy" className="mx-auto max-w-6xl px-5 pb-20">
          <div className="grid gap-6 rounded-3xl border border-border bg-secondary-soft p-8 md:grid-cols-[auto_1fr] md:items-center">
            <ShieldCheck className="h-10 w-10 text-accent" aria-hidden="true" />
            <div>
              <h2 className="text-2xl font-bold text-foreground">Private by default</h2>
              <p className="mt-2 max-w-2xl text-muted-foreground">
                JWT-secured sessions, no data shared without consent. Your queries stay between you
                and Granite running locally on-device.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>Astitva — Don't just tell her what exists. Help her understand what to do next.</p>
          <p>FastAPI · Granite 3.3 8B · Local MLX</p>
        </div>
      </footer>
    </div>
  );
}

function JourneyVisual() {
  const nodes = [
    { label: "Safety", color: "bg-primary", text: "text-primary-foreground" },
    { label: "Stability", color: "bg-accent", text: "text-accent-foreground" },
    { label: "Financial Independence", color: "bg-secondary", text: "text-secondary-foreground" },
    { label: "Career & Education", color: "bg-accent", text: "text-accent-foreground" },
    { label: "Long-Term Growth", color: "bg-primary", text: "text-primary-foreground" },
  ];

  return (
    <div className="rounded-3xl border border-border bg-surface p-6 sm:p-8">
      <p className="text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">
        A sample life roadmap
      </p>
      <ol className="relative mt-6 space-y-5 pl-8">
        <span
          aria-hidden="true"
          className="absolute top-2 bottom-2 left-[13px] w-0.5 rounded-full bg-gradient-to-b from-primary via-secondary to-accent"
        />
        {nodes.map((node, index) => (
          <li key={node.label} className="relative">
            <span
              aria-hidden="true"
              className={`absolute -left-8 flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold ${node.color} ${node.text}`}
            >
              0{index + 1}
            </span>
            <div className="rounded-xl border border-border bg-background px-4 py-3">
              <p className="text-sm font-semibold text-foreground">{node.label}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
