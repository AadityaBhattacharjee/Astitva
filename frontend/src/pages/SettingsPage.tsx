import { useState } from "react";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/astitva/Card";
import { Button } from "@/components/ui/button";
import { ToggleRow } from "@/components/astitva/Form";
import { useAuth } from "@/hooks/use-auth";
import { toast } from "sonner";

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const [notifications, setNotifications] = useState(true);
  const [highContrast, setHighContrast] = useState(false);
  const [lowBandwidth, setLowBandwidth] = useState(false);

  const handleHighContrast = (v: boolean) => {
    setHighContrast(v);
    document.documentElement.classList.toggle("contrast-boost", v);
    toast.success(`High contrast ${v ? "enabled" : "disabled"}.`);
  };

  return (
    <AppLayout title="Settings" subtitle="Manage your account and accessibility options.">
      <div className="space-y-6">
        <Card>
          <h2 className="text-base font-semibold text-foreground">Account</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Email</dt>
              <dd className="font-medium text-foreground">{user?.email ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Role</dt>
              <dd className="font-medium text-foreground">{user?.role ?? "USER"}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <h2 className="text-base font-semibold text-foreground">Accessibility</h2>
          <div className="mt-1">
            <ToggleRow
              label="High contrast mode"
              description="Increases contrast for better readability."
              checked={highContrast}
              onChange={handleHighContrast}
            />
            <ToggleRow
              label="Low bandwidth mode"
              description="Reduces data usage where possible."
              checked={lowBandwidth}
              onChange={(v) => { setLowBandwidth(v); toast.success(`Low bandwidth ${v ? "enabled" : "disabled"}.`); }}
            />
            <ToggleRow
              label="Notifications"
              description="Receive in-app status updates."
              checked={notifications}
              onChange={(v) => { setNotifications(v); toast.success(`Notifications ${v ? "enabled" : "disabled"}.`); }}
            />
          </div>
        </Card>

        <Card>
          <h2 className="text-base font-semibold text-foreground">About</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Backend</dt>
              <dd className="font-medium text-foreground">FastAPI · PostgreSQL · ChromaDB</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">LLM</dt>
              <dd className="font-medium text-foreground">IBM Granite 3.3 8B (Local MLX)</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Auth</dt>
              <dd className="font-medium text-foreground">JWT · HS256 · 60 min expiry</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Agents</dt>
              <dd className="font-medium text-foreground">12 implemented</dd>
            </div>
          </dl>
        </Card>

        <div className="pt-2">
          <Button
            variant="destructive"
            onClick={() => {
              logout();
              window.location.href = "/";
            }}
          >
            Sign out
          </Button>
        </div>
      </div>
    </AppLayout>
  );
}
