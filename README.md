# Odoo Telegram Integration

Odoo 18 modules that turn your Odoo instance into a **Telegram bot with AI-powered chat**, REST API, and MCP server — all running natively inside Odoo with zero external services.

## Features

- **AI Chat via Telegram** — Ask questions in natural language, get answers from your Odoo data
- **Function Calling** — The AI autonomously queries and modifies Odoo (sales, inventory, projects, etc.)
- **30+ Built-in Tools** — From generic CRUD to high-level business actions (sales summary, pipeline CRM, log timesheets, etc.)
- **Write Operations** — Create sales orders, contacts, post messages, execute actions — with confirmation flow for dangerous operations
- **GitHub Integration** — Read files, search code, list commits and PRs from your GitHub repos
- **Dynamic Tool Registry** — Tools are Odoo records (`telegram.tool`), configurable via UI — no code changes needed to add/remove tools
- **Webhook-based** — No polling, no separate Python process, just an Odoo controller
- **REST API** — External tools can query Odoo via authenticated API endpoints
- **MCP Server** — IDE integration (Claude Code, Cursor, Windsurf) via Model Context Protocol
- **Permission System** — Hierarchical groups (Admin > Dev > Freela) with per-tool and per-chat restrictions
- **Analytics Dashboard** — Cost tracking per user, token usage, response times, tool usage stats
- **Message Logging** — Full audit trail of bot interactions with token usage and cost estimation

## Modules

| Module | Description |
|--------|-------------|
| `telegram_base` | User fields (`telegram_id`), chat model, security groups, AI provider config, GitHub config |
| `telegram_bot` | Webhook controller, AI chat with function calling, tool registry, analytics, confirmation flow |
| `telegram_api` | REST API controllers for external integrations (Bearer token auth) |
| `telegram_mcp` | MCP server (Streamable HTTP) for IDE integration — tools loaded dynamically from registry |

## Architecture

```
Telegram ──webhook──> Odoo (telegram_bot controller)
                        ├── AI Provider (DeepSeek/Qwen/OpenAI)
                        │     └── Function Calling ──> telegram.tool registry ──> ORM
                        ├── Confirmation Flow (inline keyboard for write ops)
                        ├── GitHub API (read repos, code, commits, PRs)
                        ├── Message Log (telegram.message) + Analytics
                        └── Permission Check (res.groups + telegram.chat)

IDE (Claude Code) ──MCP──> Odoo (telegram_mcp controller)
                             └── telegram.tool registry ──> ORM

External App ──REST──> Odoo (telegram_api controller)
                         └── Bearer Token ──> res.users.telegram_api_token
```

**Key insight:** Since the bot runs *inside* Odoo, there's no XML-RPC overhead. Tool calls go directly through the ORM with full security context.

## Available Tools

### Generic Tools (14 built-in)

Low-level tools that work with any Odoo model:

| Tool | Description | Permission |
|------|-------------|:---:|
| `search_odoo` | Search records in any model with domain filters | Freela |
| `count_odoo` | Count records matching a domain | Freela |
| `read_record` | Read a single record by ID | Freela |
| `get_fields` | Get field definitions for any model | Freela |
| `create_record` | Create records in any model | Dev+ |
| `update_record` | Update fields on existing records | Dev+ |
| `execute_action` | Run actions (confirm sale, validate picking, etc.) | Dev+ |
| `delete_record` | Delete a record (always requires confirmation) | Admin |
| `post_message` | Post to the chatter of any record | Dev+ |
| `github_list_repos` | List repos in your GitHub org | Dev+ |
| `github_read_file` | Read file contents from a repo | Dev+ |
| `github_search_code` | Search code across repos | Dev+ |
| `github_list_commits` | List recent commits | Dev+ |
| `github_list_prs` | List pull requests | Dev+ |

### Core Odoo Tools (16 built-in)

High-level convenience tools for common business operations. These work out of the box with core Odoo modules — no need to know model names or fields:

#### Sales

| Tool | Description | Permission |
|------|-------------|:---:|
| `sales_summary` | Sales summary with totals, counts and top customers. Filter by period and state. *"Quanto vendemos esse mes?"* | Freela |
| `create_quotation` | Create a quotation with product lines. Resolves partner and products by name. | Dev+ |

#### Invoicing

| Tool | Description | Permission |
|------|-------------|:---:|
| `invoicing_summary` | Invoicing summary: total billed, receivables, overdue amounts, top debtors. *"Quanto temos a receber?"* | Dev+ |

#### CRM

| Tool | Description | Permission |
|------|-------------|:---:|
| `crm_pipeline` | Pipeline overview: opportunities by stage, expected revenue, recent leads. *"Como esta o pipeline?"* | Freela |
| `create_lead` | Create a lead or opportunity in CRM. | Dev+ |

