import { useEffect, useState } from "react";
import { userApi, agentApi } from "@/api/client";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/astitva/Card";
import { Badge } from "@/components/astitva/Badge";
import { Button } from "@/components/ui/button";
import { TextArea } from "@/components/astitva/Form";
import { LoadingState } from "@/components/astitva/States";
import { toast } from "sonner";
import { useAuth } from "@/hooks/use-auth";

interface ProfileData {
  id?: number;
  user_id?: number;
  full_name: string | null;
  state: string | null;
  language: string | null;
}

interface CaseData {
  case_summary: string;
  priority_actions: Array<{ title?: string; description?: string; priority?: string; action?: string }>;
  document_gaps: string[];
  roadmap_status: string;
  risk_flags: string[];
}

export default function ProfilePage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [caseData, setCaseData] = useState<CaseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.allSettled([
      userApi.getProfile(),
      agentApi.case_worker("Give me a complete case assessment and my current status."),
    ]).then(([profileResp, caseResp]) => {
      if (!alive) return;
      if (profileResp.status === "fulfilled") {
        setProfile(profileResp.value as ProfileData);
        setDraft(profileResp.value.full_name ?? "");
      }
      if (caseResp.status === "fulfilled") {
        setCaseData(caseResp.value as unknown as CaseData);
      }
      setLoading(false);
    });
    return () => { alive = false; };
  }, []);

  if (loading) {
    return (
      <AppLayout title="Your profile">
        <LoadingState message="Loading your profile and case data…" />
      </AppLayout>
    );
  }

  return (
    <AppLayout title="Your profile" subtitle="Your context, priorities and case summary.">
      <div className="space-y-6">
        {/* Account info */}
        <Card>
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
            <h2 className="text-base font-semibold text-foreground">Account</h2>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                if (editing) {
                  // In a real app: PATCH /api/v1/profile/me
                  toast.success("Profile updated locally.");
                }
                setEditing((e) => !e);
              }}
            >
              {editing ? "Save" : "Edit"}
            </Button>
          </div>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Email</dt>
              <dd className="font-medium text-foreground">{user?.email ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Role</dt>
              <dd className="font-medium text-foreground">{user?.role ?? "USER"}</dd>
            </div>
            {profile?.state ? (
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">State</dt>
                <dd className="font-medium text-foreground">{profile.state}</dd>
              </div>
            ) : null}
            {profile?.language ? (
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Language</dt>
                <dd className="font-medium text-foreground">{profile.language}</dd>
              </div>
            ) : null}
          </dl>
          {editing ? (
            <div className="mt-4">
              <TextArea
                label="Full name"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Your full name"
              />
            </div>
          ) : null}
        </Card>

        {/* Case summary from Case Worker agent */}
        {caseData ? (
          <>
            <Card tone="berry">
              <h2 className="text-base font-semibold text-foreground">Case summary</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {caseData.case_summary !== "LLM provider placeholder response."
                  ? caseData.case_summary
                  : "Start your journey by completing the onboarding and adding roadmap tasks."}
              </p>
              <div className="mt-3 flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Roadmap status:</span>
                <Badge tone="sage">{caseData.roadmap_status}</Badge>
              </div>
            </Card>

            {/* Priority actions */}
            {caseData.priority_actions.length > 0 ? (
              <Card>
                <h2 className="text-base font-semibold text-foreground">Priority actions</h2>
                <ul className="mt-3 space-y-2">
                  {caseData.priority_actions.map((action, i) => (
                    <li key={i} className="rounded-xl bg-background/70 px-4 py-3 text-sm">
                      <p className="font-medium text-foreground">
                        {action.title ?? action.action ?? `Action ${i + 1}`}
                      </p>
                      {action.description ? (
                        <p className="text-muted-foreground">{action.description}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}

            {/* Document gaps */}
            {caseData.document_gaps.length > 0 ? (
              <Card tone="sand">
                <h2 className="text-base font-semibold text-foreground">Document gaps</h2>
                <ul className="mt-3 space-y-1.5 text-sm text-muted-foreground">
                  {caseData.document_gaps.map((gap, i) => (
                    <li key={i}>• {gap}</li>
                  ))}
                </ul>
              </Card>
            ) : null}

            {/* Risk flags */}
            {caseData.risk_flags.length > 0 ? (
              <Card tone="berry">
                <h2 className="text-base font-semibold text-foreground">Risk flags</h2>
                <ul className="mt-3 space-y-1.5 text-sm text-muted-foreground">
                  {caseData.risk_flags.map((flag, i) => (
                    <li key={i}>⚠ {flag}</li>
                  ))}
                </ul>
              </Card>
            ) : null}
          </>
        ) : null}
      </div>
    </AppLayout>
  );
}
