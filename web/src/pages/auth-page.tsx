// Auth page — split-screen brand panel + credentials form (design.md §5).
import React, { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Bot, Lock, ShieldCheck, Zap } from "lucide-react";
import { api } from "../lib/api";
import type { TokenPair } from "../lib/types";
import { useAuth } from "../components/auth";
import { Button, Card, Field, Input, Tabs } from "../components/ui";

const FEATURES = [
  { icon: Zap, text: "Multi-model agent loops with automatic failover" },
  { icon: ShieldCheck, text: "Human-in-the-loop gates for destructive actions" },
  { icon: Zap, text: "Built-in tools, skills, and MCP marketplace" },
];

export function AuthPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = params.get("returnTo") || "/app";

  const [mode, setMode] = useState<"signin" | "signup">(
    params.get("mode") === "signup" ? "signup" : "signin",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const tokens = await api.post<TokenPair>(
        mode === "signin" ? "/api/v1/auth/login" : "/api/v1/auth/signup",
        mode === "signin" ? { email, password } : { email, password, name: name || null },
      );
      signIn(tokens);
      navigate(returnTo, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-border bg-card p-10 lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            background:
              "radial-gradient(60rem 30rem at 20% 0%, hsl(var(--primary) / 0.14), transparent 60%), radial-gradient(40rem 24rem at 90% 100%, hsl(var(--accent) / 0.25), transparent 60%)",
          }}
        />
        <div className="relative flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Bot className="h-6 w-6" />
          </div>
          <div>
            <p className="text-lg font-bold tracking-tight">AgentFactory</p>
            <p className="text-xs text-muted-foreground">Universal agentic factory</p>
          </div>
        </div>

        <div className="relative space-y-6">
          <h1 className="max-w-md text-4xl font-extrabold leading-tight tracking-tight">
            Build agents. Ship autonomy.
            <span className="block bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              Own the factory floor.
            </span>
          </h1>
          <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
            Compose tools, skills, MCP servers, and models into full agentic
            loops — with verification, budgets, and human-in-the-loop gates.
          </p>
          <ul className="space-y-3">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sm">
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/15 text-primary">
                  <Icon className="h-4 w-4" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-muted-foreground">
          <Lock className="mr-1 inline h-3 w-3" />
          Argon2id hashing · rotating refresh tokens · workspace isolation
        </p>
      </div>

      {/* Form panel */}
      <div className="flex w-full flex-col items-center justify-center px-6 py-12 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Bot className="h-5 w-5" />
            </div>
            <p className="text-lg font-bold">AgentFactory</p>
          </div>

          <h2 className="text-2xl font-bold tracking-tight">
            {mode === "signin" ? "Welcome back" : "Start the assembly line"}
          </h2>
          <p className="mt-1 mb-6 text-sm text-muted-foreground">
            {mode === "signin"
              ? "Sign in to your workspace."
              : "Create your account — a starter workspace and agent are seeded automatically."}
          </p>

          <Tabs
            value={mode}
            onValueChange={(v) => {
              setMode(v as "signin" | "signup");
              setError(null);
            }}
            tabs={[
              { value: "signin", label: "Sign in" },
              { value: "signup", label: "Sign up" },
            ]}
            className="mb-5 w-full"
          />

          <form onSubmit={submit} className="space-y-4">
            {mode === "signup" && (
              <Field label="Name (optional)">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ada Lovelace"
                  autoComplete="name"
                />
              </Field>
            )}
            <Field label="Email">
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                autoComplete="email"
              />
            </Field>
            <Field label="Password">
              <Input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
              />
            </Field>

            {error && (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" loading={loading} className="w-full" size="lg">
              {mode === "signin" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            Prefer to explore first?{" "}
            <Link to="/" className="text-primary hover:underline">
              Back to the landing page
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
