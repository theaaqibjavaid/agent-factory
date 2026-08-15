# Project

## gstack

This project uses [gstack](https://github.com/garrytan/gstack) — a suite of AI engineering skills for Claude Code.

**Web browsing:** Always use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools — they are slow, unreliable, and not what this project uses.

### Available skills

| Skill | Description |
|-------|-------------|
| `/office-hours` | YC Office Hours — startup diagnostic + builder brainstorm |
| `/plan-ceo-review` | CEO-level feature idea review and planning |
| `/plan-eng-review` | Engineering architecture review |
| `/plan-design-review` | Design system and plan review |
| `/design-consultation` | Design system from scratch |
| `/design-shotgun` | Visual design exploration |
| `/design-html` | HTML design generation |
| `/review` | Code review and PR analysis |
| `/ship` | Ship workflow — merge, deploy, canary verify |
| `/land-and-deploy` | Land branch and deploy |
| `/canary` | Post-deploy monitoring loop |
| `/benchmark` | Performance regression detection |
| `/browse` | Headless browser CLI (Playwright) — use for all web browsing |
| `/connect-chrome` | Connect to Chrome for browser automation |
| `/qa` | Full QA with fixes — run against staging URL |
| `/qa-only` | Report-only QA — no fixes, just findings |
| `/design-review` | Design audit + fix loop |
| `/setup-browser-cookies` | Set up browser cookies for testing |
| `/setup-deploy` | One-time deploy configuration |
| `/setup-gbrain` | Set up gbrain (AI memory layer) |
| `/retro` | Retrospective — analyze what happened, capture learnings |
| `/investigate` | Systematic root-cause debugging |
| `/document-release` | Post-ship documentation updates |
| `/document-generate` | Diataxis doc generator |
| `/codex` | Multi-AI second opinion via OpenAI Codex CLI |
| `/cso` | OWASP Top 10 + STRIDE security audit |
| `/autoplan` | Auto-review pipeline: CEO → design → eng |
| `/plan-devex-review` | Developer experience review |
| `/devex-review` | Developer experience review (alternate) |
| `/careful` | Careful mode — extra scrutiny on AI-generated code |
| `/freeze` | Freeze environment for reproducible evaluation |
| `/guard` | Guard — security and quality gate |
| `/unfreeze` | Unfreeze environment |
| `/gstack-upgrade` | Upgrade gstack to latest version |
| `/learn` | Capture learnings from completed work |
