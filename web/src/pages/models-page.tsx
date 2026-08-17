// Models — provider cards, key guidance, and live model connections with
// test-calls (Phase 4.4). Keys live in platform secrets; the DB stores only a
// reference (key_ref) to the env var name.
import React, { useCallback, useEffect, useState } from "react";
import { Cpu, KeyRound, Loader2, Plus, TestTube2, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { ModelConnection, TestCallResult } from "../lib/types";
import { cn } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Dialog, EmptyState, Field, Input, Select, Skeleton } from "../components/ui";

interface ProviderDef {
  id: string;
  name: string;
  envVar: string;
  models: string[];
  builtIn: boolean;
  defaultBaseUrl?: string;
}

const PROVIDERS: ProviderDef[] = [
  { id: "openai", name: "OpenAI", envVar: "OPENAI_API_KEY", models: ["gpt-4o", "gpt-4o-mini", "o3-mini"], builtIn: true },
  { id: "anthropic", name: "Anthropic", envVar: "ANTHROPIC_API_KEY", models: ["claude-sonnet-4-5", "claude-haiku-4-5"], builtIn: true },
  { id: "google", name: "Google", envVar: "GOOGLE_API_KEY", models: ["gemini-2.5-pro", "gemini-2.5-flash"], builtIn: true },
  { id: "groq", name: "Groq", envVar: "GROQ_API_KEY", models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"], builtIn: true },
  { id: "openrouter", name: "OpenRouter", envVar: "OPENROUTER_API_KEY", models: ["openai/gpt-4o", "anthropic/claude-sonnet-4-5"], builtIn: true, defaultBaseUrl: "https://openrouter.ai/api/v1" },
  { id: "ollama", name: "Ollama (local)", envVar: "— (local)", models: ["llama3.2", "qwen2.5"], builtIn: false, defaultBaseUrl: "http://localhost:11434/v1" },
];

export function ModelsPage() {
  const { workspace } = useWorkspace();
  const [connections, setConnections] = useState<ModelConnection[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestCallResult>>({});

  const load = useCallback(async () => {
    if (!workspace) return;
    try {
      const data = await api.get<{ connections: ModelConnection[] }>(`/api/v1/workspaces/${workspace.id}/models`);
      setConnections(data.connections);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load connections");
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const testCall = async (conn: ModelConnection) => {
    if (!workspace) return;
    setTesting(conn.id);
    try {
      const result = await api.post<TestCallResult>(`/api/v1/workspaces/${workspace.id}/models/${conn.id}/test-call`);
      setTestResults((prev) => ({ ...prev, [conn.id]: result }));
    } catch (err) {
      setTestResults((prev) => ({ ...prev, [conn.id]: { ok: false, error: err instanceof Error ? err.message : "Test failed" } }));
    } finally {
      setTesting(null);
    }
  };

  const remove = async (conn: ModelConnection) => {
    if (!workspace) return;
    if (!window.confirm(`Delete connection "${conn.model}"?`)) return;
    try {
      await api.delete(`/api/v1/workspaces/${workspace.id}/models/${conn.id}`);
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const toggleEnabled = async (conn: ModelConnection) => {
    if (!workspace) return;
    try {
      await api.patch(`/api/v1/workspaces/${workspace.id}/models/${conn.id}`, { enabled: !conn.enabled });
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Update failed");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Models</h1>
          <p className="text-sm text-muted-foreground">
            Connect providers once; every agent can use them. Agents pick models
            by name — connections resolve the endpoint and key at run time.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> Connect model
        </Button>
      </div>

      {/* Connections */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-primary" /> Connected models
          </CardTitle>
          <CardDescription>Keys are never stored — each connection references an env var in platform secrets.</CardDescription>
        </CardHeader>
        <CardContent>
          {error && <EmptyState title="Couldn't load connections" description={error} />}
          {!connections && !error && <Skeleton className="h-32" />}
          {connections && connections.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No connections yet — connect a model to use it in agents.
            </p>
          )}
          {connections && connections.length > 0 && (
            <div className="space-y-2">
              {connections.map((conn) => {
                const result = testResults[conn.id];
                return (
                  <div key={conn.id} className={cn("rounded-md border border-border p-3", !conn.enabled && "opacity-60")}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-mono text-sm font-semibold">{conn.model}</p>
                        <p className="text-xs text-muted-foreground">
                          {conn.provider}
                          {conn.base_url && <span className="ml-2 font-mono">{conn.base_url}</span>}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone={conn.key_configured ? "success" : "warning"}>
                          {conn.key_configured ? "key set" : "key missing"}
                        </Badge>
                        <Button size="sm" variant="secondary" onClick={() => testCall(conn)} loading={testing === conn.id}>
                          <TestTube2 className="h-3.5 w-3.5" /> Test
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => toggleEnabled(conn)}>
                          {conn.enabled ? "Enabled" : "Disabled"}
                        </Button>
                        <Button size="icon" variant="ghost" onClick={() => remove(conn)} aria-label={`Delete ${conn.model}`}>
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>
                    {result && (
                      <div className={cn("mt-2 rounded-md px-3 py-2 text-xs", result.ok ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive")}>
                        {result.ok ? (
                          <>
                            <span className="flex items-center gap-1 font-medium"><Loader2 className="h-3 w-3" /> Connected</span>
                            <span className="mt-0.5 block truncate text-muted-foreground">reply: {result.reply}</span>
                          </>
                        ) : (
                          <span className="flex items-start gap-1.5"><TestTube2 className="mt-0.5 h-3 w-3 shrink-0" /> {result.error}</span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Provider cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {PROVIDERS.map((p) => (
          <Card key={p.id}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle>{p.name}</CardTitle>
                <Badge tone={p.builtIn ? "success" : "info"}>{p.builtIn ? "built-in" : "local"}</Badge>
              </div>
              <CardDescription className="flex items-center gap-1.5">
                <KeyRound className="h-3 w-3" />
                <code className="font-mono text-[11px]">{p.envVar}</code>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">
                {p.models.length} models: {p.models.join(", ")}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Key setup guidance */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-primary" /> Connecting a provider
          </CardTitle>
          <CardDescription>
            Keys live in platform secrets, read server-side by the runtime — never
            in the browser or in agent configs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">
            <li>
              Generate an API key at the provider's dashboard (e.g.{" "}
              <code className="font-mono text-xs">platform.openai.com/api-keys</code>).
            </li>
            <li>
              Add it to the platform's secret store under the exact env var name
              listed on the provider card.
            </li>
            <li>
              Connect the model below, then set it in an agent's{" "}
              <em>model preferences</em> — the runtime failovers to the next
              preference on errors.
            </li>
          </ol>
        </CardContent>
      </Card>

      {creating && workspace && (
        <CreateConnectionDialog
          workspaceId={workspace.id}
          onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); load(); }}
        />
      )}
    </div>
  );
}

function CreateConnectionDialog({
  workspaceId,
  onClose,
  onSaved,
}: {
  workspaceId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [provider, setProvider] = useState("openai_compatible");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [keyRef, setKeyRef] = useState("OPENAI_API_KEY");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const providerDefaults: Record<string, { env: string; baseUrl: string }> = {
    google: { env: "GOOGLE_API_KEY", baseUrl: "" },
    openai: { env: "OPENAI_API_KEY", baseUrl: "" },
    anthropic: { env: "ANTHROPIC_API_KEY", baseUrl: "" },
    openai_compatible: { env: "OPENAI_API_KEY", baseUrl: "http://localhost:11434/v1" },
    ollama: { env: "OLLAMA_API_KEY", baseUrl: "http://localhost:11434/v1" },
  };

  const selectProvider = (p: string) => {
    setProvider(p);
    const d = providerDefaults[p];
    if (d) {
      setKeyRef(d.env);
      setBaseUrl(d.baseUrl);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/api/v1/workspaces/${workspaceId}/models`, {
        provider,
        model,
        base_url: baseUrl || null,
        key_ref: keyRef || null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect");
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} title="Connect a model">
      <div className="space-y-4">
        <Field label="Provider">
          <Select value={provider} onChange={(e) => selectProvider(e.target.value)}>
            <option value="openai_compatible">OpenAI-compatible endpoint (Ollama, vLLM, LM Studio…)</option>
            <option value="ollama">Ollama (local)</option>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
            <option value="google">Google Gemini</option>
          </Select>
        </Field>
        <Field label="Model name" hint="The exact string agents use in model preferences.">
          <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="e.g. llama3.2, gpt-4o-mini" autoFocus />
        </Field>
        {provider !== "google" && provider !== "openai" && provider !== "anthropic" && (
          <Field label="Base URL" hint="OpenAI-compatible /v1 endpoint.">
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://localhost:11434/v1" />
          </Field>
        )}
        <Field label="Key env var" hint="The secret holding the API key — never the key itself.">
          <Input value={keyRef} onChange={(e) => setKeyRef(e.target.value)} placeholder="OPENAI_API_KEY" />
        </Field>
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} loading={saving} disabled={!model.trim() || !keyRef.trim()}>
            Connect model
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
