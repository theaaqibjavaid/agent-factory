// Agents — list, create, and jump into the editor (design.md §5).
import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Bot, Plus, Settings2, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { Agent } from "../lib/types";
import { RANKS } from "../lib/types";
import { cn } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, Dialog, EmptyState, Field, Input, Select, Skeleton, Switch, Textarea } from "../components/ui";

export function AgentsPage() {
  const { workspace } = useWorkspace();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (!workspace) return;
    try {
      const data = await api.get<{ agents: Agent[] }>(`/api/v1/workspaces/${workspace.id}/agents`);
      setAgents(data.agents);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  // ?new=1 opens the create dialog (dashboard quick action).
  useEffect(() => {
    if (params.get("new") === "1") {
      setCreating(true);
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  const remove = async (agent: Agent) => {
    if (!workspace) return;
    if (!window.confirm(`Delete "${agent.name}"? Runs for this agent will be removed.`)) return;
    try {
      await api.delete(`/api/v1/workspaces/${workspace.id}/agents/${agent.id}`);
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
          <p className="text-sm text-muted-foreground">
            Configuration-as-data: tools, skills, models, budgets, gates.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> New agent
        </Button>
      </div>

      {error && !agents && (
        <EmptyState title="Couldn't load agents" description={error} />
      )}

      {!agents && !error && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}

      {agents && agents.length === 0 && (
        <EmptyState
          icon={<Bot className="h-6 w-6" />}
          title="No agents yet"
          description="Create your first agent — pick a rank, attach tools and model preferences, then run it."
          action={
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> Create agent
            </Button>
          }
        />
      )}

      {agents && agents.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <Card key={agent.id} className="group">
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/15 text-primary">
                      <Bot className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-semibold leading-tight">{agent.name}</p>
                      <p className="text-xs text-muted-foreground">{agent.rank}</p>
                    </div>
                  </div>
                  <Badge tone={agent.hitl_mode === "gate" ? "warning" : "success"}>
                    {agent.hitl_mode === "gate" ? "Gate" : "Auto"}
                  </Badge>
                </div>
                <p className="mt-3 line-clamp-2 min-h-8 text-sm text-muted-foreground">
                  {agent.role_description || "No role description set."}
                </p>
                <div className="mt-3 flex items-center gap-3 border-t border-border pt-3 text-xs text-muted-foreground">
                  <span className="tabular-nums">{agent.tools.length} tools</span>
                  <span className="tabular-nums">{agent.model_preferences.length} models</span>
                  <span className="tabular-nums">${agent.max_budget_usd_per_day}/day</span>
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <Button size="sm" variant="secondary" className="flex-1" onClick={() => navigate(`/app/agents/${agent.id}`)}>
                    <Settings2 className="h-3.5 w-3.5" /> Open
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => remove(agent)} aria-label={`Delete ${agent.name}`}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {creating && workspace && (
        <CreateAgentDialog
          workspaceId={workspace.id}
          onClose={() => setCreating(false)}
          onCreated={(agent) => {
            setCreating(false);
            navigate(`/app/agents/${agent.id}`);
          }}
        />
      )}
    </div>
  );
}

function CreateAgentDialog({
  workspaceId,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  onClose: () => void;
  onCreated: (agent: Agent) => void;
}) {
  const [name, setName] = useState("");
  const [rank, setRank] = useState("Junior");
  const [role, setRole] = useState("");
  const [instructions, setInstructions] = useState("");
  const [hitl, setHitl] = useState(false);
  const [budget, setBudget] = useState(5);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const agent = await api.post<Agent>(`/api/v1/workspaces/${workspaceId}/agents`, {
        name,
        rank,
        role_description: role || null,
        system_instructions: instructions || null,
        tools: ["web_search", "web_fetch", "read_text_file", "list_directory_contents", "git_check_status"],
        model_preferences: [],
        temperature: 0.2,
        max_budget_usd_per_day: budget,
        hitl_mode: hitl ? "gate" : "auto",
        max_iterations: 20,
      });
      onCreated(agent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} title="New agent">
      <div className="space-y-4">
        <Field label="Name" hint="A memorable name for the assembly line.">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Research Assistant"
            autoFocus
          />
        </Field>
        <Field label="Rank" hint="Determines the default system-prompt personality.">
          <Select value={rank} onChange={(e) => setRank(e.target.value)}>
            {RANKS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Role description" hint="One line describing what this agent does.">
          <Input
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder="e.g. Deep-dives research topics and writes briefs"
          />
        </Field>
        <Field label="System instructions (optional)" hint="Extra instructions appended to the rendered system prompt.">
          <Textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={4}
            placeholder="e.g. Always cite sources; never modify files without approval."
          />
        </Field>
        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <p className="text-sm font-medium">Human-in-the-loop gate</p>
            <p className="text-xs text-muted-foreground">
              Queue every run for approval instead of executing immediately.
            </p>
          </div>
          <Switch checked={hitl} onCheckedChange={setHitl} label="Human-in-the-loop gate" />
        </div>
        <Field label="Daily budget (USD)">
          <Input
            type="number"
            min={0}
            step={0.5}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </Field>
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={saving} disabled={!name.trim()} onClick={save} className={cn(!name.trim() && "opacity-50")}>
            Create agent
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
