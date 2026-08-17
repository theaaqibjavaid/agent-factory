// Approvals — human-in-the-loop inbox (Phase 2.3). Review gated proposals:
// approve (executes the linked run), reject (cancels), or modify (amend plan).
import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCheck, Check, RotateCcw, X } from "lucide-react";
import { api } from "../lib/api";
import type { Proposal } from "../lib/types";
import { cn, timeAgo } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Skeleton, Textarea, Tabs } from "../components/ui";

type Filter = "pending" | "history";

const STATUS_TONE: Record<Proposal["status"], "default" | "warning" | "success" | "destructive" | "muted" | "info"> = {
  pending: "warning",
  approved: "success",
  rejected: "destructive",
  modified: "info",
  executed: "success",
  cancelled: "default",
};

export function ApprovalsPage() {
  const { workspace } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>(params.get("status") === "pending" ? "pending" : "pending");
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(params.get("proposal"));
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!workspace) return;
    try {
      const data = await api.get<{ proposals: Proposal[] }>(
        `/api/v1/workspaces/${workspace.id}/proposals${filter === "pending" ? "?status=pending" : "?limit=100"}`,
      );
      setProposals(data.proposals);
      setError(null);
      if (!data.proposals.some((p) => p.id === activeId)) {
        setActiveId(data.proposals[0]?.id ?? null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load proposals");
    }
  }, [workspace?.id, filter, activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const review = async (action: "approve" | "reject" | "modify", notes?: string) => {
    if (!workspace || !activeId) return;
    setBusy(true);
    try {
      await api.post(`/api/v1/workspaces/${workspace.id}/proposals/${activeId}/review`, {
        action,
        notes: notes ?? null,
      });
      // Refresh both views so the inbox drains as things resolve.
      const data = await api.get<{ proposals: Proposal[] }>(
        `/api/v1/workspaces/${workspace.id}/proposals${filter === "pending" ? "?status=pending" : "?limit=100"}`,
      );
      setProposals(data.proposals);
      setActiveId((prev) => (data.proposals.some((p) => p.id === prev) ? prev : data.proposals[0]?.id ?? null));
      setParams({}, { replace: true });
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Review failed");
    } finally {
      setBusy(false);
    }
  };

  const active = proposals?.find((p) => p.id === activeId) ?? null;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Approvals</h1>
          <p className="text-sm text-muted-foreground">
            Human-in-the-loop gate for gated agents.
          </p>
        </div>
        <Tabs
          value={filter}
          onValueChange={(v) => setFilter(v as Filter)}
          tabs={[
            { value: "pending", label: "Inbox" },
            { value: "history", label: "History" },
          ]}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle>{filter === "pending" ? "Waiting on you" : "Review history"}</CardTitle>
          </CardHeader>
          <CardContent>
            {!proposals && !error && <Skeleton className="h-64" />}
            {error && !proposals && <EmptyState title="Couldn't load approvals" description={error} />}
            {proposals && proposals.length === 0 && (
              <EmptyState
                icon={<CheckCheck className="h-6 w-6" />}
                title="Inbox zero"
                description={
                  filter === "pending"
                    ? "No proposals waiting. Gated agents will queue here."
                    : "No reviewed proposals yet."
                }
              />
            )}
            {proposals && proposals.length > 0 && (
              <div className="max-h-[32rem] space-y-1 overflow-y-auto scroll-thin pr-1">
                {proposals.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setActiveId(p.id)}
                    className={cn(
                      "w-full rounded-md border px-3 py-2.5 text-left transition-colors",
                      activeId === p.id ? "border-primary/50 bg-primary/10" : "border-border hover:border-primary/30",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">{p.title}</p>
                      <Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{timeAgo(p.created_at)}</p>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader className="pb-2">
            <CardTitle>Proposal</CardTitle>
          </CardHeader>
          <CardContent>
            {!active ? (
              <EmptyState
                icon={<CheckCheck className="h-6 w-6" />}
                title="Nothing to review"
                description="Select a proposal from the list."
              />
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold">{active.title}</p>
                  <Badge tone={STATUS_TONE[active.status]}>{active.status}</Badge>
                </div>
                <pre className="scroll-thin max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-background/70 p-4 font-mono text-xs leading-relaxed">
                  {active.plan}
                </pre>
                {active.decision_notes && (
                  <div className="rounded-md border border-border p-3">
                    <p className="text-xs font-medium text-muted-foreground">Decision notes</p>
                    <p className="mt-1 text-sm">{active.decision_notes}</p>
                  </div>
                )}

                {active.status === "pending" || active.status === "modified" ? (
                  <ReviewActions onReview={review} busy={busy} />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    This proposal was {active.status} — nothing left to do.
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ReviewActions({
  onReview,
  busy,
}: {
  onReview: (action: "approve" | "reject" | "modify", notes?: string) => Promise<void>;
  busy: boolean;
}) {
  const [notes, setNotes] = useState("");
  const [mode, setMode] = useState<"approve" | "modify">("approve");

  return (
    <div className="space-y-3 rounded-md border border-border p-4">
      <Textarea
        rows={3}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder={
          mode === "modify"
            ? "Amended plan / additional instructions for the run…"
            : "Notes (optional)…"
        }
      />
      <div className="flex flex-wrap items-center gap-2">
        {mode === "approve" ? (
          <>
            <Button onClick={() => onReview("approve", notes || undefined)} loading={busy}>
              <Check className="h-4 w-4" /> Approve & execute
            </Button>
            <Button variant="destructive" onClick={() => onReview("reject", notes || undefined)} loading={busy}>
              <X className="h-4 w-4" /> Reject
            </Button>
            <Button variant="ghost" onClick={() => setMode("modify")}>
              <RotateCcw className="h-4 w-4" /> Modify plan
            </Button>
          </>
        ) : (
          <>
            <Button variant="primary" onClick={() => onReview("modify", notes)} loading={busy}>
              Save amended plan
            </Button>
            <Button variant="ghost" onClick={() => setMode("approve")}>
              Back
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
