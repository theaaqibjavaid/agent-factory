// Landing page — factory-themed intro to AgentFactory Studio.
import React from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  CheckCheck,
  Cpu,
  Database,
  GitBranch,
  Hammer,
  Layers,
  Play,
  ShieldCheck,
  Terminal,
  Zap,
} from "lucide-react";
import { useAuth } from "../components/auth";
import { Badge, Button } from "../components/ui";

const FEATURES = [
  {
    icon: Layers,
    title: "Agents as data",
    text: "Every agent is configuration: rank, tools, skills, MCP servers, model preferences, budget, and gates. Render it, snapshot it, audit it.",
  },
  {
    icon: Hammer,
    title: "Built-in tool catalog",
    text: "Web, files, git, and notifications out of the box — each tagged with safety level and per-call cost. Custom tools and an MCP marketplace come next.",
  },
  {
    icon: ShieldCheck,
    title: "Human-in-the-loop",
    text: "Gated agents queue every plan for approval. Approve, reject, or amend from the inbox before anything executes.",
  },
  {
    icon: Database,
    title: "Memory you own",
    text: "Per-agent facts and conversation history — export and import portable, versioned bundles between workspaces and machines.",
  },
  {
    icon: Play,
    title: "Streamed runs",
    text: "Every run is an SSE event stream: tokens, tool calls, verification, cost. Replay from any point; retry failures cleanly.",
  },
  {
    icon: Cpu,
    title: "Model freedom",
    text: "Bring your own keys. Multi-model preferences with automatic failover — or point agents at local models.",
  },
];

export function LandingPage() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen">
      {/* Nav */}
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Bot className="h-5 w-5" />
            </div>
            <span className="text-base font-bold tracking-tight">AgentFactory</span>
            <Badge tone="info" className="ml-1 hidden sm:inline-flex">
              Studio v0.3
            </Badge>
          </div>
          <nav className="hidden items-center gap-6 text-sm text-muted-foreground md:flex">
            <a href="#features" className="hover:text-foreground">Features</a>
            <a href="#how" className="hover:text-foreground">How it works</a>
          </nav>
          <div className="flex items-center gap-2">
            {user ? (
              <Link to="/app">
                <Button size="sm">
                  Open Studio <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </Link>
            ) : (
              <>
                <Link to="/auth">
                  <Button variant="ghost" size="sm">Sign in</Button>
                </Link>
                <Link to="/auth?mode=signup">
                  <Button size="sm">
                    Start free <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(70rem 35rem at 15% -10%, hsl(var(--primary) / 0.12), transparent 55%), radial-gradient(50rem 30rem at 95% 20%, hsl(var(--accent) / 0.2), transparent 55%)",
          }}
        />
        <div className="relative mx-auto max-w-6xl px-6 py-24 text-center md:py-32">
          <Badge tone="primary" className="mb-6">
            <Zap className="h-3 w-3" /> The universal agentic factory
          </Badge>
          <h1 className="mx-auto max-w-3xl text-4xl font-extrabold leading-tight tracking-tight md:text-6xl">
            Build agents the way you'd run a{" "}
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              factory floor
            </span>
            .
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground md:text-lg">
            Compose tools, skills, MCP servers, and models into full agentic
            loops — verified, budgeted, and gated. Sign up, connect a model
            key, and ship your first agent in minutes.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            {user ? (
              <Link to="/app">
                <Button size="lg">
                  Open Studio <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            ) : (
              <>
                <Link to="/auth?mode=signup">
                  <Button size="lg">
                    Build your first agent <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link to="/auth">
                  <Button variant="outline" size="lg">Sign in</Button>
                </Link>
              </>
            )}
          </div>

          {/* Terminal mock */}
          <div className="mx-auto mt-16 max-w-3xl overflow-hidden rounded-xl border border-border bg-card text-left shadow-2xl">
            <div className="flex items-center gap-1.5 border-b border-border px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-destructive/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-warning/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-success/70" />
              <span className="ml-2 font-mono text-xs text-muted-foreground">run console</span>
            </div>
            <pre className="scroll-thin overflow-x-auto p-4 font-mono text-xs leading-relaxed text-foreground/90">
              <span className="text-muted-foreground">$ </span>launch --agent research-assistant --task "MCP ecosystem brief"
              <span className="text-success">✓ run.start</span>             {"{"}task: "MCP ecosystem brief", snapshot: v1{"}"}
              <span className="text-primary">→ tool_call</span>             web_search (iter 1)
              <span className="text-muted-foreground">← tool_result</span>         12 results
              <span className="text-success">✓ verify</span>               source quality: safe
              <span className="text-muted-foreground">Σ cost</span>               $0.0012 · 1,842 tokens
              <span className="text-success">✓ run.end</span>              completed in 8.4s
            </pre>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-t border-border bg-card/40 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mb-12 text-center">
            <h2 className="text-3xl font-bold tracking-tight">Everything a factory needs</h2>
            <p className="mt-3 text-muted-foreground">
              Verification, budgets, gates, and memory — not just prompts.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div
                key={title}
                className="group rounded-lg border border-border bg-card p-6 transition-colors hover:border-primary/40"
              >
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/15 text-primary">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="mb-2 font-semibold">{title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="py-20">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mb-12 text-center">
            <h2 className="text-3xl font-bold tracking-tight">From zero to autonomous in four steps</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-4">
            {[
              { icon: Bot, step: "01", title: "Create an agent", text: "Pick a rank, write instructions, choose tools and model preferences." },
              { icon: CheckCheck, step: "02", title: "Set the gates", text: "Budget per day, iteration cap, and human-in-the-loop mode." },
              { icon: Terminal, step: "03", title: "Launch a run", text: "Stream every token, tool call, and verification live over SSE." },
              { icon: GitBranch, step: "04", title: "Iterate with memory", text: "Facts and history persist per agent — export and import bundles." },
            ].map(({ icon: Icon, step, title, text }) => (
              <div key={step} className="relative rounded-lg border border-border p-6">
                <span className="font-mono text-xs text-primary">{step}</span>
                <Icon className="my-3 h-5 w-5 text-muted-foreground" />
                <h3 className="mb-1.5 font-semibold">{title}</h3>
                <p className="text-sm text-muted-foreground">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border bg-card/40 py-20">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h2 className="text-3xl font-bold tracking-tight">Ready to start the line?</h2>
          <p className="mt-3 text-muted-foreground">
            Your first workspace and a starter research agent are seeded the
            moment you sign up.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            {user ? (
              <Link to="/app">
                <Button size="lg">
                  Go to Studio <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            ) : (
              <Link to="/auth?mode=signup">
                <Button size="lg">
                  Create your account <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            )}
          </div>
        </div>
      </section>

      <footer className="border-t border-border py-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 text-xs text-muted-foreground">
          <p>AgentFactory Studio · universal agentic factory</p>
          <p className="flex items-center gap-2">
            <GitBranch className="h-3 w-3" /> open, portable, self-hostable
          </p>
        </div>
      </footer>
    </div>
  );
}
