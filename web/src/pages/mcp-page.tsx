// MCP servers — register stdio servers, test connections with the hardened
// client, and enable per server (Phase 4.3).
import React, { useCallback, useEffect, useState } from "react";
import { Cable, Loader2, Plus, Server, Trash2, Zap } from "lucide-react";
import { api } from "../lib/api";
import type { MCPServer, MCPTestResult } from "../lib/types";
import { cn } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, Dialog, EmptyState, Field, Input, Select, Skeleton, Textarea } from "../components/ui";

export function McpPage() {
  const { workspace } = useWorkspace();
  const [servers, setServers] = useState<MCPServer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (!workspace) return;
    try {
      const data = await api.get<{ servers: MCPServer[] }>(`/api/v1/workspaces/${workspace.id}/mcp`);
      setServers(data.servers);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load servers");
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (server: MCPServer) => {
    if (!workspace) return;
    if (!window.confirm(`Delete MCP server "${server.name}"?`)) return;
    try {
      await api.delete(`/api/v1/workspaces/${workspace.id}/mcp/${server.id}`);
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const toggleEnabled = async (server: MCPServer) => {
    if (!workspace) return;
    try {
      await api.patch(`/api/v1/workspaces/${workspace.id}/mcp/${server.id}`, {
        enabled: !server.enabled,
      });
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Update failed");
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">MCP Servers</h1>
          <p className="text-sm text-muted-foreground">
            Model Context Protocol servers — test connections here, then attach
            them to agents. Commands are allowlisted; env vars pass through only
            when explicitly permitted.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> Add server
        </Button>
      </div>

      {error && !servers && <EmptyState title="Couldn't load servers" description={error} />}
      {!servers && !error && <Skeleton className="h-48" />}

      {servers && servers.length === 0 && (
        <EmptyState
          icon={<Cable className="h-6 w-6" />}
          title="No MCP servers"
          description="Add a stdio server (npx/uvx/python…), test the connection, then attach it to an agent."
          action={<Button size="sm" onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> Add server</Button>}
        />
      )}

      {servers && servers.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {servers.map((server) => (
            <Card key={server.id} className={cn(!server.enabled && "opacity-60")}>
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/15 text-primary">
                      <Server className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-semibold leading-tight">{server.name}</p>
                      <p className="font-mono text-xs text-muted-foreground">
                        {server.transport === "stdio" ? server.command : server.url}
                      </p>
                    </div>
                  </div>
                  <Badge tone="info">{server.transport}</Badge>
                </div>
                <p className="mt-3 truncate font-mono text-xs text-muted-foreground">
                  {server.args.join(" ")}
                </p>
                <div className="mt-3 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
                  <span>{server.timeout}s timeout</span>
                  {server.env_allow.length > 0 && <span>{server.env_allow.join(", ")}</span>}
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <Button
                    size="sm"
                    variant={server.enabled ? "secondary" : "outline"}
                    className="flex-1"
                    onClick={() => toggleEnabled(server)}
                  >
                    {server.enabled ? "Enabled" : "Disabled"}
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => remove(server)} aria-label={`Delete ${server.name}`}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {creating && workspace && (
        <CreateServerDialog
          workspaceId={workspace.id}
          onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); load(); }}
        />
      )}
    </div>
  );
}

function CreateServerDialog({
  workspaceId,
  onClose,
  onSaved,
}: {
  workspaceId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [transport, setTransport] = useState<"stdio" | "sse">("stdio");
  const [command, setCommand] = useState("npx");
  const [args, setArgs] = useState("");
  const [url, setUrl] = useState("");
  const [envAllow, setEnvAllow] = useState("");
  const [timeout, setTimeoutVal] = useState(10);
  const [test, setTest] = useState<MCPTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const testConnection = async () => {
    setTesting(true);
    setError(null);
    try {
      const result = await api.post<MCPTestResult>(`/api/v1/workspaces/${workspaceId}/mcp/test`, {
        name,
        transport,
        command: transport === "stdio" ? command : null,
        args: args.split(/\s+/).filter(Boolean),
        url: transport === "sse" ? url : null,
        env_allow: envAllow.split(",").map((s) => s.trim()).filter(Boolean),
        timeout,
      });
      setTest(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/api/v1/workspaces/${workspaceId}/mcp`, {
        name,
        transport,
        command: transport === "stdio" ? command : null,
        args: args.split(/\s+/).filter(Boolean),
        url: transport === "sse" ? url : null,
        env_allow: envAllow.split(",").map((s) => s.trim()).filter(Boolean),
        timeout,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} title="Add MCP server" wide>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. filesystem" autoFocus />
          </Field>
          <Field label="Transport">
            <Select value={transport} onChange={(e) => setTransport(e.target.value as "stdio" | "sse")}>
              <option value="stdio">stdio (spawn a process)</option>
              <option value="sse">SSE (remote URL)</option>
            </Select>
          </Field>
        </div>
        {transport === "stdio" ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Command" hint={`Allowlisted: npx, uvx, python, node, deno, bun`}>
                <Input value={command} onChange={(e) => setCommand(e.target.value)} />
              </Field>
              <Field label="Args" hint="Space-separated">
                <Input value={args} onChange={(e) => setArgs(e.target.value)} placeholder="-y @modelcontextprotocol/server-filesystem /tmp" />
              </Field>
            </div>
          </>
        ) : (
          <Field label="SSE URL">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://mcp.example.com/sse" />
          </Field>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Env allowlist" hint="Comma-separated env var names passed to the server.">
            <Input value={envAllow} onChange={(e) => setEnvAllow(e.target.value)} placeholder="GITHUB_TOKEN, OPENAI_API_KEY" />
          </Field>
          <Field label="Timeout (seconds)">
            <Input type="number" min={1} max={120} value={timeout} onChange={(e) => setTimeoutVal(Number(e.target.value))} />
          </Field>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={testConnection} loading={testing}>
            <Zap className="h-4 w-4" /> Test connection
          </Button>
          {test && (
            <div className={cn("text-sm", test.ok ? "text-success" : "text-destructive")}>
              {test.ok ? (
                <span className="flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5" /> Connected — {test.count} tool{test.count === 1 ? "" : "s"} discovered
                </span>
              ) : (
                <span>Connection failed: {test.error}</span>
              )}
            </div>
          )}
        </div>
        {test?.tools.length ? (
          <ul className="max-h-28 space-y-1 overflow-y-auto scroll-thin rounded-md border border-border p-2 text-xs">
            {test.tools.map((t) => (
              <li key={t.name} className="flex items-center justify-between">
                <span className="font-mono">{t.name}</span>
                <span className="text-muted-foreground">{t.description}</span>
              </li>
            ))}
          </ul>
        ) : null}

        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} loading={saving} disabled={!name.trim() || (transport === "stdio" ? !command.trim() : !url.trim())}>
            Save server
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
