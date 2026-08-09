import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { StepIndicator } from "@/components/astitva/StepIndicator";
import { OptionGroup, Select, TextInput } from "@/components/astitva/Form";

const steps = ["About You", "Current Situation", "Immediate Needs", "Goals", "Constraints", "Review"];

const processingMessages = [
  "Understanding your situation…",
  "Finding relevant support…",
  "Setting up your workspace…",
];

interface Assessment {
  ageRange: string;
  location: string;
  language: string;
  situation: string[];
  employmentStatus: string;
  housing: string;
  dependents: string;
  safetyConcern: string;
  legalNeeds: string[];
  healthcareNeeds: string[];
  financialNeeds: string[];
  goals: string[];
  careerNeeds: string[];
  constraints: string[];
  communicationPreference: string;
}

const empty: Assessment = {
  ageRange: "",
  location: "",
  language: "English",
  situation: [],
  employmentStatus: "",
  housing: "",
  dependents: "",
  safetyConcern: "",
  legalNeeds: [],
  healthcareNeeds: [],
  financialNeeds: [],
  goals: [],
  careerNeeds: [],
  constraints: [],
  communicationPreference: "",
};

function ReviewRow({ label, value }: { label: string; value?: string }) {
  return (
    <div className="grid grid-cols-[40%_minmax(0,1fr)] gap-3 py-3 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium text-foreground">{value?.trim() ? value : "Not answered"}</dd>
    </div>
  );
}

