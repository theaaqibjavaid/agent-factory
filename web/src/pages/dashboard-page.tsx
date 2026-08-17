// Dashboard — workspace overview: stats, recent runs, pending approvals,
// and quick actions (design.md §5).
import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Bot,
  CheckCheck,
  Clock,
  Cpu,
  DollarSign,
  Plus,
} from "lucide-react";
import { api } from "../lib/api";
import type { Agent, Proposal, Run } from "../lib/types";
import { formatDuration, formatUsd, timeAgo } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { RunStatusBadge } from "../components/run-console";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState, Skeleton } from "../components/ui";

interface DashboardData {
  agents: Agent[];
  runs: Run[];
  proposals: Proposal[];
}

export function DashboardPage() {
  const { workspace } = useWorkspace();
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    setError(null);
    try {
      const [agents, runs, proposals] = await Promise.all([
        api.get<{ agents: Agent[] }>(`/api/v1/workspaces/${workspace.id}/agents`),
        api.get<{ runs: Run[] }>(`/api/v1/workspaces/${workspace.id}/runs?limit=8`),
        api.get<{ proposals: Proposal[] }>(`/api/v1/workspaces/${workspace.id}/proposals?status=pending`),
      ]);
      setData({ agents: agents.agents, runs: runs.runs, proposals: proposals.proposals });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  if (!workspace) {
    return (
      <div className="p-8">
        <EmptyState
          title="No workspace"
          description="You don't belong to any workspace yet."
        />
      </div>
    );
  }

  if (loading) return <DashboardSkeleton />;

  if (error || !data) {
    return (
      <div className="p-8">
        <EmptyState title="Couldn't load the dashboard" description={error ?? undefined} />
      </div>
    );
  }

  const totalCost = data.runs.reduce((sum, r) => sum + (r.stats?.total_cost_usd ?? 0), 0);
  const pendingCount = data.proposals.length;

  const stats = [
    {
      label: "Agents",
      value: String(data.agents.length),
      icon: Bot,
      tone: "text-primary",
      to: "/app/agents",
    },
    {
      label: "Runs (recent)",
      value: String(data.runs.length),
      icon: Activity,
      tone: "text-muted-foreground",
      to: "/app/runs",
    },
    {
      label: "Pending approvals",
      value: String(pendingCount),
      icon: CheckCheck,
      tone: pendingCount ? "text-warning" : "text-muted-foreground",
      to: "/app/approvals",
    },
    {
      label: "Spend (30d)",
      value: formatUsd(totalCost),
      icon: DollarSign,
      tone: "text-muted-foreground",
      to: "/app/settings",
    },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            {workspace.name} — factory overview
          </p>
        </div>
        <Button onClick={() => navigate("/app/agents?new=1")}>
          <Plus className="h-4 w-4" /> New agent
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map(({ label, value, icon: Icon, tone, to }) => (
          <Link key={label} to={to} className="group">
            <Card className="transition-colors group-hover:border-primary/40">
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">{label}</p>
                  <Icon className={`h-4 w-4 ${tone}`} />
                </div>
                <p className="mt-2 text-2xl font-bold tabular-nums tracking-tight">{value}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Recent runs */}
        <Card className="lg:col-span-3">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Recent runs</CardTitle>
              <CardDescription>Latest agent executions</CardDescription>
            </div>
            <Link to="/app/runs" className="text-sm text-primary hover:underline">
              View all <ArrowRight className="ml-0.5 inline h-3.5 w-3.5" />
            </Link>
          </CardHeader>
          <CardContent>
            {data.runs.length === 0 ? (
              <EmptyState
                icon={<Activity className="h-6 w-6" />}
                title="No runs yet"
                description="Create an agent and kick off its first run from the Agents page."
              />
            ) : (
              <div className="divide-y divide-border">
                {data.runs.map((run) => (
                  <Link
                    key={run.id}
                    to={`/app/runs?run=${run.id}`}
                    className="flex items-center gap-3 py-3 transition-colors hover:bg-muted/40"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{run.task}</p>
                      <p className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {timeAgo(run.created_at)}
                        {run.stats && (
                          <>
                            <span className="tabular-nums">· {formatDuration(run.stats.duration_seconds)}</span>
                            <span className="tabular-nums">· {formatUsd(run.stats.total_cost_usd)}</span>
                          </>
                        )}
                      </p>
                    </div>
                    <RunStatusBadge status={run.status} />
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pending approvals */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Approvals</CardTitle>
              <CardDescription>Human-in-the-loop inbox</CardDescription>
            </div>
            {pendingCount > 0 && <Badge tone="warning">{pendingCount} waiting</Badge>}
          </CardHeader>
          <CardContent>
            {data.proposals.length === 0 ? (
              <EmptyState
                icon={<CheckCheck className="h-6 w-6" />}
                title="All clear"
                description="No proposals waiting for review. Gate-mode agents will queue their plans here."
              />
            ) : (
              <div className="space-y-2">
                {data.proposals.slice(0, 4).map((p) => (
                  <Link
                    key={p.id}
                    to={`/app/approvals?proposal=${p.id}`}
                    className="block rounded-md border border-border p-3 transition-colors hover:border-primary/40"
                  >
                    <p className="truncate text-sm font-medium">{p.title}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{timeAgo(p.created_at)}</p>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Agents strip */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Your agents</CardTitle>
            <CardDescription>
              <span className="inline-flex items-center gap-1">
                <Cpu className="h-3 w-3" /> Agents run with config snapshots, budgets, and verification
              </span>
            </CardDescription>
          </div>
          <Link to="/app/agents" className="text-sm text-primary hover:underline">
            Manage <ArrowRight className="ml-0.5 inline h-3.5 w-3.5" />
          </Link>
        </CardHeader>
        <CardContent>
          {data.agents.length === 0 ? (
            <EmptyState
              icon={<Bot className="h-6 w-6" />}
              title="No agents in this workspace"
              description="Spin up your first agent — pick a rank, tools, and model preferences."
              action={
                <Button size="sm" onClick={() => navigate("/app/agents?new=1")}>
                  <Plus className="h-4 w-4" /> Create agent
                </Button>
              }
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.agents.map((agent) => (
                <Link
                  key={agent.id}
                  to={`/app/agents/${agent.id}`}
                  className="rounded-md border border-border p-4 transition-colors hover:border-primary/40"
                >
                  <div className="flex items-center justify-between">
                    <p className="font-semibold">{agent.name}</p>
                    <Badge tone={agent.hitl_mode === "gate" ? "warning" : "success"}>
                      {agent.hitl_mode === "gate" ? "HITL gate" : "Auto"}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {agent.rank} · {agent.tools.length} tools · {agent.model_preferences.length} models
                  </p>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-5">
        <Skeleton className="h-72 lg:col-span-3" />
        <Skeleton className="h-72 lg:col-span-2" />
      </div>
    </div>
  );
}