#### Projects & Timesheets

| Tool | Description | Permission |
|------|-------------|:---:|
| `project_summary` | Project overview: tasks by stage, overdue tasks, logged hours. *"Quantas horas registrei?"* | Freela |
| `log_timesheet` | Log worked hours on a task. Resolves task by name. *"Registra 2h na tarefa X"* | Freela |
| `create_task` | Create a task in a project with assignee and deadline. | Dev+ |

#### Contacts

| Tool | Description | Permission |
|------|-------------|:---:|
| `find_contact` | Search contacts by name, email, phone or VAT. Returns full data including sales info. | Freela |
| `create_contact` | Create a contact (person or company) with address, VAT, etc. | Dev+ |

#### Purchase

| Tool | Description | Permission |
|------|-------------|:---:|
| `purchase_summary` | Purchase summary: order count, amounts, pending orders, top suppliers. | Dev+ |

#### Inventory

| Tool | Description | Permission |
|------|-------------|:---:|
| `stock_levels` | Stock levels by product. Filter by low stock, warehouse. *"Quanto temos de [produto]?"* | Dev+ |
| `stock_moves` | Recent stock moves (incoming, outgoing, internal). | Dev+ |

#### HR

| Tool | Description | Permission |
|------|-------------|:---:|
| `employees` | Employee list with department, job, manager info. | Dev+ |
| `expenses` | Expense overview: pending, approved, paid. Filter by employee and period. | Freela |

#### Calendar

| Tool | Description | Permission |
|------|-------------|:---:|
| `calendar` | Calendar events for a period. *"O que tenho na agenda hoje?"* | Freela |
| `create_event` | Create a calendar event with attendees. | Dev+ |

### Adding Custom Tools

Tools are Odoo records. You can add new tools via:
1. **UI** — Go to Telegram > Configuration > Tools and create a new record
2. **XML data** — Add `<record id="..." model="telegram.tool">` in your module's data files
3. **New module** — Create a module that depends on `telegram_bot` and adds tools + methods

Each tool record defines: name, description, JSON schema, method name, permission level, and whether it requires confirmation. The Python method goes on `telegram.ai.chat` (inherit the AbstractModel in your module).

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
   - **AI Provider** — DeepSeek (recommended), Qwen, or OpenAI-compatible
   - **AI API Key** — From your AI provider
   - **GitHub Token** — (optional) For repository access tools
   - **GitHub Org** — Default organization name
4. Go to **Telegram > Configuration > Set Webhook**
5. Assign users to Telegram groups (Admin/Dev/Freela) in **Settings > Users**
6. Review available tools in **Telegram > Configuration > Tools**

### MCP Setup (IDE Integration)

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

Works with Claude Code, Cursor, Windsurf, and any MCP-compatible IDE.

### REST API

External tools can query Odoo directly:

```bash
# Count orders
curl -X POST https://your-odoo.com/mcp \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
    "name":"sales_summary",
    "arguments":{"period":"month"}
  }}'
```

## AI Providers

Any OpenAI-compatible API works. Tested with:

| Provider | Model | Cost (1M tokens in/out) | Function Calling |
|----------|-------|------------------------|------------------|
| **DeepSeek** | deepseek-chat | $0.14 / $0.28 | Good |
| **Qwen** | qwen-plus | $0.80 / $2.00 | Better |
| **OpenAI** | gpt-4o-mini | $0.15 / $0.60 | Excellent |

## Analytics

The bot tracks every interaction with full metrics:

- **Token usage** — Input/output tokens per message
- **Cost estimation** — Automatic cost calculation based on model pricing
- **Response time** — Processing time per request
- **Tool usage** — Which tools are called and how often
- **Error rate** — Track failures and slow responses

Access analytics via **Telegram > Analytics** in the Odoo menu, with graph views, pivot tables, and advanced filters.

## Security

- Webhook validates `X-Telegram-Bot-Api-Secret-Token` header
- REST API and MCP use Bearer token authentication linked to Odoo users
- Three permission levels with hierarchical inheritance
- Tool-level permission gating (each tool defines minimum required level)
- Write operations to financial models require explicit user confirmation via Telegram buttons
- System models (ir.model, ir.rule, etc.) are blocked from modification
- Method whitelist for `execute_action` prevents arbitrary code execution
- Freela users can only see their own data (automatic ORM filtering)
- All interactions are logged in `telegram.message` with full audit trail

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add your changes (new tools, views, etc.)
4. Submit a pull request

New tools can be contributed as:
- Additional tool records in XML data files
- New `_tool_*` methods on `telegram.ai.chat`
- Separate Odoo modules that extend the tool registry

## License

LGPL-3 — Same as Odoo Community.

## Credits

Developed by [Softhill](https://softhill.com.br) for the Odoo community.
