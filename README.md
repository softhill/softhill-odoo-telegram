# Odoo Telegram Bot + AI Assistant

**Give your team a fast lane into Odoo — right from Telegram.**

Quick answers, instant actions, zero context switching. The bot brings Odoo data to where your team already is: their chat app. It doesn't replace Odoo — it makes Odoo more accessible.

> **You:** How much did we sell this month?
>
> **Bot:** 📊 Sales Summary (March 2026)
> - 47 confirmed orders
> - Total: $142,350.00
> - Top customer: Acme Corp ($28,400)
> - Avg order value: $3,028.72

> **You:** Create a quote for Acme Corp — 50 units of Premium Widget at $89 each
>
> **Bot:** ✅ Quotation S00048 created
> - Customer: Acme Corp
> - 50x Premium Widget @ $89.00 = $4,450.00
> - [Open in Odoo →]

> **You:** Who has overdue invoices?
>
> **Bot:** ⚠️ 3 overdue invoices totaling $12,840.00
> - INV/2026/0087 — Beta Industries — $5,200 (23 days overdue)
> - INV/2026/0091 — GlobalTech — $4,140 (12 days overdue)
> - INV/2026/0095 — NovaCorp — $3,500 (5 days overdue)

> **You:** Log 3 hours on the "Website Redesign" task — finished the responsive layout
>
> **Bot:** ✅ Timesheet logged
> - Task: Website Redesign
> - 3.0 hours on 2026-03-06
> - Description: Finished the responsive layout

The bot runs **inside Odoo** as native modules. No XML-RPC, no middleware, no separate server — it uses the ORM directly with full security context. Install, configure your Telegram token and AI provider, and your team is running in minutes.

---

## Why Use This?

**For your team:**

Your sales reps check pipeline status from their phone between meetings. Your finance team gets a quick overdue report without switching apps. Your developers log timesheets from the terminal. Your project managers get a task summary while commuting.

The bot is a **fast lane** — not a replacement for Odoo. For detailed work, open Odoo. For quick data and simple actions, just ask the bot.

**For you as admin:**

- Every interaction is logged with token usage and cost estimation
- **Configurable user profiles** — not just "admin/user" but "Sales Rep", "External Consultant", "Warehouse Operator", or whatever fits your organization
- Each tool can be restricted to specific profiles or permission levels
- Write operations on financial data require explicit confirmation
- Sensitive models and fields are automatically protected
- MCP endpoint lets your IDE (Claude Code, Cursor, Windsurf) query Odoo directly
- REST API for scripts and external integrations

---

## 44 Built-in Tools

The bot ships with **44 tools** out of the box, organized in two layers:

### Layer 1: Generic ORM Tools (14 tools)

Low-level tools that work with **any** Odoo model. Power users and developers can query anything:

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `search_odoo` | Search any model with domain filters | User |
| `count_odoo` | Count records matching criteria | User |
| `read_record` | Read a single record by ID | User |
| `get_fields` | Discover fields of any model | User |
| `create_record` | Create records in any model | Manager |
| `update_record` | Update existing records | Manager |
| `execute_action` | Run actions (confirm, validate, post, etc.) | Manager |
| `delete_record` | Delete records (always requires confirmation) | Admin |
| `post_message` | Post to chatter of any record | Manager |
| `github_list_repos` | List repos in your GitHub org | Manager |
| `github_read_file` | Read file contents from repos | Manager |
| `github_search_code` | Search code across repos | Manager |
| `github_list_commits` | Recent commits from any repo | Manager |
| `github_list_prs` | Pull requests (open, closed, all) | Manager |

### Layer 2: Business Tools (30 tools)

High-level tools for common operations. Users don't need to know model names or field names — just describe what they want:

#### Sales & Invoicing

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `sales_summary` | Revenue totals, order counts, top customers by period | User |
| `sales_by_product` | Best-selling products ranked by revenue or quantity | Manager |
| `sales_by_salesperson` | Salesperson ranking by revenue | Manager |
| `create_quotation` | Create quotation with product lines — resolves names automatically | Manager |
| `invoicing_summary` | Billed vs. receivable vs. overdue, top debtors | Manager |
| `overdue_invoices` | List overdue invoices with days past due | Manager |
| `create_invoice` | Create customer or vendor invoice | Admin |
| `register_payment` | Register payment on a posted invoice | Admin |

