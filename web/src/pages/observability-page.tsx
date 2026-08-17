// Observability (Phase 5.2) — cost/token dashboards, budget alerts, run events.
import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, Clock, Coins, Gauge, Zap } from "lucide-react";
import { api } from "../lib/api";
import { useWorkspace } from "../components/workspaces";
import { Badge, Card, EmptyState, Skeleton } from "../components/ui";
import { cn, formatUsd } from "../lib/utils";

interface SummaryTotals {
  runs: number;
  completed: number;
  failed: number;
  cancelled: number;
  pending: number;
  total_cost_usd: number;
  total_tokens: number;
  total_duration_seconds: number;
}

interface AgentRollup {
  runs: number;
  total_cost_usd: number;
  total_tokens: number;
}

interface BudgetEntry {
  agent_id: string;
  agent_name: string;
  spend_today_usd: number;
  budget_usd: number;
  pct: number;
  level: "ok" | "warn" | "exceeded";
}

interface RunEvent {
  run_id: string;
  seq: number;
  event: string;
  data: Record<string, unknown>;
  ts: string;
}

const LEVEL_TONE = { ok: "success", warn: "warning", exceeded: "destructive" } as const;

export function ObservabilityPage() {
  const { workspace } = useWorkspace();
  const [totals, setTotals] = useState<SummaryTotals | null>(null);
  const [perAgent, setPerAgent] = useState<Record<string, AgentRollup>>({});
  const [budgets, setBudgets] = useState<BudgetEntry[]>([]);
  const [alerts, setAlerts] = useState<Array<{ level: string; message: string; created_at: string }>>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspace) return;
    try {
      const summary = await api.get<{ totals: SummaryTotals; per_agent: Record<string, AgentRollup> }>(
        `/api/v1/workspaces/${workspace.id}/observability/summary`,
      );
      setTotals(summary.totals);
      setPerAgent(summary.per_agent);
      const budgetData = await api.get<{ agents: BudgetEntry[] }>(
        `/api/v1/workspaces/${workspace.id}/observability/budgets`,
      );
      setBudgets(budgetData.agents);
      const alertData = await api.get<{ alerts: Array<{ level: string; message: string; created_at: string }> }>(
        `/api/v1/workspaces/${workspace.id}/observability/alerts`,
      );
      setAlerts(alertData.alerts);
      const eventData = await api.get<{ events: RunEvent[] }>(
        `/api/v1/workspaces/${workspace.id}/observability/events?limit=40`,
      );
      setEvents(eventData.events);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load observability");
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const stats = [
    { label: "Total runs", value: String(totals?.runs ?? 0), icon: Activity },
    { label: "Completed", value: String(totals?.completed ?? 0), icon: Gauge },
    { label: "Failed", value: String(totals?.failed ?? 0), icon: AlertTriangle },
    { label: "Total cost", value: formatUsd(totals?.total_cost_usd ?? 0), icon: Coins },
    { label: "Total tokens", value: (totals?.total_tokens ?? 0).toLocaleString(), icon: Zap },
    { label: "Runtime", value: `${(totals?.total_duration_seconds ?? 0).toFixed(1)}s`, icon: Clock },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Observability</h1>
        <p className="text-sm text-muted-foreground">
          Cost, tokens, budgets, and structured run events.
        </p>
      </div>

      {error && <EmptyState title="Couldn't load observability" description={error} />}
      {!totals && !error && <Skeleton className="h-48" />}

      {totals && (
        <>
          {/* Totals */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
            {stats.map(({ label, value, icon: Icon }) => (
              <Card key={label} className="p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Icon className="h-3.5 w-3.5" /> {label}
                </div>
                <p className="mt-1.5 text-xl font-bold tabular-nums tracking-tight">{value}</p>
              </Card>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Budgets */}
            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold">Daily budgets</h2>
              {budgets.length === 0 && (
                <p className="text-sm text-muted-foreground">No agents with budgets yet.</p>
              )}
              <div className="space-y-3">
                {budgets.map((b) => (
                  <div key={b.agent_id}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span className="font-medium">{b.agent_name}</span>
                      <span className="flex items-center gap-2 text-xs text-muted-foreground">
                        {formatUsd(b.spend_today_usd)} / {formatUsd(b.budget_usd)}
                        <Badge tone={LEVEL_TONE[b.level]}>{b.level}</Badge>
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all",
                          b.level === "exceeded" ? "bg-destructive" : b.level === "warn" ? "bg-warning" : "bg-success",
                        )}
                        style={{ width: `${Math.min(100, b.pct)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              {alerts.length > 0 && (
                <div className="mt-4 space-y-1.5 border-t border-border pt-3">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    Budget alerts
                  </p>
                  {alerts.map((a, i) => (
                    <p key={i} className="flex items-start gap-2 text-xs">
                      <Badge tone={a.level === "exceeded" ? "destructive" : "warning"}>{a.level}</Badge>
                      <span className="text-muted-foreground">{a.message}</span>
                    </p>
                  ))}
                </div>
              )}
            </Card>

            {/* Per-agent costs */}
            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold">Cost by agent</h2>
              {Object.keys(perAgent).length === 0 && (
                <p className="text-sm text-muted-foreground">No runs yet.</p>
              )}
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="pb-2 font-medium">Agent</th>
                    <th className="pb-2 text-right font-medium">Runs</th>
                    <th className="pb-2 text-right font-medium">Cost</th>
                    <th className="pb-2 text-right font-medium">Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(perAgent).map(([name, v]) => (
                    <tr key={name} className="border-t border-border">
                      <td className="py-2 font-medium">{name}</td>
                      <td className="py-2 text-right tabular-nums">{v.runs}</td>
                      <td className="py-2 text-right tabular-nums">{formatUsd(v.total_cost_usd)}</td>
                      <td className="py-2 text-right tabular-nums">{v.total_tokens.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          {/* Recent events */}
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold">Recent run events</h2>
            <div className="max-h-80 overflow-y-auto scroll-thin">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="pb-2 font-medium">Run</th>
                    <th className="pb-2 font-medium">Event</th>
                    <th className="pb-2 font-medium">Details</th>
                    <th className="pb-2 text-right font-medium">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="py-1.5 font-mono">{e.run_id.slice(0, 8)}</td>
                      <td className="py-1.5">
                        <Badge tone={e.event === "run.end" ? "primary" : "default"}>{e.event}</Badge>
                      </td>
                      <td className="max-w-[380px] truncate py-1.5 text-muted-foreground">
                        {JSON.stringify(e.data).slice(0, 120)}
                      </td>
                      <td className="py-1.5 text-right text-muted-foreground">
                        {new Date(e.ts).toLocaleTimeString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
