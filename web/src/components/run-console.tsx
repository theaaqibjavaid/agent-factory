// Run console: subscribes to the SSE event stream for a run (design.md §6)
// and renders events as a live transcript. Also exports a small JSON viewer.
import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  Cpu,
  Database,
  Hammer,
  Loader2,
  Terminal,
  XCircle,
} from "lucide-react";
import { api, streamRunEvents } from "../lib/api";
import type { Run, RunEvent, RunEventType } from "../lib/types";
import { cn, formatUsd, formatTokens } from "../lib/utils";
import { Badge, Card } from "./ui";

const EVENT_META: Record<RunEventType, { label: string; icon: React.ReactNode; tone: string }> = {
  "run.start": { label: "Run started", icon: <Terminal className="h-3.5 w-3.5" />, tone: "text-muted-foreground" },
  token: { label: "Token", icon: <Cpu className="h-3.5 w-3.5" />, tone: "text-muted-foreground" },
  tool_call: { label: "Tool call", icon: <Hammer className="h-3.5 w-3.5" />, tone: "text-primary" },
  tool_result: { label: "Tool result", icon: <CheckCircle2 className="h-3.5 w-3.5" />, tone: "text-muted-foreground" },
  verify: { label: "Verified", icon: <ShieldIcon />, tone: "text-success" },
  memory: { label: "Memory", icon: <Database className="h-3.5 w-3.5" />, tone: "text-muted-foreground" },
  cost: { label: "Cost", icon: <CircleDashed className="h-3.5 w-3.5" />, tone: "text-warning" },
  "run.end": { label: "Run complete", icon: <CheckCircle2 className="h-3.5 w-3.5" />, tone: "text-success" },
  error: { label: "Error", icon: <XCircle className="h-3.5 w-3.5" />, tone: "text-destructive" },
};

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

