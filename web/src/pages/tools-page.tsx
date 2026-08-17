// Tools — merged catalog (built-ins + custom + marketplace) with a custom
// tool editor that validates code before it can be enabled (Phase 4.1).
import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, Hammer, Pencil, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { ToolEntry, ValidationResult } from "../lib/types";
import { cn, formatUsd } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, Dialog, EmptyState, Field, Input, Select, Skeleton, Textarea } from "../components/ui";

const SAFETY_TONE = { safe: "success", modified: "warning", destructive: "destructive" } as const;

const SAMPLE_CODE = `def my_tool(query: str, limit: int = 5) -> str:
    """Describe what this tool does."""
    # Your implementation here. Safe stdlib imports allowed:
    # re, json, math, urllib.request, ...
    return f"results for {query}: {limit}"`;

export function ToolsPage() {
  const { workspace } = useWorkspace();
  const [tools, setTools] = useState<ToolEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ToolEntry | null>(null);

  const load = useCallback(async () => {
    if (!workspace) return;
    try {
      const data = await api.get<{ tools: ToolEntry[] }>(`/api/v1/workspaces/${workspace.id}/tools`);
      setTools(data.tools);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tools");
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (tool: ToolEntry) => {
    if (!workspace || !tool.id || tool.source === "builtin") return;
    if (!window.confirm(`Delete custom tool "${tool.name}"?`)) return;
    try {
      await api.delete(`/api/v1/workspaces/${workspace.id}/tools/${tool.id}`);
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const toggleEnabled = async (tool: ToolEntry) => {
    if (!workspace || !tool.id || tool.source === "builtin") return;
    try {
      await api.patch(`/api/v1/workspaces/${workspace.id}/tools/${tool.id}`, {
        enabled: !tool.enabled,
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
          <h1 className="text-2xl font-bold tracking-tight">Tools</h1>
          <p className="text-sm text-muted-foreground">
            Built-in catalog plus your custom tools — validated, sandboxed, safety-tagged.
          </p>
        </div>
        <Button onClick={() => { setEditing(null); setEditorOpen(true); }}>
          <Plus className="h-4 w-4" /> New custom tool
        </Button>
      </div>

      {error && !tools && <EmptyState title="Couldn't load tools" description={error} />}
      {!tools && !error && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-36" />)}
        </div>
      )}

      {tools && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tools.map((tool) => {
            const isBuiltin = tool.source === "builtin";
            return (
              <Card key={`${tool.source}-${tool.name}`} className={cn(!tool.enabled && !isBuiltin && "opacity-60")}>
                <div className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/15 text-primary">
                        <Hammer className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="font-mono text-sm font-semibold leading-tight">{tool.name}</p>
                        <p className="text-xs text-muted-foreground">{tool.category}</p>
                      </div>
                    </div>
                    <Badge tone={SAFETY_TONE[tool.safety_level]}>{tool.safety_level}</Badge>
                  </div>
                  <p className="mt-3 line-clamp-2 min-h-8 text-sm text-muted-foreground">{tool.description}</p>
                  <div className="mt-3 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
                    <span className="tabular-nums">{formatUsd(tool.cost_per_call_usd)}/call</span>
                    <Badge tone={isBuiltin ? "info" : tool.source === "marketplace" ? "primary" : "default"}>
                      {tool.source}
                    </Badge>
                  </div>
                  {!isBuiltin && (
                    <div className="mt-3 flex items-center gap-2">
                      <Button
                        size="sm"
                        variant={tool.enabled ? "secondary" : "outline"}
                        className="flex-1"
                        onClick={() => toggleEnabled(tool)}
                      >
                        {tool.enabled ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                        {tool.enabled ? "Enabled" : "Disabled"}
                      </Button>
                      <Button size="icon" variant="ghost" onClick={() => { setEditing(tool); setEditorOpen(true); }} aria-label={`Edit ${tool.name}`}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button size="icon" variant="ghost" onClick={() => remove(tool)} aria-label={`Delete ${tool.name}`}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {editorOpen && workspace && (
        <ToolEditorDialog
          workspaceId={workspace.id}
          existing={editing}
          onClose={() => setEditorOpen(false)}
          onSaved={() => { setEditorOpen(false); load(); }}
        />
      )}
    </div>
  );
}

function ToolEditorDialog({
  workspaceId,
  existing,
  onClose,
  onSaved,
}: {
  workspaceId: string;
  existing: ToolEntry | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const meta = (existing?.metadata ?? {}) as Record<string, any>;
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState<string>(meta.description ?? "");
  const [category, setCategory] = useState<string>(meta.category ?? "custom");
  const [safety, setSafety] = useState<string>(meta.safety_level ?? "safe");
  const [code, setCode] = useState<string>(existing ? "" : SAMPLE_CODE);
  const [functionName, setFunctionName] = useState<string>(meta.function_name ?? "");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedCode, setLoadedCode] = useState(false);

  // Fetch the existing code for editing (code is delivered to the workspace
  // owner only; the list endpoint deliberately omits it).
  useEffect(() => {
    if (!existing?.id || loadedCode) return;
    api
      .get<{ code: string }>(`/api/v1/workspaces/${workspaceId}/tools/${existing.id}`)
      .then((r) => { setCode(r.code); setLoadedCode(true); })
      .catch(() => setLoadedCode(true));
  }, [existing?.id, loadedCode, workspaceId]);

  const validate = async () => {
    setError(null);
    try {
      const result = await api.post<ValidationResult>(`/api/v1/workspaces/${workspaceId}/tools/validate`, {
        name,
        code,
        function_name: functionName || null,
      });
      setValidation(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = {
      name,
      description,
      code,
      category,
      safety_level: safety,
      function_name: functionName || null,
    };
    try {
      if (existing?.id) {
        await api.patch(`/api/v1/workspaces/${workspaceId}/tools/${existing.id}`, body);
      } else {
        await api.post(`/api/v1/workspaces/${workspaceId}/tools`, body);
      }
      onSaved();
    } catch (err) {
      const detail = (err as { detail?: unknown }).detail;
      if (detail && typeof detail === "object") {
        const v = (detail as { validation?: ValidationResult }).validation;
        if (v) setValidation(v);
        setError((detail as { message?: string }).message ?? (err instanceof Error ? err.message : "Save failed"));
      } else {
        setError(err instanceof Error ? err.message : "Save failed");
      }
    } finally {
      setSaving(false);
    }
  };

  const canSave = validation?.passes === true && name.trim();

  return (
    <Dialog open onClose={onClose} title={existing ? `Edit ${existing.name}` : "New custom tool"} wide>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name" hint="The identifier agents reference in their tool list.">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. slugify" disabled={Boolean(existing)} />
          </Field>
          <Field label="Function name" hint="Optional — defaults to the first function in the code.">
            <Input value={functionName} onChange={(e) => setFunctionName(e.target.value)} placeholder="e.g. slugify" />
          </Field>
        </div>
        <Field label="Description">
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does it do?" />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Category">
            <Input value={category} onChange={(e) => setCategory(e.target.value)} />
          </Field>
          <Field label="Safety level" hint="Metadata, not a claim — the runtime enforces it.">
            <Select value={safety} onChange={(e) => setSafety(e.target.value)}>
              <option value="safe">safe</option>
              <option value="modified">modified</option>
              <option value="destructive">destructive</option>
            </Select>
          </Field>
        </div>
        <Field label="Code" hint="Runs in a sandbox: safe stdlib imports only (re, json, urllib…), no subprocess/socket/eval. DESTRUCTIVE tools stay gated by the runtime.">
          <Textarea
            rows={12}
            className="font-mono text-xs"
            value={code}
            onChange={(e) => { setCode(e.target.value); setValidation(null); }}
            spellCheck={false}
          />
        </Field>

        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={validate}>
            <ShieldAlert className="h-4 w-4" /> Validate
          </Button>
          {validation && (
            <div className="flex-1 space-y-1">
              {validation.ok && validation.passes && (
                <p className="flex items-center gap-1.5 text-sm text-success">
                  <CheckCircle2 className="h-4 w-4" /> Valid — function {validation.function_name}, {validation.findings.length} findings
                </p>
              )}
              {validation.ok && !validation.passes && (
                <p className="flex items-center gap-1.5 text-sm text-destructive">
                  <AlertTriangle className="h-4 w-4" /> Blocked: high-severity findings
                </p>
              )}
              {!validation.ok && (
                <p className="flex items-center gap-1.5 text-sm text-destructive">
                  <AlertTriangle className="h-4 w-4" /> {validation.errors[0]}
                </p>
              )}
              {validation.findings.length > 0 && (
                <ul className="space-y-0.5 pl-5 text-xs text-muted-foreground">
                  {validation.findings.slice(0, 4).map((f, i) => (
                    <li key={i} className={cn(f.severity === "high" && "text-destructive")}>
                      [{f.severity}] line {f.line}: {f.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} loading={saving} disabled={!canSave}>
            {existing ? "Save changes" : "Create tool"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