#### CRM

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `crm_pipeline` | Opportunities by stage, expected revenue, recent leads | User |
| `create_lead` | Create a lead or opportunity | Manager |

#### Projects & Timesheets

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `project_summary` | Tasks by stage, overdue tasks, logged hours | User |
| `log_timesheet` | Log worked hours on a task by name | User |
| `create_task` | Create task in a project with assignee and deadline | Manager |

#### Contacts

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `find_contact` | Search by name, email, phone, VAT — returns full profile | User |
| `create_contact` | Create person or company with address, VAT, etc. | Manager |

#### Purchase & Inventory

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `purchase_summary` | Purchase totals, pending orders, top suppliers | Manager |
| `create_purchase_order` | Create RFQ with product lines | Manager |
| `stock_levels` | Stock by product, low stock alerts, warehouse filter | Manager |
| `stock_moves` | Recent stock movements (in, out, internal) | Manager |
| `find_product` | Search products by name, code, or barcode | User |
| `create_product` | Create a new product | Manager |

#### HR & Expenses

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `employees` | Employee list with department, job, manager | Manager |
| `expenses` | Expense overview by status and period | User |
| `create_expense` | Create expense entry for approval | User |
| `recruitment` | Open positions and applicant count | Manager |

#### Calendar & Messaging

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `calendar` | Upcoming events and meetings | User |
| `create_event` | Create calendar event with attendees | Manager |
| `send_message` | Send internal message via Odoo Discuss | User |

#### System

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `installed_modules` | List installed Odoo modules and apps | Manager |
| `system_info` | Odoo version, database, user count, record stats | Admin |
| `user_activity` | User last login, activity tracking | Admin |
| `events` | Website events with registration info | User |

---

## Architecture

```
Telegram ──webhook──> Odoo (telegram_bot)
                        ├── AI Provider (DeepSeek / Qwen / OpenAI / any compatible)
                        │     └── Function Calling ──> Tool Registry ──> ORM
                        ├── Confirmation Flow (inline keyboard for write ops)
                        ├── GitHub API integration
                        ├── Message Log + Analytics
                        └── Permission Check (groups + chat-level)

IDE ──────── MCP ────> Odoo (telegram_mcp)
                         └── Same tool registry, same permissions

Scripts ─── REST ────> Odoo (telegram_api)
                         └── Bearer token ──> res.users
```

Since the bot runs **inside Odoo**, tool calls go directly through the ORM — no XML-RPC overhead, no serialization, no external processes.

### Modules

| Module | Required | Description |
|--------|:--------:|-------------|
| `telegram_base` | Yes | User fields, security groups, AI provider config, GitHub config |
| `telegram_bot` | Yes | Webhook, AI chat, function calling, tool registry, analytics |
| `telegram_api` | No | REST API for external integrations (Bearer token auth) |
| `telegram_mcp` | No | MCP server (Streamable HTTP) for IDE integration |

---

## Installation

### Standard Odoo

```bash
# Clone into your addons directory
cd /path/to/odoo/addons
git clone https://github.com/softhill/softhill-odoo-telegram.git
```

Add to your `odoo.conf`:

```ini
addons_path = /path/to/odoo/addons,/path/to/softhill-odoo-telegram
```

Restart Odoo, go to **Apps**, search for "Telegram", and install **Telegram Base** + **Telegram Bot**.

### Doodba / Docker

Add to `repos.yaml`:

```yaml
./softhill-odoo-telegram:
  defaults:
    depth: $DEPTH_DEFAULT
  remotes:
    origin: https://github.com/softhill/softhill-odoo-telegram.git
  target: origin dev
  merges:
    - origin dev
```

Add to `addons.yaml`:

```yaml
softhill-odoo-telegram:
  - telegram_base
  - telegram_bot
  - telegram_api    # optional
  - telegram_mcp    # optional
```

### Git Submodule

```bash
git submodule add https://github.com/softhill/softhill-odoo-telegram.git
```

---

## Configuration