export function RunConsole({
  run,
  onEvent,
  compact,
}: {
  run: Run;
  onEvent?: (event: RunEvent) => void;
  compact?: boolean;
}) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const connect = async () => {
      try {
        // Start from the latest seq we have (replay/resume support).
        const afterSeq = events.length ? events[events.length - 1].seq : 0;
        await streamRunEvents(
          `/api/v1/runs/${run.id}/events?after_seq=${afterSeq}`,
          (ev) => {
            if (cancelled) return;
            setEvents((prev) => (prev.some((e) => e.seq === ev.seq) ? prev : [...prev, ev]));
            setConnected(true);
            onEvent?.(ev);
          },
          controller.signal,
        );
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Stream failed");
        }
      }
    };

    connect();
    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.id]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length]);

  const toggle = (seq: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });
  };

  if (error && events.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        <AlertTriangle className="h-4 w-4" />
        {error}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col", compact ? "h-full" : "h-[28rem]")}>
      {/* Status bar */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {connected ? (
            <>
              <span className="h-2 w-2 animate-pulse rounded-full bg-success" />
              streaming
            </>
          ) : (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              connecting
            </>
          )}
          <span className="tabular-nums">seq {events.length ? events[events.length - 1].seq : 0}</span>
        </div>
        {run.stats && (
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="tabular-nums">{formatTokens(run.stats.total_tokens)} tok</span>
            <span className="tabular-nums">{formatUsd(run.stats.total_cost_usd)}</span>
          </div>
        )}
      </div>

      {/* Transcript */}
      <div ref={scrollRef} className="flex-1 space-y-1 overflow-y-auto scroll-thin p-3 font-mono text-xs">
        {events.length === 0 && (
          <p className="py-6 text-center text-muted-foreground">
            {error ? error : "Waiting for events…"}
          </p>
        )}
        {events.map((ev) => {
          const meta = EVENT_META[ev.event] ?? { label: ev.event, icon: null, tone: "text-muted-foreground" };
          const isExpandable = ev.event === "tool_call" || ev.event === "tool_result";
          const isOpen = expanded.has(ev.seq);
          return (
            <div key={ev.seq} className="group rounded-md px-2 py-1 hover:bg-muted/50">
              <button
                type="button"
                onClick={() => isExpandable && toggle(ev.seq)}
                className={cn(
                  "flex w-full items-start gap-2 text-left",
                  isExpandable && "cursor-pointer",
                )}
              >
                <span className={cn("mt-0.5 shrink-0", meta.tone)}>{meta.icon}</span>
                <span className="flex-1 leading-relaxed">
                  <span className="mr-2 select-none text-muted-foreground/60 tabular-nums">
                    {ev.seq}
                  </span>
                  <span className={cn("font-medium", meta.tone)}>{meta.label}</span>
                  <EventSummary ev={ev} />
                </span>
                {isExpandable && (
                  <ChevronRight
                    className={cn(
                      "mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
                      isOpen && "rotate-90",
                    )}
                  />
                )}
              </button>
              {isOpen && (
                <JsonViewer
                  value={ev.data}
                  className="mt-1 ml-6 border-l-2 border-border pl-3"
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EventSummary({ ev }: { ev: RunEvent }) {
  const d = ev.data as Record<string, any>;
  switch (ev.event) {
    case "run.start":
      return <span className="text-muted-foreground"> — {String(d.task ?? "")}</span>;
    case "token":
      return <span className="text-muted-foreground"> — {String(d.text ?? "")}</span>;
    case "tool_call":
      return (
        <span className="text-muted-foreground">
          {" "}
          — {String(d.name ?? "")}
          {d.iterations != null && <span className="tabular-nums"> (iter {String(d.iterations)})</span>}
        </span>
      );
    case "tool_result":
      return <span className="text-muted-foreground"> — ok</span>;
    case "verify":
      return (
        <span className="text-muted-foreground">
          {" "}
          — {String(d.result ?? "")}
          {d.safety != null && <Badge tone={d.safety === "safe" ? "success" : "warning"} className="ml-2">{String(d.safety)}</Badge>}
        </span>
      );
    case "memory":
      return <span className="text-muted-foreground"> — saved {String(d.messages ?? 0)} messages</span>;
    case "cost":
      return (
        <span className="text-muted-foreground">
          {" "}
          — {formatUsd(d.total_cost_usd)} · {formatTokens(d.total_tokens)} tokens
        </span>
      );
    case "run.end":
      return <span className="text-muted-foreground"> — {String(d.status ?? "")}</span>;
    case "error":
      return <span className="text-destructive"> — {String(d.message ?? d.error ?? "")}</span>;
    default:
      return null;
  }
}

/** Collapsible pretty-printer for any JSON blob. */
export function JsonViewer({
  value,
  className,
  maxHeight,
}: {
  value: unknown;
  className?: string;
  maxHeight?: string;
}) {
  const [open, setOpen] = useState(true);
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <div className={cn("rounded-md border border-border bg-background/70", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
        JSON
      </button>
      {open && (
        <pre
          className={cn("scroll-thin overflow-auto px-3 pb-3 font-mono text-[11px] leading-relaxed text-foreground/90", maxHeight ? "" : "max-h-72")}
          style={maxHeight ? { maxHeight } : undefined}
        >
          {text}
        </pre>
      )}
    </div>
  );
}

/** Status badge for a run, shared by lists and headers. */
export function RunStatusBadge({ status }: { status: Run["status"] }) {
  const map: Record<Run["status"], { tone: "default" | "primary" | "success" | "warning" | "destructive" | "muted"; label: string }> = {
    pending: { tone: "muted", label: "Pending" },
    pending_approval: { tone: "warning", label: "Awaiting approval" },
    running: { tone: "primary", label: "Running" },
    completed: { tone: "success", label: "Completed" },
    failed: { tone: "destructive", label: "Failed" },
    cancelled: { tone: "default", label: "Cancelled" },
  };
  const m = map[status];
  return <Badge tone={m.tone}>{m.label}</Badge>;
}
