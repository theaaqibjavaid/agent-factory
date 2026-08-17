// Models — provider registry and API key management (Phase 4 wires the live
// registry; the Studio shows the supported providers and how to connect keys).
import React, { useState } from "react";
import { Cpu, KeyRound, Plus, Trash2 } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input, Select } from "../components/ui";

interface ProviderDef {
  id: string;
  name: string;
  envVar: string;
  models: string[];
  builtIn: boolean;
}

const PROVIDERS: ProviderDef[] = [
  { id: "openai", name: "OpenAI", envVar: "OPENAI_API_KEY", models: ["gpt-4o", "gpt-4o-mini", "o3-mini"], builtIn: true },
  { id: "anthropic", name: "Anthropic", envVar: "ANTHROPIC_API_KEY", models: ["claude-sonnet-4-5", "claude-haiku-4-5"], builtIn: true },
  { id: "google", name: "Google", envVar: "GOOGLE_API_KEY", models: ["gemini-2.5-pro", "gemini-2.5-flash"], builtIn: true },
  { id: "groq", name: "Groq", envVar: "GROQ_API_KEY", models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"], builtIn: true },
  { id: "openrouter", name: "OpenRouter", envVar: "OPENROUTER_API_KEY", models: ["openai/gpt-4o", "anthropic/claude-sonnet-4-5"], builtIn: true },
  { id: "ollama", name: "Ollama (local)", envVar: "— (local)", models: ["llama3.2", "qwen2.5"], builtIn: false },
];

export function ModelsPage() {
  const [custom, setCustom] = useState<Array<{ name: string; provider: string }>>([]);
  const [name, setName] = useState("");
  const [provider, setProvider] = useState(PROVIDERS[0].id);

  const addCustom = () => {
    if (!name.trim()) return;
    setCustom((prev) => [...prev, { name: name.trim(), provider }]);
    setName("");
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Models</h1>
        <p className="text-sm text-muted-foreground">
          Connect provider keys once; every agent can use them. Custom models
          are added by the operator in the registry (Phase 4 makes this live).
        </p>
      </div>

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
            Keys are never stored in the browser or in agent configs — they live
            in platform secrets and are read server-side by the runtime.
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
              listed above.
            </li>
            <li>
              Set the provider in an agent's <em>model preferences</em> — the
              runtime failovers to the next preference on errors.
            </li>
          </ol>
        </CardContent>
      </Card>

      {/* Custom model registry (UI stub — persisted in Phase 4) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-primary" /> Custom models
          </CardTitle>
          <CardDescription>Model names outside the built-in catalog.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="model id, e.g. my-fine-tune-v2"
              className="max-w-xs"
              onKeyDown={(e) => e.key === "Enter" && addCustom()}
            />
            <Select value={provider} onChange={(e) => setProvider(e.target.value)} className="w-44">
              {PROVIDERS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
            <Button variant="secondary" onClick={addCustom} disabled={!name.trim()}>
              <Plus className="h-4 w-4" /> Add
            </Button>
          </div>
          {custom.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No custom models yet. Agents reference models by string, so any
              provider that can serve them will work.
            </p>
          ) : (
            <div className="space-y-1.5">
              {custom.map((m) => (
                <div
                  key={m.name}
                  className="flex items-center justify-between rounded-md border border-border px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-muted-foreground" />
                    <span className="font-mono text-sm">{m.name}</span>
                    <Badge tone="muted">{PROVIDERS.find((p) => p.id === m.provider)?.name}</Badge>
                  </div>
                  <button
                    type="button"
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                    onClick={() => setCustom((prev) => prev.filter((x) => x.name !== m.name))}
                    aria-label={`Remove ${m.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
