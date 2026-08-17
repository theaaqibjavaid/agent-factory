// Agent editor + run console (design.md §5). Edit configuration-as-data,
// preview the rendered prompt/manifest, and kick off live runs over SSE.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  Hammer,
  Play,
  RotateCcw,
  Save,
  Sparkles,
} from "lucide-react";
import { api } from "../lib/api";
import type { Agent, AgentRender, Run, ToolEntry } from "../lib/types";
import { RANKS } from "../lib/types";
import { cn, formatUsd } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { RunConsole, RunStatusBadge } from "../components/run-console";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState, Field, Input, Select, Skeleton, Switch, Tabs, Textarea } from "../components/ui";

const SAFETY_TONE = { safe: "success", modified: "warning", destructive: "destructive" } as const;

export function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const { workspace } = useWorkspace();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [render, setRender] = useState<AgentRender | null>(null);
  const [toolCatalog, setToolCatalog] = useState<ToolEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState("editor");
  const [run, setRun] = useState<Run | null>(null);
  const [task, setTask] = useState("");
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const runKey = useRef(0);

  const load = useCallback(async () => {
    if (!workspace || !agentId) return;
    try {
      const [a, r, tc] = await Promise.all([
        api.get<Agent>(`/api/v1/workspaces/${workspace.id}/agents/${agentId}`),
        api.get<AgentRender>(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/render`),
        api.get<{ tools: ToolEntry[] }>(`/api/v1/workspaces/${workspace.id}/tools`),
      ]);
      setAgent(a);
      setRender(r);
      setToolCatalog(tc.tools);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agent");
    }
  }, [workspace?.id, agentId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const patch = <K extends keyof Agent>(key: K, value: Agent[K]) => {
    setAgent((prev) => (prev ? { ...prev, [key]: value } : prev));
    setDirty(true);
  };

  const save = async () => {
    if (!workspace || !agent) return;
    setSaving(true);
    try {
      const updated = await api.patch<Agent>(`/api/v1/workspaces/${workspace.id}/agents/${agent.id}`, {
        name: agent.name,
        rank: agent.rank,
        role_description: agent.role_description,
        system_instructions: agent.system_instructions,
        model_preferences: agent.model_preferences,
        tools: agent.tools,
        skills: agent.skills,
        mcp_servers: agent.mcp_servers,
        temperature: agent.temperature,
        max_budget_usd_per_day: agent.max_budget_usd_per_day,
        hitl_mode: agent.hitl_mode,
        max_iterations: agent.max_iterations,
      });
      setAgent(updated);
      const r = await api.get<AgentRender>(`/api/v1/workspaces/${workspace.id}/agents/${agent.id}/render`);
      setRender(r);
      setDirty(false);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const launch = async () => {
    if (!workspace || !agent || !task.trim()) return;
    setLaunching(true);
    setLaunchError(null);
    try {
      const resp = await api.post<{ run_id: string; status: string; proposal_id?: string }>(
        `/api/v1/workspaces/${workspace.id}/agents/${agent.id}/runs`,
        { task: task.trim() },
      );
      // Fetch the full run record, then stream its events.
      const runRecord = await api.get<Run>(`/api/v1/workspaces/${workspace.id}/runs/${resp.run_id}`);
      runKey.current += 1;
      setRun({ ...runRecord, status: resp.status as Run["status"] });
      setTab("console");
      if (resp.proposal_id) {
        setLaunchError("Agent is gated — this run was queued for approval.");
      }
    } catch (err) {
      setLaunchError(err instanceof Error ? err.message : "Launch failed");
    } finally {
      setLaunching(false);
    }
  };

  const retry = async () => {
    if (!workspace || !run) return;
    try {
      const resp = await api.post<{ run_id: string; status: string }>(
        `/api/v1/workspaces/${workspace.id}/runs/${run.id}/retry`,
      );
      runKey.current += 1;
      setRun({ ...run, status: resp.status as Run["status"] });
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Retry failed");
    }
  };

  if (error && !agent) {
    return (
      <div className="p-8">
        <EmptyState title="Agent not found" description={error} />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const toggleTool = (name: string) => {
    const tools = agent.tools.includes(name)
      ? agent.tools.filter((t) => t !== name)
      : [...agent.tools, name];
    patch("tools", tools);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate("/app/agents")} aria-label="Back to agents">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
              {agent.name}
              {dirty && <Badge tone="warning">unsaved</Badge>}
            </h1>
            <p className="text-sm text-muted-foreground">
              {agent.rank} · {agent.hitl_mode === "gate" ? "HITL gate" : "Auto"} ·{" "}
              {formatUsd(agent.max_budget_usd_per_day)}/day budget
            </p>
          </div>
        </div>
        <Button onClick={save} loading={saving} disabled={!dirty}>
          <Save className="h-4 w-4" /> Save changes
        </Button>
      </div>

      <Tabs
        value={tab}
        onValueChange={setTab}
        tabs={[
          { value: "editor", label: "Editor" },
          { value: "render", label: "Rendered config" },
          { value: "console", label: "Run console" },
        ]}
      />

      {tab === "editor" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Identity & behavior</CardTitle>
              <CardDescription>Who this agent is and how it thinks.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Name">
                <Input value={agent.name} onChange={(e) => patch("name", e.target.value)} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Rank">
                  <Select value={agent.rank} onChange={(e) => patch("rank", e.target.value)}>
                    {RANKS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Temperature">
                  <Input
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={agent.temperature}
                    onChange={(e) => patch("temperature", Number(e.target.value))}
                  />
                </Field>
              </div>
              <Field label="Role description">
                <Input
                  value={agent.role_description ?? ""}
                  onChange={(e) => patch("role_description", e.target.value || null)}
                  placeholder="What does this agent do?"
                />
              </Field>
              <Field label="System instructions">
                <Textarea
                  rows={6}
                  value={agent.system_instructions ?? ""}
                  onChange={(e) => patch("system_instructions", e.target.value || null)}
                  placeholder="Extra instructions for the system prompt…"
                />
              </Field>
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Tools</CardTitle>
                <CardDescription>
                  Pick from the built-in catalog ({agent.tools.length} selected).
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid max-h-72 grid-cols-1 gap-1.5 overflow-y-auto scroll-thin sm:grid-cols-2">
                  {toolCatalog.map((tool) => {
                    const on = agent.tools.includes(tool.name);
                    return (
                      <button
                        key={`${tool.source}-${tool.name}`}
                        type="button"
                        onClick={() => toggleTool(tool.name)}
                        className={cn(
                          "flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-left transition-colors",
                          on
                            ? "border-primary/50 bg-primary/10"
                            : "border-border hover:border-primary/30",
                        )}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-mono text-xs font-medium">{tool.name}</span>
                          <span className="block truncate text-[11px] text-muted-foreground">
                            {tool.category} · {tool.source}
                          </span>
                        </span>
                        <Badge tone={SAFETY_TONE[tool.safety_level]}>{tool.safety_level}</Badge>
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Guards</CardTitle>
                <CardDescription>Budget and human-in-the-loop policy.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between rounded-md border border-border p-3">
                  <div>
                    <p className="text-sm font-medium">Human-in-the-loop gate</p>
                    <p className="text-xs text-muted-foreground">
                      {agent.hitl_mode === "gate"
                        ? "Runs queue for approval before executing."
                        : "Runs execute automatically (destructive tools stay blocked)."}
                    </p>
                  </div>
                  <Switch
                    checked={agent.hitl_mode === "gate"}
                    onCheckedChange={(v) => patch("hitl_mode", v ? "gate" : "auto")}
                    label="Human-in-the-loop gate"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Daily budget (USD)">
                    <Input
                      type="number"
                      min={0}
                      step={0.5}
                      value={agent.max_budget_usd_per_day}
                      onChange={(e) => patch("max_budget_usd_per_day", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Max iterations">
                    <Input
                      type="number"
                      min={1}
                      max={200}
                      value={agent.max_iterations}
                      onChange={(e) => patch("max_iterations", Number(e.target.value))}
                    />
                  </Field>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {tab === "render" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" /> System prompt
              </CardTitle>
              <CardDescription>The exact prompt sent to the model at run time.</CardDescription>
            </CardHeader>
            <CardContent>
              <pre className="scroll-thin max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-background/70 p-4 font-mono text-xs leading-relaxed">
                {render?.system_prompt ?? "Loading…"}
              </pre>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Hammer className="h-4 w-4 text-primary" /> Tool manifest
              </CardTitle>
              <CardDescription>
                {render?.tools.length ?? 0} tools with safety and cost metadata.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="scroll-thin max-h-[32rem] space-y-2 overflow-y-auto pr-1">
                {render?.tools.map((tool) => (
                  <div key={tool.name} className="rounded-md border border-border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-mono text-xs font-semibold">{tool.name}</p>
                      <Badge tone={SAFETY_TONE[tool.safety]}>{tool.safety}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{tool.description}</p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {tool.category} · {formatUsd(tool.cost_per_call_usd)}/call
                    </p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {tab === "console" && (
        <div className="grid gap-6 lg:grid-cols-5">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Launch a run</CardTitle>
              <CardDescription>
                {agent.hitl_mode === "gate"
                  ? "Gated — creates a proposal for approval first."
                  : "Executes immediately with the saved configuration."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea
                rows={5}
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="e.g. Research the latest MCP ecosystem news and write a 3-point brief."
              />
              {launchError && (
                <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
                  {launchError}
                </p>
              )}
              <Button className="w-full" onClick={launch} loading={launching} disabled={!task.trim()}>
                <Play className="h-4 w-4" /> Launch run
              </Button>
              {run && (
                <div className="space-y-2 rounded-md border border-border p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">Run {run.id.slice(0, 8)}…</p>
                    <RunStatusBadge status={run.status} />
                  </div>
                  {run.status === "failed" && (
                    <Button size="sm" variant="secondary" className="w-full" onClick={retry}>
                      <RotateCcw className="h-3.5 w-3.5" /> Retry
                    </Button>
                  )}
                  {run.status === "completed" && run.result && (
                    <pre className="scroll-thin max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-background/70 p-2 font-mono text-[11px] leading-relaxed">
                      {run.result}
                    </pre>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
          <Card className="lg:col-span-3">
            <CardHeader className="pb-2">
              <CardTitle>Event stream</CardTitle>
            </CardHeader>
            <CardContent>
              {run ? (
                <RunConsole key={`${run.id}-${runKey.current}`} run={run} compact />
              ) : (
                <EmptyState
                  icon={<Play className="h-6 w-6" />}
                  title="No run yet"
                  description="Enter a task and launch a run to see the live event stream."
                />
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
