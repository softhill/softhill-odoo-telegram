# Odoo Telegram Bot + AI Assistant

**Turn your Odoo into an AI-powered assistant that your team actually wants to use.**

Ask questions in plain language on Telegram and get instant answers from your Odoo data — sales reports, overdue invoices, stock levels, project status, CRM pipeline — all without opening a browser. Create quotations, log timesheets, register payments, and manage contacts just by chatting. Works from your phone, your IDE, or any HTTP client.

> *"Quanto vendemos esse mês?"* — The bot queries `sale.order`, aggregates by period, and responds in seconds.
>
> *"Cria uma cotação pro cliente X com 10 unidades do produto Y"* — Done. Quotation created, link sent.
>
> *"Quem está devendo?"* — Overdue invoices listed with amounts, due dates, and days overdue.

No XML-RPC. No middleware. No separate server. The bot runs **inside Odoo** as native modules, using the ORM directly with full security context. Install, configure your Telegram token and AI provider, and your team is up and running.

---

## Why This Bot?

| Traditional approach | This bot |
|---------------------|----------|
| Open browser → navigate menus → click filters → read data | Send a message → get the answer |
| Train users on Odoo's UI for every module | Users already know how to chat |
| Build custom dashboards for mobile access | Telegram works everywhere |
| Pay for external BI tools or custom reports | Ask the AI in natural language |
| Hire developers for every integration | Add tools via Odoo UI — no code |
| Separate MCP server for IDE integration | Built-in MCP endpoint |

### What your team gets

- **Sales team**: Pipeline status, quotation creation, customer lookup — all from Telegram
- **Finance**: Invoice summaries, overdue reports, payment registration
- **Operations**: Stock levels, purchase orders, delivery tracking
- **HR**: Employee info, expense management, recruitment status
- **Project managers**: Task overview, timesheet logging, deadline tracking
- **Everyone**: Calendar events, internal messaging, contact search

### What you get as admin

- **Full audit trail** of every bot interaction
- **Cost tracking** per user with token usage analytics
- **Granular permissions** — control who can read vs. write vs. admin
- **Dynamic tool registry** — enable/disable tools from the UI, no restart needed
- **MCP + REST API** — connect your IDE and external tools to Odoo

---

## 44 Built-in Tools

The bot ships with **44 tools** out of the box, organized in two layers:

### Layer 1: Generic ORM Tools (14 tools)

Low-level tools that work with **any** Odoo model. Power users and developers can query anything:

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `search_odoo` | Search any model with domain filters | Freela |
| `count_odoo` | Count records matching criteria | Freela |
| `read_record` | Read a single record by ID | Freela |
| `get_fields` | Discover fields of any model | Freela |
| `create_record` | Create records in any model | Dev |
| `update_record` | Update existing records | Dev |
| `execute_action` | Run actions (confirm, validate, post, etc.) | Dev |
| `delete_record` | Delete records (always requires confirmation) | Admin |
| `post_message` | Post to chatter of any record | Dev |
| `github_list_repos` | List repos in your GitHub org | Dev |
| `github_read_file` | Read file contents from repos | Dev |
| `github_search_code` | Search code across repos | Dev |
| `github_list_commits` | Recent commits from any repo | Dev |
| `github_list_prs` | Pull requests (open, closed, all) | Dev |

### Layer 2: Business Tools (30 tools)

High-level tools for common operations. Users don't need to know model names or field names — just describe what they want:

#### Sales & Invoicing

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `sales_summary` | Revenue totals, order counts, top customers by period | Freela |
| `sales_by_product` | Best-selling products ranked by revenue or quantity | Dev |
| `sales_by_salesperson` | Salesperson ranking by revenue | Dev |
| `create_quotation` | Create quotation with product lines — resolves names automatically | Dev |
| `invoicing_summary` | Billed vs. receivable vs. overdue, top debtors | Dev |
| `overdue_invoices` | List overdue invoices with days past due | Dev |
| `create_invoice` | Create customer or vendor invoice | Admin |
| `register_payment` | Register payment on a posted invoice | Admin |

#### CRM

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `crm_pipeline` | Opportunities by stage, expected revenue, recent leads | Freela |
| `create_lead` | Create a lead or opportunity | Dev |

#### Projects & Timesheets

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `project_summary` | Tasks by stage, overdue tasks, logged hours | Freela |
| `log_timesheet` | Log worked hours on a task by name | Freela |
| `create_task` | Create task in a project with assignee and deadline | Dev |

#### Contacts

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `find_contact` | Search by name, email, phone, VAT — returns full profile | Freela |
| `create_contact` | Create person or company with address, VAT, etc. | Dev |

#### Purchase & Inventory

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `purchase_summary` | Purchase totals, pending orders, top suppliers | Dev |
| `create_purchase_order` | Create RFQ with product lines | Dev |
| `stock_levels` | Stock by product, low stock alerts, warehouse filter | Dev |
| `stock_moves` | Recent stock movements (in, out, internal) | Dev |
| `find_product` | Search products by name, code, or barcode | Freela |
| `create_product` | Create a new product | Dev |

#### HR & Expenses

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `employees` | Employee list with department, job, manager | Dev |
| `expenses` | Expense overview by status and period | Freela |
| `create_expense` | Create expense entry for approval | Freela |
| `recruitment` | Open positions and applicant count | Dev |

#### Calendar & Messaging

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `calendar` | Upcoming events and meetings | Freela |
| `create_event` | Create calendar event with attendees | Dev |
| `send_message` | Send internal message via Odoo Discuss | Freela |

#### System

| Tool | What it does | Permission |
|------|-------------|:----------:|
| `installed_modules` | List installed Odoo modules and apps | Dev |
| `system_info` | Odoo version, database, user count, record stats | Admin |
| `user_activity` | User last login, activity tracking | Admin |
| `events` | Website events with registration info | Freela |

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

Three hierarchical levels — each inherits all permissions from levels below:

| Level | Can do | Typical user |
|-------|--------|-------------|
| **Freela** | Read data, search contacts, log timesheets, view calendar | Freelancers, interns |
| **Dev** | Create records, manage CRM, projects, products, purchases | Team members, managers |
| **Admin** | Financial operations (invoices, payments), system info, user management, delete records | Administrators |

Write operations on sensitive models require **explicit confirmation** via Telegram inline buttons before execution.

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