function Intro({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h2 className="text-xl font-semibold text-foreground">{title}</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{body}</p>
    </div>
  );
}

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [assessment, setAssessment] = useState<Assessment>(empty);
  const [processing, setProcessing] = useState(false);
  const [processingIndex, setProcessingIndex] = useState(0);

  const update = (patch: Partial<Assessment>) => setAssessment((a) => ({ ...a, ...patch }));
  const setList =
    (key: keyof Assessment) => (next: string[]) =>
      update({ [key]: next } as Partial<Assessment>);

  const submit = async () => {
    setProcessing(true);
    for (let i = 0; i < processingMessages.length; i++) {
      setProcessingIndex(i);
      await new Promise((r) => setTimeout(r, 750));
    }
    // Store assessment in sessionStorage for Dashboard to use
    sessionStorage.setItem("astitva.assessment", JSON.stringify(assessment));
    toast.success("Your profile is ready!");
    await navigate("/dashboard");
  };

  if (processing) {
    return (
      <div className="grid min-h-dvh place-items-center bg-background px-6">
        <div className="w-full max-w-sm rounded-3xl border border-border bg-surface p-8 text-center">
          <Loader2 className="mx-auto h-7 w-7 animate-spin text-primary" aria-hidden="true" />
          <p className="mt-5 text-base font-semibold text-foreground" aria-live="polite">
            {processingMessages[processingIndex]}
          </p>
          <div className="mt-6 flex justify-center gap-1.5" aria-hidden="true">
            {processingMessages.map((msg, i) => (
              <span
                key={msg}
                className={`h-1.5 rounded-full transition-all ${
                  i <= processingIndex ? "w-8 bg-primary" : "w-4 bg-muted"
                }`}
              />
            ))}
          </div>
          <p className="mt-6 text-sm text-muted-foreground">
            This stays private. You can change any answer later.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-5 py-4">
          <Link to="/" className="font-display text-base font-bold tracking-tight">
            ASTITVA
          </Link>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
            Private
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-5 py-8">
        <StepIndicator steps={steps} current={step} />

        <div
          key={step}
          className="mt-8 animate-fade-in-up space-y-6 rounded-3xl border border-border bg-surface p-6"
        >
          {step === 0 ? (
            <>
              <Intro
                title="Let's start with a little about you"
                body="Only what's needed to find the right support. Nothing is shared without your consent."
              />
              <Select
                label="Age range"
                options={["18-24", "25-29", "30-39", "40-49", "50+"]}
                value={assessment.ageRange}
                onChange={(e) => update({ ageRange: e.target.value })}
              />
              <TextInput
                label="Where are you based?"
                placeholder="City, state"
                value={assessment.location}
                onChange={(e) => update({ location: e.target.value })}
              />
              <Select
                label="Preferred language"
                options={["English", "हिन्दी", "मराठी", "தமிழ்", "বাংলা"]}
                value={assessment.language}
                onChange={(e) => update({ language: e.target.value })}
              />
            </>
          ) : null}

          {step === 1 ? (
            <>
              <Intro
                title="What best describes your situation right now?"
                body="Choose everything that applies."
              />
              <OptionGroup
                label="Current situation"
                multiple
                options={["Left an unsafe household", "Widowed", "Separated or divorced", "Single parent", "Career break", "Financially dependent"]}
                value={assessment.situation}
                onChange={setList("situation")}
              />
              <Select
                label="Employment status"
                options={["Not working right now", "Working part-time", "Working full-time", "Self-employed"]}
                value={assessment.employmentStatus}
                onChange={(e) => update({ employmentStatus: e.target.value })}
              />
              <Select
                label="Housing"
                options={["My own home", "Staying with family temporarily", "Rented accommodation", "Looking for a safe place"]}
                value={assessment.housing}
                onChange={(e) => update({ housing: e.target.value })}
              />
              <Select
                label="Dependents"
                options={["None", "1 child", "2 or more children", "Elderly family member"]}
                value={assessment.dependents}
                onChange={(e) => update({ dependents: e.target.value })}
              />
            </>
          ) : null}

          {step === 2 ? (
            <>
              <Intro title="What needs attention first?" body="This helps Astitva place safety before everything else." />
              <Select
                label="Is there an immediate safety concern?"
                options={["Yes, right now", "Resolved for now", "No"]}
                value={assessment.safetyConcern}
                onChange={(e) => update({ safetyConcern: e.target.value })}
              />
              <OptionGroup
                label="Legal needs"
                multiple
                options={["Protection order", "Maintenance", "Custody", "Property rights", "Not sure yet"]}
                value={assessment.legalNeeds}
                onChange={setList("legalNeeds")}
              />
              <OptionGroup
                label="Health needs"
                multiple
                options={["General check-up", "Counselling", "Ongoing treatment", "Child healthcare"]}
                value={assessment.healthcareNeeds}
                onChange={setList("healthcareNeeds")}
              />
              <OptionGroup
                label="Financial needs"
                multiple
                options={["Emergency assistance", "Bank account", "Monthly support", "Debt guidance"]}
                value={assessment.financialNeeds}
                onChange={setList("financialNeeds")}
              />
            </>
          ) : null}

          {step === 3 ? (
            <>
              <Intro title="What would you like to move toward?" body="Your goals shape the later stages of your roadmap." />
              <OptionGroup
                label="Goals"
                multiple
                options={["Live somewhere I feel safe", "Earn an income of my own", "Finish or restart my education", "Keep my child in school", "Build savings"]}
                value={assessment.goals}
                onChange={setList("goals")}
              />
              <OptionGroup
                label="Career or education support"
                multiple
                options={["Skill training", "Job placement", "Flexible hours", "Resume help"]}
                value={assessment.careerNeeds}
                onChange={setList("careerNeeds")}
              />
            </>
          ) : null}

          {step === 4 ? (
            <>
              <Intro title="What should Astitva work around?" body="Constraints are practical, not limitations." />
              <OptionGroup
                label="Constraints"
                multiple
                options={["Childcare responsibilities", "Limited travel budget", "Limited phone data", "Prefer not to share my address", "Limited free time on weekdays"]}
                value={assessment.constraints}
                onChange={setList("constraints")}
              />
              <Select
                label="How would you like to hear from us?"
                options={["In-app messages", "Phone call", "SMS", "No notifications"]}
                value={assessment.communicationPreference}
                onChange={(e) => update({ communicationPreference: e.target.value })}
              />
            </>
          ) : null}

          {step === 5 ? (
            <>
              <Intro title="Review before we build your profile" body="You can update anything later from your profile." />
              <dl className="divide-y divide-border rounded-2xl bg-background/70 px-4">
                <ReviewRow label="Age range" value={assessment.ageRange} />
                <ReviewRow label="Location" value={assessment.location} />
                <ReviewRow label="Situation" value={assessment.situation.join(", ")} />
                <ReviewRow label="Employment" value={assessment.employmentStatus} />
                <ReviewRow label="Housing" value={assessment.housing} />
                <ReviewRow label="Safety concern" value={assessment.safetyConcern} />
                <ReviewRow label="Goals" value={assessment.goals.join(", ")} />
                <ReviewRow label="Constraints" value={assessment.constraints.join(", ")} />
              </dl>
            </>
          ) : null}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <Button
            variant="ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back
          </Button>

          <div className="flex flex-wrap gap-2">
            <Button variant="subtle" onClick={() => toast.success("Saved. You can come back anytime.")}>
              Save &amp; continue later
            </Button>
            {step < steps.length - 1 ? (
              <Button onClick={() => setStep((s) => s + 1)}>
                Continue
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            ) : (
              <Button onClick={submit}>Create My Life Profile</Button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
