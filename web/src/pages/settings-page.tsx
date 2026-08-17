// Settings — workspace configuration, safety policy, profile, and theme.
import React, { useEffect, useState } from "react";
import { Bell, Moon, Save, ShieldAlert, Sun, User } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../components/auth";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input, Switch } from "../components/ui";

type Theme = "dark" | "light";

export function SettingsPage() {
  const { workspace, reload } = useWorkspace();
  const { user, refreshUser } = useAuth();
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains("light") ? "light" : "dark",
  );
  const [name, setName] = useState(workspace?.name ?? "");
  const [allowDestructive, setAllowDestructive] = useState<boolean>(
    Boolean(workspace?.settings && (workspace.settings as Record<string, unknown>).allow_destructive),
  );
  const [notifications, setNotifications] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (workspace) {
      setName(workspace.name);
      setAllowDestructive(Boolean((workspace.settings as Record<string, unknown>)?.allow_destructive));
      const notif = (workspace.settings as Record<string, unknown>)?.notifications;
      setNotifications(typeof notif === "object" && notif !== null ? (notif as Record<string, unknown>) : {});
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyTheme = (t: Theme) => {
    setTheme(t);
    document.documentElement.classList.toggle("light", t === "light");
    localStorage.setItem("af_theme", t);
  };

  useEffect(() => {
    const stored = localStorage.getItem("af_theme") as Theme | null;
    if (stored) applyTheme(stored);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveWorkspace = async () => {
    if (!workspace) return;
    setSaving(true);
    setSaved(false);
    try {
      await api.patch(`/api/v1/workspaces/${workspace.id}`, {
        name,
        settings: {
          ...(workspace.settings as Record<string, unknown>),
          allow_destructive: allowDestructive,
          notifications,
        },
      });
      await reload();
      setSaved(true);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Workspace, safety, and profile.</p>
      </div>

      {/* Workspace */}
      <Card>
        <CardHeader>
          <CardTitle>Workspace</CardTitle>
          <CardDescription>
            {workspace?.role === "owner" || workspace?.role === "admin"
              ? "You can edit workspace configuration."
              : "Members can view; owners and admins can edit."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={workspace?.role !== "owner" && workspace?.role !== "admin"}
            />
          </Field>

          <div className="flex items-center justify-between rounded-md border border-border p-3">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 h-4 w-4 text-warning" />
              <div>
                <p className="text-sm font-medium">Allow destructive tools</p>
                <p className="text-xs text-muted-foreground">
                  When off, DESTRUCTIVE tools are blocked by the runtime for all
                  agents. When on, gated agents may run them after approval.
                </p>
              </div>
            </div>
            <Switch
              checked={allowDestructive}
              onCheckedChange={setAllowDestructive}
              disabled={workspace?.role !== "owner" && workspace?.role !== "admin"}
              label="Allow destructive tools"
            />
          </div>

          <div className="flex items-center justify-end gap-3">
            {saved && <Badge tone="success">Saved</Badge>}
            <Button onClick={saveWorkspace} loading={saving}>
              <Save className="h-4 w-4" /> Save workspace
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Notifications (Phase 5.4) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-4 w-4" /> Notifications
          </CardTitle>
          <CardDescription>
            Fire Discord / generic webhook / email alerts when runs complete or
            gated proposals await review.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex items-center justify-between rounded-md border border-border p-3">
              <div>
                <p className="text-sm font-medium">Run completed</p>
                <p className="text-xs text-muted-foreground">Notify when a run finishes.</p>
              </div>
              <Switch
                checked={Boolean(notifications.on_run_complete)}
                onCheckedChange={(v) => setNotifications((n) => ({ ...n, on_run_complete: v }))}
                disabled={workspace?.role !== "owner" && workspace?.role !== "admin"}
                label="Notify on run complete"
              />
            </div>
            <div className="flex items-center justify-between rounded-md border border-border p-3">
              <div>
                <p className="text-sm font-medium">Proposal pending</p>
                <p className="text-xs text-muted-foreground">Notify when a gated run awaits approval.</p>
              </div>
              <Switch
                checked={Boolean(notifications.on_proposal)}
                onCheckedChange={(v) => setNotifications((n) => ({ ...n, on_proposal: v }))}
                disabled={workspace?.role !== "owner" && workspace?.role !== "admin"}
                label="Notify on proposal"
              />
            </div>
          </div>
          <Field label="Discord webhook URL" hint="Rich embed sent to this webhook.">
            <Input
              value={(notifications.discord_webhook_url as string) ?? ""}
              onChange={(e) => setNotifications((n) => ({ ...n, discord_webhook_url: e.target.value }))}
              placeholder="https://discord.com/api/webhooks/…"
              disabled={workspace?.role !== "owner" && workspace?.role !== "admin"}
            />
          </Field>
          <Field label="Generic webhook URL" hint="JSON payload with event name + run/proposal details.">
            <Input
              value={(notifications.webhook_url as string) ?? ""}
              onChange={(e) => setNotifications((n) => ({ ...n, webhook_url: e.target.value }))}
              placeholder="https://hooks.example.com/agentfactory"
              disabled={workspace?.role !== "owner" && workspace?.role !== "admin"}
            />
          </Field>
          <Field label="Email (Gmail SMTP)" hint="Needs GMAIL_USER + GMAIL_APP_PASSWORD env vars set on the server.">
            <Input
              value={(notifications.email as string) ?? ""}
              onChange={(e) => setNotifications((n) => ({ ...n, email: e.target.value }))}
              placeholder="ops@example.com"
              disabled={workspace?.role !== "owner" && workspace?.role !== "admin"}
            />
          </Field>
          <div className="flex items-center justify-end">
            <Button variant="secondary" onClick={saveWorkspace} loading={saving}>
              <Save className="h-4 w-4" /> Save notifications
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Appearance */}
      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>Theme preference is stored locally.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2">
            <Button
              variant={theme === "dark" ? "primary" : "secondary"}
              onClick={() => applyTheme("dark")}
            >
              <Moon className="h-4 w-4" /> Dark
            </Button>
            <Button
              variant={theme === "light" ? "primary" : "secondary"}
              onClick={() => applyTheme("light")}
            >
              <Sun className="h-4 w-4" /> Light
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Profile */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-4 w-4" /> Profile
          </CardTitle>
          <CardDescription>Your account on this platform.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Email">
            <Input value={user?.email ?? ""} disabled />
          </Field>
          <Field label="Name">
            <Input value={user?.name ?? ""} disabled />
          </Field>
          <p className="text-xs text-muted-foreground">
            Member since {user?.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}
            {user?.id ? ` · id ${user.id.slice(0, 8)}…` : ""}
          </p>
          <Button variant="secondary" onClick={() => refreshUser().catch(() => undefined)}>
            Refresh profile
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
