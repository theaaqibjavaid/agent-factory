// Terminal (Phase 5.1) — workspace-scoped PTY shell over WebSocket.
// xterm.js renders the stream; destructive commands surface a confirmation
// prompt in-terminal and are only dispatched after explicit confirm.
import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { Plus, ShieldAlert, Square, TerminalSquare } from "lucide-react";
import { api, getAccessToken } from "../lib/api";
import { useWorkspace } from "../components/workspaces";
import { Button, Card, EmptyState, Skeleton } from "../components/ui";

interface TerminalSessionInfo {
  id: string;
  workspace_id: string;
  cwd: string;
  alive: boolean;
  pending_confirmation: string | null;
  pending_reason: string | null;
  created_at: string | null;
}

const WS_BASE = () => {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
};

export function TerminalPage() {
  const { workspace } = useWorkspace();
  const [sessions, setSessions] = useState<TerminalSessionInfo[] | null>(null);
  const [active, setActive] = useState<TerminalSessionInfo | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [socketState, setSocketState] = useState<"disconnected" | "connecting" | "connected">("disconnected");

  const termRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingConfirmRef = useRef<string | null>(null);

  const load = async () => {
    if (!workspace) return;
    try {
      const data = await api.get<{ sessions: TerminalSessionInfo[] }>(
        `/api/v1/workspaces/${workspace.id}/terminal/sessions`,
      );
      setSessions(data.sessions);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace?.id]);

  // Create a session and attach the terminal to it.
  const create = async () => {
    if (!workspace) return;
    setCreating(true);
    setError(null);
    try {
      const session = await api.post<TerminalSessionInfo>(
        `/api/v1/workspaces/${workspace.id}/terminal/sessions`,
        {},
      );
      await load();
      setActive(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setCreating(false);
    }
  };

  const close = async (session: TerminalSessionInfo) => {
    if (!workspace) return;
    try {
      await api.delete(`/api/v1/workspaces/${workspace.id}/terminal/sessions/${session.id}`);
      if (active?.id === session.id) setActive(null);
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Close failed");
    }
  };

  // Attach xterm once; reuse for every session.
  useEffect(() => {
    if (!termRef.current) return;
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
      theme: {
        background: "#0c0f14",
        foreground: "#d4d4d8",
        cursor: "#f59e0b",
        selectionBackground: "#3f3f46",
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(termRef.current);
    fit.fit();
    xtermRef.current = term;
    fitRef.current = fit;
    term.onData((data) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        if (pendingConfirmRef.current) {
          // Confirmation gate: Enter dispatches the pending command.
          if (data === "\r" || data === "\n" || data === "y" || data === "Y") {
            wsRef.current.send(JSON.stringify({ type: "confirm", data: pendingConfirmRef.current }));
            pendingConfirmRef.current = null;
          }
          return;
        }
        wsRef.current.send(JSON.stringify({ type: "input", data }));
      }
    });
    const onResize = () => {
      try {
        fit.fit();
        if (wsRef.current?.readyState === WebSocket.OPEN && active) {
          wsRef.current.send(
            JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }),
          );
        }
      } catch {
        /* container hidden */
      }
    };
    window.addEventListener("resize", onResize);
    const observer = new ResizeObserver(onResize);
    if (termRef.current) observer.observe(termRef.current);
    return () => {
      window.removeEventListener("resize", onResize);
      observer.disconnect();
      term.dispose();
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Open the WebSocket when a session becomes active.
  useEffect(() => {
    if (!active || !workspace) return;
    if (wsRef.current) wsRef.current.close();
    pendingConfirmRef.current = null;
    const term = xtermRef.current;
    if (!term) return;

    term.reset();
    term.writeln("\x1b[90m— AgentFactory terminal — workspace-scoped shell\x1b[0m");
    term.writeln(`\x1b[90m— cwd: ${active.cwd}\x1b[0m`);
    term.writeln("");

    setSocketState("connecting");
    const token = getAccessToken() ?? "";
    const ws = new WebSocket(
      `${WS_BASE()}/api/v1/workspaces/${workspace.id}/terminal/ws?token=${token}&session=${active.id}`,
    );
    wsRef.current = ws;

    ws.onopen = () => {
      setSocketState("connected");
      setTimeout(() => {
        try {
          fitRef.current?.fit();
          ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
        } catch {
          /* noop */
        }
      }, 50);
    };
    ws.onmessage = (ev) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      if (msg.type === "output") {
        term.write(String(msg.data ?? ""));
      } else if (msg.type === "confirm") {
        pendingConfirmRef.current = String(msg.command ?? "");
        term.writeln("");
        term.writeln(
          `\x1b[31m⚠ Destructive command — ${String(msg.reason ?? "requires confirmation")}\x1b[0m`,
        );
        term.writeln(`\x1b[33m  ${String(msg.command ?? "").trim()}\x1b[0m`);
        term.writeln("\x1b[31mPress Enter to run it anyway, or type anything else to cancel.\x1b[0m");
      } else if (msg.type === "closed") {
        term.writeln("\r\n\x1b[90m— session closed —\x1b[0m");
        setSocketState("disconnected");
        setActive(null);
        load();
      } else if (msg.type === "error") {
        term.writeln(`\r\n\x1b[31m${String(msg.message ?? "error")}\x1b[0m`);
      }
    };
    ws.onclose = () => {
      setSocketState("disconnected");
    };
    return () => {
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <TerminalSquare className="h-6 w-6 text-primary" /> Terminal
          </h1>
          <p className="text-sm text-muted-foreground">
            Workspace-scoped shell — commands run inside the workspace sandbox
            root. Destructive commands need confirmation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {socketState === "connected" && (
            <span className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs text-success">
              <span className="h-1.5 w-1.5 rounded-full bg-success" /> connected
            </span>
          )}
          {active && (
            <Button variant="outline" size="sm" onClick={() => close(active)}>
              <Square className="h-3.5 w-3.5" /> Close session
            </Button>
          )}
          <Button size="sm" onClick={create} loading={creating}>
            <Plus className="h-4 w-4" /> New session
          </Button>
        </div>
      </div>

      {error && <EmptyState title="Terminal error" description={error} />}

      {!sessions && !error && <Skeleton className="h-72" />}

      {sessions && sessions.length === 0 && !active && (
        <EmptyState
          icon={<TerminalSquare className="h-6 w-6" />}
          title="No terminal session"
          description="Start a workspace-scoped shell to run commands."
          action={<Button size="sm" onClick={create}><Plus className="h-4 w-4" /> New session</Button>}
        />
      )}

      <Card className="overflow-hidden">
        <div ref={termRef} className="h-[480px] w-full bg-[#0c0f14] p-2" />
        <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5 text-warning" />
            Guarded: rm -rf, force push, hard reset, and other destructive
            commands require confirmation.
          </span>
          {active && <span className="font-mono">{active.id.slice(0, 8)}</span>}
        </div>
      </Card>
    </div>
  );
}