1. Go to **Settings > Telegram**
2. Set your **Bot Token** (from [@BotFather](https://t.me/BotFather))
3. Set a **Webhook Secret** (random string for validation)
4. Configure your **AI Provider** — DeepSeek (cheapest), Qwen, OpenAI, or any compatible API
5. (Optional) Add **GitHub Token** for repo access tools
6. Click **Set Webhook** in **Telegram > Configuration**
7. Assign users to groups (**Admin / Dev / Freela**) in Settings > Users
8. Review tools in **Telegram > Configuration > Tools** — enable or disable as needed

### AI Providers

Any OpenAI-compatible API works. Tested providers:

| Provider | Model | Cost (1M tokens in/out) | Quality |
|----------|-------|:-----------------------:|:-------:|
| **DeepSeek** | deepseek-chat | $0.14 / $0.28 | Good |
| **Qwen** | qwen-plus | $0.80 / $2.00 | Better |
| **OpenAI** | gpt-4o-mini | $0.15 / $0.60 | Excellent |

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

Works with **Claude Code**, **Cursor**, **Windsurf**, and any MCP-compatible IDE. Generate API tokens in **Settings > Users > [user] > Telegram tab**.

### REST API

```bash
# Example: Get sales summary for this month
curl -X POST https://your-odoo.com/mcp \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
    "name":"sales_summary",
    "arguments":{"period":"month"}
  }}'
```

---

## Permission System

### User Profiles (Configurable)

The bot includes a **configurable user profile system** (`telegram.user.profile`). Profiles define what each type of user can do — and you can create as many as your organization needs:

| Profile | Sequence | Example tools | Your use case |
|---------|:--------:|---------------|---------------|
| User | 10 | Calendar, contacts, timesheets | Employees, interns |
| Manager | 50 | CRM, projects, purchases, products | Team leads, managers |
| Admin | 100 | Invoicing, payments, system, delete | CFO, IT admin |

**Need more profiles?** Create them in **Telegram > Configuration > User Profiles**:

- "Sales Rep" (sequence 20) — access to CRM + quotations but not invoicing
- "External Consultant" (sequence 15) — timesheets and their own projects only
- "Warehouse Operator" (sequence 30) — stock levels and moves only
- "Finance" (sequence 80) — invoicing tools but not system admin

Each tool can be restricted to specific profiles via the `Allowed Profiles` field. If no profiles are set on a tool, it falls back to the legacy 3-tier permission level (User < Manager < Admin).

Profiles can be auto-assigned via Odoo groups or set explicitly per user.

### Security

- Write operations on financial models require **explicit confirmation** via Telegram buttons
- Sensitive models (`ir.rule`, `res.users`, `ir.config_parameter`, etc.) are **blocked** from modification
- Sensitive fields (`password`, `token`, `api_key`) are **automatically stripped** from search results
- Users at the base level cannot use generic search tools on financial/HR models
- All interactions are logged in `telegram.message` with full audit trail

---

## Analytics & Monitoring

Every bot interaction is logged with:

- **Token usage** — input/output tokens per message
- **Cost estimation** — automatic based on model pricing
- **Response time** — processing time per request
- **Tool usage** — which tools are called, how often, by whom
- **Error tracking** — failures and slow responses

Access via **Telegram > Analytics** with graph views, pivot tables, and filters.

---

## Security

- Webhook validates `X-Telegram-Bot-Api-Secret-Token` header
- REST API and MCP use Bearer token authentication linked to Odoo users
- Tool-level permission gating — each tool defines its minimum required level
- Write operations on financial models require user confirmation via Telegram buttons
- System models (`ir.model`, `ir.rule`, etc.) are blocked from modification
- Method whitelist for `execute_action` prevents arbitrary code execution
- Full audit trail in `telegram.message`

---

## Adding Custom Tools

Tools are Odoo records (`telegram.tool`). Three ways to add your own:

### 1. Via UI (no code)

Go to **Telegram > Configuration > Tools**, create a record with name, description, JSON schema, method name, and permission level.

### 2. Via XML data

```xml
<record id="tool_my_report" model="telegram.tool">
    <field name="name">my_report</field>
    <field name="display_name_field">My Custom Report</field>
    <field name="description">Returns custom report data...</field>
    <field name="category">read</field>
    <field name="method_name">_tool_my_report</field>
    <field name="permission_level">freela</field>
    <field name="input_schema">{"type": "object", "properties": {...}}</field>
</record>
```

### 3. Via Python (inherit the AbstractModel)

```python
from odoo import models

class AIChatCustom(models.AbstractModel):
    _inherit = "telegram.ai.chat"

    def _tool_my_report(self, args, user, permission, **kw):
        # Your logic here — full ORM access
        return {"result": "..."}
```

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add your tools (XML data + Python methods)
4. Submit a pull request

---

## License

LGPL-3 — Same as Odoo Community.

## Credits

Developed by [Softhill](https://softhill.com.br) for the Odoo community.
