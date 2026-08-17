// Studio router — public landing + auth, and the protected /app shell.
import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth, useAuth } from "./components/auth";
import { WorkspaceProvider } from "./components/workspaces";
import { AppShell } from "./components/shell";
import { LandingPage } from "./pages/landing-page";
import { AuthPage } from "./pages/auth-page";
import { DashboardPage } from "./pages/dashboard-page";
import { AgentsPage } from "./pages/agents-page";
import { AgentDetailPage } from "./pages/agent-detail-page";
import { RunsPage } from "./pages/runs-page";
import { ApprovalsPage } from "./pages/approvals-page";
import { MemoryPage } from "./pages/memory-page";
import { ModelsPage } from "./pages/models-page";
import { SettingsPage } from "./pages/settings-page";

/** Already signed in? Skip the auth screen. */
function RedirectIfAuthed({ children }: { children: React.ReactNode }) {
  const { user, initializing } = useAuth();
  if (initializing) return null;
  if (user) return <Navigate to="/app" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />

          <Route
            path="/auth"
            element={
              <RedirectIfAuthed>
                <AuthPage />
              </RedirectIfAuthed>
            }
          />

          {/* Protected studio shell. AuthPage's redirectAfterAuth fallback is /app,
              and RequireAuth preserves ?returnTo= for deep links. */}
          <Route
            path="/app"
            element={
              <RequireAuth>
                <WorkspaceProvider>
                  <AppShell />
                </WorkspaceProvider>
              </RequireAuth>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="agents/:agentId" element={<AgentDetailPage />} />
            <Route path="runs" element={<RunsPage />} />
            <Route path="approvals" element={<ApprovalsPage />} />
            <Route path="memory" element={<MemoryPage />} />
            <Route path="models" element={<ModelsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
