// Shared types for the AgentFactory platform API (Phases 1–2).

export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  owner_user_id: string;
  settings: Record<string, unknown>;
  created_at: string;
  role?: string; // present in /me responses
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface MeResponse {
  user: User;
  workspaces: Workspace[];
}

export interface Member {
  user_id: string;
  role: "owner" | "admin" | "member";
  created_at: string;
  name: string | null;
  email: string;
  avatar_url: string | null;
}

export type HitlMode = "auto" | "gate";

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  rank: string;
  role_description: string | null;
  system_instructions: string | null;
  model_preferences: string[];
  tools: string[];
  skills: string[];
  mcp_servers: string[];
  temperature: number;
  max_budget_usd_per_day: number;
  hitl_mode: HitlMode;
  constitution: string[];
  guardrails: {
    protected_branches?: string[];
    path_allowlist?: string[];
  };
  max_iterations: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AgentRender {
  id: string;
  name: string;
  rank: string;
  system_prompt: string;
  tools: ToolManifestEntry[];
  model_preferences: string[];
  hitl_mode: HitlMode;
  max_iterations: number;
  max_budget_usd_per_day: number;
}

export interface ToolManifestEntry {
  name: string;
  description: string;
  parameters: { properties: Record<string, unknown>; required: string[] };
  safety: "safe" | "modified" | "destructive";
  category: string;
  cost_per_call_usd: number;
}

export type RunStatus =
  | "pending"
  | "pending_approval"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface Run {
  id: string;
  agent_id: string;
  workspace_id: string;
  task: string;
  status: RunStatus;
  result: string | null;
  stats: RunStats | null;
  error: string | null;
  config_snapshot: AgentRender | null;
  retries: number;
  created_at: string;
  updated_at: string;
}

export interface RunStats {
  iterations: number;
  tool_calls_made: number;
  total_cost_usd: number;
  total_tokens: number;
  duration_seconds: number;
  errors: number;
  successes: number;
  budget_usd: number;
}

export type ProposalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "modified"
  | "executed"
  | "cancelled";

