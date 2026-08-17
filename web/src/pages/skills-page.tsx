// Skills — create from the UI, browse installed, delete (Phase 4.2).
// A skill's instructions are injected into any agent that lists it.
import React, { useCallback, useEffect, useState } from "react";
import { BookOpen, Plus, Trash2, Wand2 } from "lucide-react";
import { api } from "../lib/api";
import type { SkillEntry } from "../lib/types";
import { cn } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, Dialog, EmptyState, Field, Input, Select, Skeleton, Textarea } from "../components/ui";

export function SkillsPage() {
  const { workspace } = useWorkspace();
  const [skills, setSkills] = useState<SkillEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (!workspace) return;
    try {
      const data = await api.get<{ skills: SkillEntry[] }>(`/api/v1/workspaces/${workspace.id}/skills`);
      setSkills(data.skills);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skills");
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (skill: SkillEntry) => {
    if (!workspace) return;
    if (!window.confirm(`Delete skill "${skill.name}"?`)) return;
    try {
      await api.delete(`/api/v1/workspaces/${workspace.id}/skills/${skill.id}`);
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const toggleEnabled = async (skill: SkillEntry) => {
    if (!workspace) return;
    try {
      await api.patch(`/api/v1/workspaces/${workspace.id}/skills/${skill.id}`, {
        enabled: !skill.enabled,
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
          <h1 className="text-2xl font-bold tracking-tight">Skills</h1>
          <p className="text-sm text-muted-foreground">
            Pluggable capabilities — instructions injected into any agent that
            lists the skill by name.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> New skill
        </Button>
      </div>

      {error && !skills && <EmptyState title="Couldn't load skills" description={error} />}
      {!skills && !error && <Skeleton className="h-48" />}

      {skills && skills.length === 0 && (
        <EmptyState
          icon={<BookOpen className="h-6 w-6" />}
          title="No skills yet"
          description="Create a skill — or install one from the Marketplace."
          action={<Button size="sm" onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> Create skill</Button>}
        />
      )}

      {skills && skills.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill) => (
            <Card key={skill.id} className={cn(!skill.enabled && "opacity-60")}>
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/15 text-primary">
                      <Wand2 className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-semibold leading-tight">{skill.name}</p>
                      <p className="text-xs text-muted-foreground">{skill.metadata.category ?? "generic"}</p>
                    </div>
                  </div>
                  <Badge tone={skill.source === "marketplace" ? "primary" : "default"}>{skill.source}</Badge>
                </div>
                <p className="mt-3 line-clamp-2 min-h-8 text-sm text-muted-foreground">
                  {skill.metadata.description}
                </p>
                {skill.metadata.instructions && (
                  <p className="mt-2 line-clamp-2 rounded-md bg-background/60 p-2 font-mono text-[11px] text-muted-foreground">
                    {skill.metadata.instructions}
                  </p>
                )}
                <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
                  <Button
                    size="sm"
                    variant={skill.enabled ? "secondary" : "outline"}
                    className="flex-1"
                    onClick={() => toggleEnabled(skill)}
                  >
                    {skill.enabled ? "Enabled" : "Disabled"}
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => remove(skill)} aria-label={`Delete ${skill.name}`}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {creating && workspace && (
        <CreateSkillDialog
          workspaceId={workspace.id}
          onClose={() => setCreating(false)}
          onCreated={() => { setCreating(false); load(); }}
        />
      )}
    </div>
  );
}

function CreateSkillDialog({
  workspaceId,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [category, setCategory] = useState("research");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/api/v1/workspaces/${workspaceId}/skills`, {
        name,
        description,
        instructions,
        category,
        tools: [],
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create skill");
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} title="New skill">
      <div className="space-y-4">
        <Field label="Name" hint="Agents reference this in their skill list.">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. briefing-writer" autoFocus />
        </Field>
        <Field label="Description">
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does this skill do?" />
        </Field>
        <Field label="Instructions" hint="Injected into the agent's system prompt when this skill is attached.">
          <Textarea
            rows={6}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="e.g. Structure briefings: TL;DR, findings, risks, next step. Never invent facts."
          />
        </Field>
        <Field label="Category">
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            {["research", "engineering", "writing", "data", "ops", "generic"].map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </Select>
        </Field>
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} loading={saving} disabled={!name.trim() || !description.trim()}>
            Create skill
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
