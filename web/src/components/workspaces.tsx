// Workspace context: loads /me, tracks the active workspace (persisted),
// and exposes helpers every page needs (workspace-scoped fetches).
import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { MeResponse, Workspace } from "../lib/types";
import { Spinner } from "./ui";

interface WorkspaceContextValue {
  me: MeResponse | null;
  workspace: Workspace | null;
  workspaces: Workspace[];
  setWorkspaceId: (id: string) => void;
  reload: () => Promise<void>;
  loading: boolean;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

const WS_KEY = "af_workspace_id";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const data = await api.get<MeResponse>("/api/v1/me");
      setMe(data);
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const workspace =
    me?.workspaces.find((w) => w.id === localStorage.getItem(WS_KEY)) ??
    me?.workspaces[0] ??
    null;

  const setWorkspaceId = (id: string) => {
    localStorage.setItem(WS_KEY, id);
    // Re-resolve from the already-loaded list without a network round-trip.
    setMe((prev) => (prev ? { ...prev } : prev));
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6 text-primary" />
      </div>
    );
  }

  return (
    <WorkspaceContext.Provider
      value={{
        me,
        workspace,
        workspaces: me?.workspaces ?? [],
        setWorkspaceId,
        reload: load,
        loading,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used inside <WorkspaceProvider>");
  return ctx;
}
