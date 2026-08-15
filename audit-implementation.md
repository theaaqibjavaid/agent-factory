Phase: Audit Implementation Plan
Phase A: Critical Bug Fixes (Priority 1) — ~2 days
A1: Fix engineering_crew.py`

Remove or fix TieredEngineeringTeam class which references non-existent AgentFactory.create_runnable_agent()
Fix Verifier(repo_paths=REPO_PATHS) → just Verifier()
Fix verifier.run_full_verification() → use correct Verifier API
Files: agentfactory/agents/engineering_crew.py
A2: Fix worker.py`

Remove duplicate factory.create_agent("Senior") call at line 162
Use load_crew_config() to instantiate proper tiered agents from YAML
Files: agentfactory/agents/worker.py
A3: Fix ToolWrapper.execute()` async handling

Replace asyncio.get_event_loop() with asyncio.run() fallback for sync contexts
Files: agentfactory/base_tools.py:277-282
`A4: Update README directory structure

Update tree to match actual agentfactory/ package layout
Files: README.md
Phase B: Persistent Memory Layer (Priority 2) — ~3 days
B1: Add PersistentMemory` class

SQLite-backed conversation history per agent_id
Key-value fact storage
Session persistence across restarts
Files: agentfactory/memory.py (new)
B2: Integrate memory into RunnableAgent`

Add memory_id: str = None parameter
Load history on init, save after each turn
Add save_fact() / load_fact() methods
Files: agentfactory/base_agent.py
`B3: Add memory tools

@tool("save_memory") / @tool("recall_memory") for agent self-use
Files: agentfactory/tools/memory_tools.py (new)
`B4: Update config

Add MEMORY_DB_PATH to settings
Files: agentfactory/config.py, .env.example
Phase C: Streaming & Tool Calling (Priority 2) — ~4 days
C1: Add async streaming to FailoverLLMManager`

generate_streaming() method with async iterator
Provider-specific streaming support (ChatOpenAI, ChatGoogleGenerativeAI, ChatAnthropic)
Files: agentfactory/llm_manager.py
`C2: Add native tool calling support

Parse OpenAI-style tool_calls and Anthropic-style content_block → tool_use
Update RunnableAgent.\_parse_tool_calls() to handle structured formats
Files: agentfactory/base_agent.py, agentfactory/llm_manager.py
C3: Make generate_textcallable fromRunnableAgent`

Connect streaming to agent loop for real-time responses
Files: agentfactory/base_agent.py
Phase D: MCP Integration Fixes (Priority 3) — ~2 days
D1: Fix event loop handling in register_mcp_tools()`

Remove asyncio.new_event_loop() — use existing loop or asyncio.run()
Files: agentfactory/mcp_integration.py
`D2: Add async MCP registration

async_register_mcp_tools() for use within async agent code
Files: agentfactory/mcp_integration.py
Phase E: Skill Marketplace (Priority 3) — ~3 days
E1: Add Skill` dataclass

Name, tools list, system_instructions, metadata
Files: agentfactory/skills.py (new)
E2: Add SkillRegistry`

Load skills from installed packages via entry points
register_skill(), get_skill(), list_skills()
Files: agentfactory/skills.py
E3: Add skill loading to AgentFactory`

factory.load_skills_from_package("my_skills_package")
Files: agentfactory/base_agent.py
Phase F: Feedback Learning (Priority 4) — ~2 days
F1: Add learn_from_correction()` method

Store correction → solution pairs
Apply to future similar situations
Files: agentfactory/base_agent.py
Phase G: API Authentication (Priority 4) — ~2 days
`G1: Add JWT authentication

/api/auth/token endpoint
Protected endpoints require Authorization: Bearer <token>
Files: agentfactory/app/approval_server.py
Phase H: Documentation Updates (Ongoing)
Phase Docs to Update
B docs/memory.md — new
C [docs/api-reference.md] — streaming/tool calling
E docs/skills.md — new
F docs/learning.md — new
G [docs/approval-server.md] — auth
All Update docs/SUMMARY.md
Read C:\Users\Aaqib\Desktop\Agent-factory\agentfactory\base_tools.py
I have the file content from earlier. Let me start implementing the bug fixes:

Update Todos

A1: Fix engineering_crew.py — non-existent methods, Verifier API mismatch

A2: Fix worker.py — duplicate agent creation, use YAML configs

A3: Fix ToolWrapper.execute() async handling

A4: Update README directory structure

B: Add PersistentMemory class, integrate into RunnableAgent, add memory tools

C: Add streaming + native tool calling to FailoverLLMManager

D: Fix MCP event loop handling

E: Add Skill dataclass, SkillRegistry, package loading

F: Add learn_from_correction() to RunnableAgent

G: Add JWT auth to approval server

H: Update docs for all new features

Phase 5: Create separate personal team repo (blocked — awaits user approval)
