# Odoo Telegram Integration

Odoo 18 modules that turn your Odoo instance into a **Telegram bot with AI-powered chat**, REST API, and MCP server — all running natively inside Odoo with zero external services.

## Features

- **AI Chat via Telegram** — Ask questions in natural language, get answers from your Odoo data
- **Function Calling** — The AI autonomously queries Odoo models (sales, inventory, projects, etc.)
- **Webhook-based** — No polling, no separate Python process, just an Odoo controller
- **REST API** — External tools can query Odoo via authenticated API endpoints
- **MCP Server** — IDE integration (Claude Code, Cursor, Windsurf) via Model Context Protocol
- **Permission System** — Hierarchical groups (Admin > Dev > Freela) with chat-level restrictions
- **Message Logging** — Full audit trail of bot interactions with token usage tracking

## Modules

| Module | Description |
|--------|-------------|
| `telegram_base` | User fields (`telegram_id`), chat model, security groups, AI provider config |
| `telegram_bot` | Webhook controller, AI chat with function calling via ORM, message logging, dashboard |
| `telegram_api` | REST API controllers for external integrations (Bearer token auth) |
| `telegram_mcp` | MCP server (Streamable HTTP) for IDE integration |

## Architecture

```
Telegram ──webhook──> Odoo (telegram_bot controller)
                        ├── AI Provider (DeepSeek/Qwen/OpenAI)
                        │     └── Function Calling ──> Odoo ORM (direct)
                        ├── Message Log (telegram.message)
                        └── Permission Check (res.groups)

IDE (Claude Code) ──MCP──> Odoo (telegram_mcp controller)
                             └── Tools ──> Odoo ORM (direct)

External App ──REST──> Odoo (telegram_api controller)
                         └── Bearer Token ──> res.users.telegram_api_token
```

**Key insight:** Since the bot runs *inside* Odoo, there's no XML-RPC overhead. Tool calls go directly through the ORM with full security context.

## Installation

### Via Doodba (recommended)

Add to your `repos.yaml`:

```yaml
./softhill-odoo-telegram:
  defaults:
    depth: $DEPTH_DEFAULT
  remotes:
    origin: https://github.com/softhill/softhill-odoo-telegram.git
  target: origin main
  merges:
    - origin main
```

Add to your `addons.yaml`:

```yaml
softhill-odoo-telegram:
  - telegram_base
  - telegram_bot
  - telegram_api    # optional
  - telegram_mcp    # optional
```

### Manual

Copy the module directories to your Odoo addons path and install via the Apps menu.

## Configuration

1. Install the modules via **Apps** menu
2. Go to **Settings > Telegram**
3. Configure:
   - **Bot Token** — Get from [@BotFather](https://t.me/BotFather)
   - **Webhook Secret** — Random string for webhook validation
   - **AI Provider** — DeepSeek (recommended), Qwen, or OpenAI
   - **AI API Key** — From your AI provider
4. Go to **Telegram > Configuration > Set Webhook**
5. Assign users to Telegram groups (Admin/Dev/Freela) in **Settings > Users**

## AI Providers

| Provider | Model | Cost (1M tokens in/out) | Function Calling |
|----------|-------|------------------------|------------------|
| **DeepSeek** | deepseek-chat | $0.28 / $0.42 | Good (81.5%) |
| **Qwen** | qwen-plus | $0.40 / $1.20 | Better (96.5%) |
| **OpenAI** | gpt-4o-mini | $0.15 / $0.60 | Excellent |

## MCP Integration

Add to your Claude Code config (`~/.claude/claude_code_config.json`):

```json
{
  "mcpServers": {
    "odoo": {
      "type": "streamable-http",
      "url": "https://your-odoo.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_TOKEN"
      }
    }
  }
}
```

Generate API tokens in **Settings > Users > [user] > Telegram tab**.

## Security

- Webhook validates `X-Telegram-Bot-Api-Secret-Token` header
- REST API uses Bearer token authentication linked to Odoo users
- Three permission levels with hierarchical inheritance
- Freela users can only see their own data (automatic ORM filtering)
- All interactions are logged in `telegram.message`

## License

LGPL-3 — Same as Odoo Community.

## Credits

Developed by [Softhill](https://softhill.com.br) for the Odoo community.
