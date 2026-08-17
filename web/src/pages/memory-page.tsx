// Memory — per-agent facts, history, and portable bundles (Phase 2.4).
// Export/import round-trips a versioned JSON bundle; clear wipes history.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Database, Download, FileUp, Plus, Trash2, XCircle } from "lucide-react";
import { api } from "../lib/api";
import type { Agent, MemoryBundle, MemoryView } from "../lib/types";
import { cn, formatDateTime } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Dialog, EmptyState, Field, Input, Select, Skeleton } from "../components/ui";

export function MemoryPage() {
  const { workspace } = useWorkspace();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState<string>("");
  const [view, setView] = useState<MemoryView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [factKey, setFactKey] = useState("");
  const [factValue, setFactValue] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!workspace) return;
    try {
      const data = await api.get<{ agents: Agent[] }>(`/api/v1/workspaces/${workspace.id}/agents`);
      setAgents(data.agents);
      setAgentId((prev) => (prev && data.agents.some((a) => a.id === prev) ? prev : data.agents[0]?.id ?? ""));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!workspace || !agentId) {
      setView(null);
      return;
    }
    let cancelled = false;
    setBusy(true);
    api
      .get<MemoryView>(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory`)
      .then((v) => {
        if (!cancelled) setView(v);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load memory");
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspace?.id, agentId]); // eslint-disable-line react-hooks/exhaustive-deps

  const addFact = async () => {
    if (!workspace || !agentId || !factKey.trim()) return;
    try {
      let value: unknown = factValue;
      try {
        value = JSON.parse(factValue);
      } catch {
        /* keep as string */
      }
      await api.post(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory/facts`, {
        key: factKey.trim(),
        value,
      });
      setFactKey("");
      setFactValue("");
      const v = await api.get<MemoryView>(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory`);
      setView(v);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Failed to save fact");
    }
  };

  const deleteFact = async (key: string) => {
    if (!workspace || !agentId) return;
    try {
      await api.delete(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory/facts/${encodeURIComponent(key)}`);
      setView((prev) => (prev ? { ...prev, facts: omitKey(prev.facts, key) } : prev));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Failed to delete fact");
    }
  };

  const clearHistory = async () => {
    if (!workspace || !agentId) return;
    if (!window.confirm("Clear this agent's conversation history? Facts are kept.")) return;
    try {
      await api.post(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory/clear`, { confirm: "DELETE" });
      const v = await api.get<MemoryView>(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory`);
      setView(v);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Clear failed");
    }
  };

  const exportMemory = async () => {
    if (!workspace || !agentId) return;
    try {
      const bundle = await api.get<MemoryBundle>(
        `/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory/export`,
      );
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `agentfactory-memory-${agentId.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Export failed");
    }
  };

  const importFile = async (file: File, mode: "merge" | "replace") => {
    if (!workspace || !agentId) return;
    try {
      const bundle = JSON.parse(await file.text()) as MemoryBundle;
      await api.post(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory/import`, {
        bundle,
        mode,
      });
      setImportOpen(false);
      const v = await api.get<MemoryView>(`/api/v1/workspaces/${workspace.id}/agents/${agentId}/memory`);
      setView(v);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Import failed");
    }
  };

  const facts = view?.facts ?? {};
  const history = view?.history ?? [];

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Memory</h1>
          <p className="text-sm text-muted-foreground">
            Scoped per agent · export/import portable bundles.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={exportMemory} disabled={!agentId}>
            <Download className="h-4 w-4" /> Export
          </Button>
          <Button variant="secondary" onClick={() => setImportOpen(true)} disabled={!agentId}>
            <FileUp className="h-4 w-4" /> Import
          </Button>
          <Button variant="destructive" onClick={clearHistory} disabled={!agentId}>
            <XCircle className="h-4 w-4" /> Clear history
          </Button>
        </div>
      </div>

      <div className="max-w-xs">
        <Select value={agentId} onChange={(e) => setAgentId(e.target.value)}>
          {agents.length === 0 && <option value="">No agents</option>}
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
      </div>

      {error && <EmptyState title="Something went wrong" description={error} />}

      {!agentId && !error && (
        <EmptyState
          icon={<Database className="h-6 w-6" />}
          title="No agent selected"
          description="Create an agent first, then manage its memory here."
        />
      )}

      {agentId && (
        <div className="grid gap-6 lg:grid-cols-5">
          {/* Facts */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Facts</CardTitle>
              <CardDescription>
                {Object.keys(facts).length} stored · used across runs.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Input
                  value={factKey}
                  onChange={(e) => setFactKey(e.target.value)}
                  placeholder="fact key"
                  className="flex-1"
                />
                <Input
                  value={factValue}
                  onChange={(e) => setFactValue(e.target.value)}
                  placeholder="value (JSON ok)"
                  className="flex-1"
                />
                <Button size="icon" onClick={addFact} disabled={!factKey.trim()} aria-label="Save fact">
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              <div className="scroll-thin max-h-80 space-y-1.5 overflow-y-auto pr-1">
                {Object.keys(facts).length === 0 && (
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    No facts yet — save one above.
                  </p>
                )}
                {Object.entries(facts).map(([key, value]) => (
                  <div key={key} className="group flex items-start justify-between gap-2 rounded-md border border-border p-2.5">
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs font-medium">{key}</p>
                      <p className="truncate font-mono text-[11px] text-muted-foreground">
                        {typeof value === "string" ? value : JSON.stringify(value)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => deleteFact(key)}
                      className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-destructive group-hover:opacity-100"
                      aria-label={`Delete fact ${key}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* History */}
          <Card className="lg:col-span-3">
            <CardHeader>
              <CardTitle>Conversation history</CardTitle>
              <CardDescription>
                {busy ? "Loading…" : `${view?.stats.message_count ?? 0} messages`}
                {view?.stats.first_seen ? ` · first ${formatDateTime(view.stats.first_seen)}` : ""}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {busy && <Skeleton className="h-64" />}
              {!busy && history.length === 0 && (
                <EmptyState
                  icon={<Database className="h-6 w-6" />}
                  title="Empty history"
                  description="Run this agent to start accumulating conversation memory."
                />
              )}
              {!busy && history.length > 0 && (
                <div className="scroll-thin max-h-[30rem] space-y-2 overflow-y-auto pr-1">
                  {history.map((msg, i) => (
                    <div
                      key={i}
                      className={cn(
                        "rounded-md border p-3",
                        msg.role === "user" ? "border-primary/30 bg-primary/5" : "border-border bg-background/60",
                      )}
                    >
                      <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                        {msg.role}
                      </p>
                      <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed">
                        {typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content)}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {importOpen && (
        <Dialog open onClose={() => setImportOpen(false)} title="Import memory bundle">
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Pick an exported bundle (schema v1). Choose merge to add to existing
              memory, or replace to wipe this agent's memory first.
            </p>
            <input
              ref={fileRef}
              type="file"
              accept="application/json,.json"
              className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-2 file:text-sm file:font-medium file:text-foreground"
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setImportOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  const file = fileRef.current?.files?.[0];
                  if (file) importFile(file, "merge");
                }}
              >
                Merge import
              </Button>
              <Button
                onClick={() => {
                  const file = fileRef.current?.files?.[0];
                  if (file) importFile(file, "replace");
                }}
              >
                Replace
              </Button>
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function omitKey(obj: Record<string, unknown>, key: string): Record<string, unknown> {
  const next = { ...obj };
  delete next[key];
  return next;
}
