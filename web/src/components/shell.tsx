// Studio app shell: sidebar nav + topbar with workspace switcher, safety
// indicator, and user menu. Layout per design.md §5.
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  Bot,
  Boxes,
  Cable,
  CheckCheck,
  Cpu,
  Database,
  Gauge,
  Hammer,
  LineChart,
  LogOut,
  Menu,
  Settings,
  ShieldAlert,
  Store,
  TerminalSquare,
  Wand2,
  X,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useAuth } from "./auth";
import { useWorkspace } from "./workspaces";
import { Badge, Button, StatusDot } from "./ui";

const NAV = [
  { to: "/app", label: "Dashboard", icon: Gauge, end: true },
  { to: "/app/agents", label: "Agents", icon: Bot },
  { to: "/app/runs", label: "Run Console", icon: Activity },
  { to: "/app/approvals", label: "Approvals", icon: CheckCheck },
  { to: "/app/memory", label: "Memory", icon: Database },
  { to: "/app/terminal", label: "Terminal", icon: TerminalSquare },
  { to: "/app/observability", label: "Observability", icon: LineChart },
];

const EXTENSIBILITY_NAV = [
  { to: "/app/tools", label: "Tools", icon: Hammer },
  { to: "/app/skills", label: "Skills", icon: Wand2 },
  { to: "/app/mcp", label: "MCP Servers", icon: Cable },
  { to: "/app/marketplace", label: "Marketplace", icon: Store },
  { to: "/app/models", label: "Models", icon: Cpu },
];

export function AppShell() {
  const { workspace, workspaces, setWorkspaceId } = useWorkspace();
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const allowDestructive = Boolean(
    workspace?.settings && (workspace.settings as Record<string, unknown>).allow_destructive,
  );

  const sidebar = (
    <div className="flex h-full flex-col">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <Bot className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-bold tracking-tight">AgentFactory</p>
          <p className="text-[11px] text-muted-foreground">Studio v0.3</p>
        </div>
      </div>

      {/* Workspace switcher */}
      <div className="px-3 pb-2">
        <select
          value={workspace?.id ?? ""}
          onChange={(e) => setWorkspaceId(e.target.value)}
          className="h-9 w-full rounded-md border border-border bg-muted px-2.5 text-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Switch workspace"
        >
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto scroll-thin px-3 py-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
        <p className="px-3 pb-1 pt-4 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
          Extensibility
        </p>
        {EXTENSIBILITY_NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-2.5 rounded-md px-2 py-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-bold uppercase">
            {(user?.name ?? user?.email ?? "?").slice(0, 2)}
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-sm font-medium">{user?.name ?? "User"}</p>
            <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
          </div>
          <button
            type="button"
            onClick={() => {
              signOut();
              navigate("/");
            }}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 border-r border-border bg-card md:block">{sidebar}</aside>

      {/* Mobile sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-border bg-card">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute right-3 top-4 rounded-md p-1 text-muted-foreground hover:bg-muted"
              aria-label="Close menu"
            >
              <X className="h-4 w-4" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card/60 px-4 backdrop-blur">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted md:hidden"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex-1" />
          <div className="hidden items-center gap-2 sm:flex">
            <Badge tone={allowDestructive ? "warning" : "success"}>
              {allowDestructive ? (
                <>
                  <ShieldAlert className="h-3 w-3" /> Destructive tools allowed
                </>
              ) : (
                <>
                  <StatusDot tone="success" /> Guardrails on
                </>
              )}
            </Badge>
            <Badge tone="info" className="hidden lg:inline-flex">
              <Boxes className="h-3 w-3" />
              {workspace?.role ?? "member"}
            </Badge>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate("/app/agents")}>
            <Bot className="h-3.5 w-3.5" /> New agent
          </Button>
        </header>

        <main className="flex-1 overflow-y-auto scroll-thin">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
