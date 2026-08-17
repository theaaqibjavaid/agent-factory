// Run Console — list workspace runs, filter by agent/status, and inspect a
// selected run's live SSE stream (design.md §6).
import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Activity, RotateCcw } from "lucide-react";
import { api } from "../lib/api";
import type { Agent, Run } from "../lib/types";
import { cn, formatDuration, formatUsd, timeAgo } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { RunConsole, RunStatusBadge } from "../components/run-console";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState, Select, Skeleton } from "../components/ui";

const STATUSES = ["", "pending", "pending_approval", "running", "completed", "failed", "cancelled"] as const;

export function RunsPage() {
  const { workspace } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [selected, setSelected] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  const agentFilter = params.get("agent") ?? "";
  const statusFilter = params.get("status") ?? "";
  const selectedId = params.get("run") ?? null;

  const load = useCallback(async () => {
    if (!workspace) return;
    setError(null);
    try {
      const qs = new URLSearchParams({ limit: "100" });
      if (agentFilter) qs.set("agent", agentFilter);
      if (statusFilter) qs.set("status", statusFilter);
      const [runsData, agentsData] = await Promise.all([
        api.get<{ runs: Run[] }>(`/api/v1/workspaces/${workspace.id}/runs?${qs}`),
        api.get<{ agents: Agent[] }>(`/api/v1/workspaces/${workspace.id}/agents`),
      ]);
      setRuns(runsData.runs);
      setAgents(agentsData.agents);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runs");
    }
  }, [workspace?.id, agentFilter, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  // Keep the selected run in sync with ?run=.
  useEffect(() => {
    if (!selectedId || !workspace) return;
    api
      .get<Run>(`/api/v1/workspaces/${workspace.id}/runs/${selectedId}`)
      .then(setSelected)
      .catch(() => setSelected(null));
  }, [selectedId, workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectRun = (run: Run) => {
    setSelected(run);
    setParams({ ...Object.fromEntries(params.entries()), run: run.id });
  };

  const retry = async (run: Run) => {
    if (!workspace) return;
    try {
      const resp = await api.post<{ run_id: string; status: string }>(
        `/api/v1/workspaces/${workspace.id}/runs/${run.id}/retry`,
      );
      const updated = { ...run, status: resp.status as Run["status"] };
      setSelected(updated);
      setRuns((prev) => prev?.map((r) => (r.id === run.id ? updated : r)) ?? prev);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Retry failed");
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Run Console</h1>
        <p className="text-sm text-muted-foreground">
          Every run is a streamed, verifiable, budgeted execution.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Select
          className="w-48"
          value={agentFilter}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            if (e.target.value) next.set("agent", e.target.value);
            else next.delete("agent");
            setParams(next);
          }}
        >
          <option value="">All agents</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        <Select
          className="w-44"
          value={statusFilter}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            if (e.target.value) next.set("status", e.target.value);
            else next.delete("status");
            setParams(next);
          }}
        >
          {STATUSES.map((s) => (
            <option key={s || "all"} value={s}>
              {s ? s.replace("_", " ") : "All statuses"}
            </option>
          ))}
        </Select>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* List */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle>Runs</CardTitle>
          </CardHeader>
          <CardContent>
            {!runs && !error && <Skeleton className="h-64" />}
            {error && !runs && <EmptyState title="Couldn't load runs" description={error} />}
            {runs && runs.length === 0 && (
              <EmptyState
                icon={<Activity className="h-6 w-6" />}
                title="No runs match"
                description="Adjust the filters, or launch a run from an agent's page."
              />
            )}
            {runs && runs.length > 0 && (
              <div className="max-h-[36rem] space-y-1 overflow-y-auto scroll-thin pr-1">
                {runs.map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => selectRun(run)}
                    className={cn(
                      "w-full rounded-md border px-3 py-2.5 text-left transition-colors",
                      selected?.id === run.id
                        ? "border-primary/50 bg-primary/10"
                        : "border-border hover:border-primary/30",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">{run.task}</p>
                      <RunStatusBadge status={run.status} />
                    </div>
                    <p className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{timeAgo(run.created_at)}</span>
                      {run.stats && (
                        <>
                          <span className="tabular-nums">· {formatDuration(run.stats.duration_seconds)}</span>
                          <span className="tabular-nums">· {formatUsd(run.stats.total_cost_usd)}</span>
                        </>
                      )}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Detail */}
        <Card className="lg:col-span-3">
          <CardHeader className="pb-2">
            {selected ? (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <CardTitle className="truncate">{selected.task}</CardTitle>
                  <CardDescription>
                    {selected.id} · retries {selected.retries}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  {selected.status === "failed" && (
                    <Button size="sm" variant="secondary" onClick={() => retry(selected)}>
                      <RotateCcw className="h-3.5 w-3.5" /> Retry
                    </Button>
                  )}
                  <RunStatusBadge status={selected.status} />
                </div>
              </div>
            ) : (
              <CardTitle>Run detail</CardTitle>
            )}
          </CardHeader>
          <CardContent>
            {selected ? (
              <RunConsole key={selected.id} run={selected} compact />
            ) : (
              <EmptyState
                icon={<Activity className="h-6 w-6" />}
                title="Select a run"
                description="Pick a run from the list to stream its events."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
