// Marketplace — curated catalog with trust indicators, one-click installs,
// and an audit trail (Phase 4.5).
import React, { useCallback, useEffect, useState } from "react";
import { BadgeCheck, Download, History, ShieldAlert, ShieldCheck, Store } from "lucide-react";
import { api } from "../lib/api";
import type { MarketplaceCatalog, MarketplaceInstall, MarketplaceItem } from "../lib/types";
import { cn, timeAgo } from "../lib/utils";
import { useWorkspace } from "../components/workspaces";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState, Skeleton, Tabs } from "../components/ui";

type Tab = "tools" | "skills" | "mcp";

export function MarketplacePage() {
  const { workspace } = useWorkspace();
  const [catalog, setCatalog] = useState<MarketplaceCatalog | null>(null);
  const [installs, setInstalls] = useState<MarketplaceInstall[]>([]);
  const [tab, setTab] = useState<Tab>("tools");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [cat, audit] = await Promise.all([
        api.get<{ catalog: MarketplaceCatalog }>("/api/v1/marketplace"),
        workspace ? api.get<{ installs: MarketplaceInstall[] }>(`/api/v1/workspaces/${workspace.id}/marketplace/installs`) : Promise.resolve({ installs: [] }),
      ]);
      setCatalog(cat.catalog);
      setInstalls(audit.installs);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load marketplace");
    }
  }, [workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const install = async (item: MarketplaceItem, type: Tab) => {
    if (!workspace) return;
    setBusy(item.id);
    try {
      await api.post(`/api/v1/workspaces/${workspace.id}/marketplace/install`, {
        item_type: type === "mcp" ? "mcp" : type,
        item_id: item.id,
      });
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Install failed");
    } finally {
      setBusy(null);
    }
  };

  const installedNames = new Set(
    installs.filter((i) => i.status === "installed").map((i) => i.item_name),
  );

  const sections: Array<{ key: Tab; label: string; items: MarketplaceItem[] }> = [
    { key: "tools", label: `Tools (${catalog?.tools.length ?? 0})`, items: catalog?.tools ?? [] },
    { key: "skills", label: `Skills (${catalog?.skills.length ?? 0})`, items: catalog?.skills ?? [] },
    { key: "mcp", label: `MCP servers (${catalog?.mcp.length ?? 0})`, items: catalog?.mcp ?? [] },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <Store className="h-6 w-6 text-primary" /> Marketplace
        </h1>
        <p className="text-sm text-muted-foreground">
          Curated tools, skills, and MCP servers. Every install is validated and audited.
        </p>
      </div>

      {error && <EmptyState title="Couldn't load marketplace" description={error} />}
      {!catalog && !error && <Skeleton className="h-64" />}

      {catalog && (
        <div className="space-y-6">
          <Tabs
            value={tab}
            onValueChange={(v) => setTab(v as Tab)}
            tabs={sections.map((s) => ({ value: s.key, label: s.label }))}
          />

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {sections.find((s) => s.key === tab)?.items.map((item) => {
              const installed = installedNames.has(item.name);
              return (
                <Card key={item.id}>
                  <div className="p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="flex items-center gap-1.5 font-semibold">
                          {item.name}
                          {item.verified && (
                            <BadgeCheck className="h-4 w-4 text-success" aria-label="Verified publisher" />
                          )}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {item.publisher} · v{item.version}
                        </p>
                      </div>
                      {item.safety_level && (
                        <Badge
                          tone={item.safety_level === "safe" ? "success" : item.safety_level === "modified" ? "warning" : "destructive"}
                        >
                          {item.safety_level}
                        </Badge>
                      )}
                    </div>
                    <p className="mt-2 line-clamp-2 min-h-8 text-sm text-muted-foreground">{item.description}</p>
                    {tab === "mcp" && (
                      <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
                        {item.command} {item.args?.join(" ")}
                      </p>
                    )}
                    <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        {item.verified ? (
                          <><ShieldCheck className="h-3 w-3 text-success" /> verified</>
                        ) : (
                          <><ShieldAlert className="h-3 w-3 text-warning" /> community</>
                        )}
                      </span>
                      <Button
                        size="sm"
                        variant={installed ? "secondary" : "primary"}
                        disabled={installed}
                        loading={busy === item.id}
                        onClick={() => install(item, tab)}
                      >
                        <Download className="h-3.5 w-3.5" />
                        {installed ? "Installed" : "Install"}
                      </Button>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>

          {/* Audit trail */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <History className="h-4 w-4 text-muted-foreground" /> Install audit
                </CardTitle>
                <CardDescription>Every install is recorded with its validation findings.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {installs.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  No installs in this workspace yet.
                </p>
              ) : (
                <div className="divide-y divide-border">
                  {installs.slice(0, 10).map((i) => (
                    <div key={i.id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {i.item_name}
                          <Badge tone="muted" className="ml-2">{i.item_type}</Badge>
                          {i.publisher && <span className="ml-2 text-xs text-muted-foreground">{i.publisher}</span>}
                        </p>
                        <p className="text-xs text-muted-foreground">{timeAgo(i.created_at)}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {i.findings.length > 0 && (
                          <Badge tone={i.findings.some((f) => f.severity === "high") ? "destructive" : "warning"}>
                            {i.findings.length} findings
                          </Badge>
                        )}
                        <Badge tone={i.status === "installed" ? "success" : "destructive"}>{i.status}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