export interface Proposal {
  id: string;
  workspace_id: string;
  agent_id: string | null;
  run_id: string | null;
  title: string;
  plan: string;
  status: ProposalStatus;
  decision_notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

// SSE run events (design.md §6)
export type RunEventType =
  | "run.start"
  | "token"
  | "tool_call"
  | "tool_result"
  | "verify"
  | "memory"
  | "cost"
  | "run.end"
  | "error";

export interface RunEvent {
  seq: number;
  event: RunEventType;
  data: Record<string, any>;
  ts: string;
}

export interface MemoryFacts {
  [key: string]: unknown;
}

export interface MemoryView {
  agent_id: string;
  workspace_id: string;
  history: Array<{ role: string; content: string; metadata: Record<string, unknown> }>;
  facts: MemoryFacts;
  stats: { message_count: number; first_seen: string | null; last_seen: string | null; agent_id: string };
}

export interface MemoryBundle {
  schema_version: number;
  workspace_id: string;
  agent_id: string;
  exported_at: string;
  history: Array<{ role: string; content: string }>;
  facts: MemoryFacts;
}

export interface ToolCatalogEntry {
  name: string;
  category: string;
  cost_per_call_usd: number;
  safety_level: "safe" | "modified" | "destructive";
  tags: string[];
  description: string;
}

// -------------------------------------------------------------------------
// Phase 4 — extensibility types (tools, skills, MCP, models, marketplace)
// -------------------------------------------------------------------------

export interface ToolEntry {
  name: string;
  category: string;
  cost_per_call_usd: number;
  safety_level: "safe" | "modified" | "destructive";
  tags: string[];
  description: string;
  source: "builtin" | "custom" | "marketplace";
  id?: string;
  enabled?: number;
  env_allow?: string[];
  metadata?: Record<string, unknown>;
}

export interface ValidationFinding {
  severity: "high" | "medium" | "low" | "info";
  message: string;
  line: number;
}

export interface ValidationResult {
  ok: boolean;
  passes: boolean;
  errors: string[];
  function_name: string | null;
  schema: Record<string, unknown> | null;
  findings: ValidationFinding[];
}

export interface SkillEntry {
  id: string;
  name: string;
  source: "builtin" | "custom" | "marketplace";
  metadata: {
    description?: string;
    instructions?: string;
    tools?: string[];
    dependencies?: string[];
    category?: string;
    tags?: string[];
    publisher?: string;
    version?: string;
  };
  enabled: number;
  created_at: string;
}

export interface MCPServer {
  id: string;
  name: string;
  transport: "stdio" | "sse";
  command: string | null;
  args: string[];
  url: string | null;
  env_allow: string[];
  timeout: number;
  enabled: number;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MCPTestResult {
  ok: boolean;
  error?: string;
  tools: Array<{ name: string; description: string; server: string }>;
  count: number;
}

export interface MCPDiscoveredTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown> | null;
  server?: string;
  enabled: boolean;
}

export interface MCPToolList {
  tools: MCPDiscoveredTool[];
  refreshed_at?: string | null;
}

export interface ModelConnection {
  id: string;
  provider: string;
  model: string;
  base_url: string | null;
  key_configured: boolean;
  enabled: number;
  created_at: string;
}

export interface TestCallResult {
  ok: boolean;
  error?: string;
  model?: string;
  reply?: string;
}

export interface MarketplaceItem {
  id: string;
  name: string;
  publisher: string;
  verified: boolean;
  version: string;
  safety_level?: string;
  category: string;
  description: string;
  transport?: string;
  command?: string;
  args?: string[];
}

export interface MarketplaceCatalog {
  tools: MarketplaceItem[];
  skills: MarketplaceItem[];
  mcp: MarketplaceItem[];
}

export interface MarketplaceInstall {
  id: string;
  item_type: string;
  item_id: string;
  item_name: string;
  publisher: string | null;
  status: string;
  findings: ValidationFinding[];
  created_at: string;
}

export const BUILTIN_TOOL_CATALOG: ToolCatalogEntry[] = [
  { name: "web_search", category: "web", cost_per_call_usd: 0, safety_level: "safe", tags: ["web", "search"], description: "Search the web (Tavily/DuckDuckGo)" },
  { name: "web_fetch", category: "web", cost_per_call_usd: 0, safety_level: "safe", tags: ["web", "fetch"], description: "Fetch and read a web page" },
  { name: "web_scrape_links", category: "web", cost_per_call_usd: 0, safety_level: "safe", tags: ["web", "scrape"], description: "Extract links from a page" },
  { name: "read_text_file", category: "file", cost_per_call_usd: 0, safety_level: "safe", tags: ["file", "read"], description: "Read text content from a file" },
  { name: "write_text_file", category: "file", cost_per_call_usd: 0, safety_level: "modified", tags: ["file", "write"], description: "Write or append text to a file" },
  { name: "list_directory_contents", category: "file", cost_per_call_usd: 0, safety_level: "safe", tags: ["file", "list"], description: "List directory contents" },
  { name: "search_files_by_pattern", category: "file", cost_per_call_usd: 0, safety_level: "safe", tags: ["file", "search"], description: "Search files by glob pattern" },
  { name: "count_lines_in_file", category: "file", cost_per_call_usd: 0, safety_level: "safe", tags: ["file", "count"], description: "Count lines in a file" },
  { name: "create_directory", category: "file", cost_per_call_usd: 0, safety_level: "modified", tags: ["file", "directory"], description: "Create a directory" },
  { name: "delete_file", category: "file", cost_per_call_usd: 0, safety_level: "destructive", tags: ["file", "delete"], description: "Delete a file (needs confirm)" },
  { name: "git_create_branch", category: "git", cost_per_call_usd: 0, safety_level: "safe", tags: ["git", "branch"], description: "Create and checkout a branch" },
  { name: "git_commit_changes", category: "git", cost_per_call_usd: 0, safety_level: "modified", tags: ["git", "commit"], description: "Commit changes" },
  { name: "git_push_branch", category: "git", cost_per_call_usd: 0, safety_level: "modified", tags: ["git", "push"], description: "Push the current branch" },
  { name: "git_check_status", category: "git", cost_per_call_usd: 0, safety_level: "safe", tags: ["git", "status"], description: "Git status" },
  { name: "git_create_pull_request", category: "git", cost_per_call_usd: 0, safety_level: "modified", tags: ["git", "pr"], description: "Create a pull request" },
  { name: "git_get_recent_commits", category: "git", cost_per_call_usd: 0, safety_level: "safe", tags: ["git", "log"], description: "Recent commit history" },
  { name: "git_switch_branch", category: "git", cost_per_call_usd: 0, safety_level: "safe", tags: ["git", "branch"], description: "Switch to an existing branch" },
  { name: "send_discord_notification", category: "notify", cost_per_call_usd: 0.001, safety_level: "safe", tags: ["notify", "discord"], description: "Send a Discord webhook notification" },
  { name: "send_gmail_notification", category: "notify", cost_per_call_usd: 0.001, safety_level: "safe", tags: ["notify", "email"], description: "Send an email via Gmail SMTP" },
  { name: "send_webhook_notification", category: "notify", cost_per_call_usd: 0, safety_level: "safe", tags: ["notify", "webhook"], description: "Send an arbitrary webhook notification" },
];

export const RANKS = ["Junior", "Senior", "QA", "Manager", "Custom"];
