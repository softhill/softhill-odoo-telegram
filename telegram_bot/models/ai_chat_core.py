"""Core Odoo tool implementations for the AI chat.

High-level convenience tools that wrap common Odoo operations.
Each method corresponds to a telegram.tool record defined in
telegram_tools_core_data.xml.
"""
import logging
from datetime import date, datetime, timedelta

from odoo import api, models

_logger = logging.getLogger(__name__)


def _period_domain(field, period):
    """Build date domain filter for a period."""
    today = date.today()
    if period == "today":
        return [(field, ">=", today.isoformat())]
    elif period == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return [(field, ">=", tomorrow.isoformat()), (field, "<", (tomorrow + timedelta(days=1)).isoformat())]
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        return [(field, ">=", start.isoformat())]
    elif period == "month":
        return [(field, ">=", today.replace(day=1).isoformat())]
    elif period == "year":
        return [(field, ">=", today.replace(month=1, day=1).isoformat())]
    return []


def _resolve_partner(env, query):
    """Find a partner by name, email, phone or ID."""
    Partner = env["res.partner"].sudo()
    if isinstance(query, int) or (isinstance(query, str) and query.isdigit()):
        return Partner.browse(int(query)).exists()
    return Partner.search([
        "|", "|", ("name", "ilike", query), ("email", "ilike", query), ("phone", "ilike", query),
    ], limit=1)


def _resolve_product(env, query):
    """Find a product by name, default_code or ID."""
    Product = env["product.product"].sudo()
    if isinstance(query, int) or (isinstance(query, str) and query.isdigit()):
        return Product.browse(int(query)).exists()
    return Product.search([
        "|", ("name", "ilike", query), ("default_code", "ilike", query),
    ], limit=1)


class TelegramAIChatCore(models.AbstractModel):
    _inherit = "telegram.ai.chat"

    # ==========================================
    # SALES
    # ==========================================

    @api.model
    def _tool_sales_summary(self, args, user, permission):
        SO = self.env["sale.order"].sudo()
        period = args.get("period", "month")
        state = args.get("state", "all")

        domain = []
        if state != "all":
            domain.append(("state", "=", state))
        else:
            domain.append(("state", "!=", "cancel"))
        domain += _period_domain("date_order", period)

        if args.get("salesperson"):
            domain.append(("user_id.name", "ilike", args["salesperson"]))

        orders = SO.search(domain)
        total = sum(orders.mapped("amount_total"))
        confirmed = orders.filtered(lambda o: o.state == "sale")
        draft = orders.filtered(lambda o: o.state == "draft")

        # Top customers
        partner_totals = {}
        for o in confirmed:
            name = o.partner_id.name
            partner_totals[name] = partner_totals.get(name, 0) + o.amount_total
        top_customers = sorted(partner_totals.items(), key=lambda x: -x[1])[:5]

        return {
            "period": period,
            "total_orders": len(orders),
            "quotations": len(draft),
            "confirmed_orders": len(confirmed),
            "total_amount": round(total, 2),
            "confirmed_amount": round(sum(confirmed.mapped("amount_total")), 2),
            "currency": "BRL",
            "top_customers": [{"name": n, "total": round(t, 2)} for n, t in top_customers],
        }

    @api.model
    def _tool_create_quotation(self, args, user, permission):
        partner = _resolve_partner(self.env, args["partner"])
        if not partner:
            return {"error": f"Cliente '{args['partner']}' nao encontrado"}

        lines = []
        for line in args.get("lines", []):
            product = _resolve_product(self.env, line["product"])
            if not product:
                return {"error": f"Produto '{line['product']}' nao encontrado"}
            vals = {
                "product_id": product.id,
                "product_uom_qty": line.get("qty", 1),
            }
            if line.get("price"):
                vals["price_unit"] = line["price"]
            lines.append((0, 0, vals))

        order = self.env["sale.order"].sudo().create({
            "partner_id": partner.id,
            "order_line": lines,
            "note": args.get("note", ""),
        })

        return {
            "id": order.id,
            "name": order.name,
            "partner": partner.name,
            "amount_total": order.amount_total,
            "line_count": len(order.order_line),
            "state": "draft",
        }

    # ==========================================
    # INVOICING
    # ==========================================

    @api.model
    def _tool_invoicing_summary(self, args, user, permission):
        AM = self.env["account.move"].sudo()
        period = args.get("period", "month")
        move_type = args.get("type", "out_invoice")

        domain = [("state", "=", "posted")]
        if move_type != "all":
            domain.append(("move_type", "=", move_type))
        else:
            domain.append(("move_type", "in", ("out_invoice", "out_refund")))
        domain += _period_domain("invoice_date", period)

        invoices = AM.search(domain)
        total = sum(invoices.mapped("amount_total"))
        residual = sum(invoices.mapped("amount_residual"))

        # Overdue
        today = date.today()
        overdue = invoices.filtered(
            lambda i: i.amount_residual > 0 and i.invoice_date_due and i.invoice_date_due < today
        )
        overdue_amount = sum(overdue.mapped("amount_residual"))

        # Top debtors
        partner_debts = {}
        for inv in invoices.filtered(lambda i: i.amount_residual > 0):
            name = inv.partner_id.name
            partner_debts[name] = partner_debts.get(name, 0) + inv.amount_residual
        top_debtors = sorted(partner_debts.items(), key=lambda x: -x[1])[:5]

        return {
            "period": period,
            "total_invoices": len(invoices),
            "total_amount": round(total, 2),
            "total_receivable": round(residual, 2),
            "overdue_count": len(overdue),
            "overdue_amount": round(overdue_amount, 2),
            "currency": "BRL",
            "top_debtors": [{"name": n, "amount": round(a, 2)} for n, a in top_debtors],
        }

    # ==========================================
    # CRM
    # ==========================================

    @api.model
    def _tool_crm_pipeline(self, args, user, permission):
        Lead = self.env["crm.lead"].sudo()
        domain = [("active", "=", True), ("type", "=", "opportunity")]

        if args.get("salesperson"):
            domain.append(("user_id.name", "ilike", args["salesperson"]))
        if args.get("stage"):
            domain.append(("stage_id.name", "ilike", args["stage"]))

        leads = Lead.search(domain)
        total_revenue = sum(leads.mapped("expected_revenue"))

        # Group by stage
        stages = {}
        for lead in leads:
            stage_name = lead.stage_id.name or "Sem Estagio"
            if stage_name not in stages:
                stages[stage_name] = {"count": 0, "revenue": 0}
            stages[stage_name]["count"] += 1
            stages[stage_name]["revenue"] += lead.expected_revenue or 0

        pipeline = [
            {"stage": name, "count": data["count"], "revenue": round(data["revenue"], 2)}
            for name, data in stages.items()
        ]

        # Recent opportunities
        recent = Lead.search(domain, limit=5, order="create_date desc")
        recent_list = [
            {
                "name": l.name,
                "partner": l.partner_id.name or l.contact_name or "",
                "stage": l.stage_id.name,
                "revenue": l.expected_revenue,
                "probability": l.probability,
            }
            for l in recent
        ]

        return {
            "total_opportunities": len(leads),
            "total_expected_revenue": round(total_revenue, 2),
            "pipeline": pipeline,
            "recent": recent_list,
            "currency": "BRL",
        }

    @api.model
    def _tool_create_lead(self, args, user, permission):
        vals = {
            "name": args["name"],
            "type": args.get("type", "opportunity"),
            "expected_revenue": args.get("expected_revenue", 0),
            "description": args.get("description", ""),
            "user_id": user.id,
        }

        if args.get("partner"):
            partner = _resolve_partner(self.env, args["partner"])
            if partner:
                vals["partner_id"] = partner.id
            else:
                vals["contact_name"] = args["partner"]

        lead = self.env["crm.lead"].sudo().create(vals)
        return {
            "id": lead.id,
            "name": lead.name,
            "type": lead.type,
            "stage": lead.stage_id.name,
        }

    # ==========================================
    # PROJECTS / TIMESHEETS
    # ==========================================

    @api.model
    def _tool_project_summary(self, args, user, permission):
        Task = self.env["project.task"].sudo()
        AAL = self.env["account.analytic.line"].sudo()
        period = args.get("period", "month")

        task_domain = []
        if args.get("project"):
            task_domain.append(("project_id.name", "ilike", args["project"]))
        if args.get("user"):
            task_domain.append(("user_ids.name", "ilike", args["user"]))
        elif permission == "freela":
            task_domain.append(("user_ids", "in", [user.id]))

        tasks = Task.search(task_domain)

        # Group by stage
        stages = {}
        for t in tasks:
            stage_name = t.stage_id.name or "Sem Estagio"
            stages[stage_name] = stages.get(stage_name, 0) + 1

        # Overdue tasks
        today = date.today()
        overdue = tasks.filtered(
            lambda t: t.date_deadline and t.date_deadline < today and not t.stage_id.fold
        )

        # Timesheets
        ts_domain = [("project_id", "!=", False)]
        ts_domain += _period_domain("date", period)
        if args.get("project"):
            ts_domain.append(("project_id.name", "ilike", args["project"]))
        if args.get("user"):
            ts_domain.append(("user_id.name", "ilike", args["user"]))
        elif permission == "freela":
            ts_domain.append(("user_id", "=", user.id))

        timesheets = AAL.search(ts_domain)
        total_hours = sum(timesheets.mapped("unit_amount"))

        return {
            "total_tasks": len(tasks),
            "tasks_by_stage": stages,
            "overdue_tasks": len(overdue),
            "overdue_list": [
                {"name": t.name, "project": t.project_id.name, "deadline": str(t.date_deadline)}
                for t in overdue[:5]
            ],
            "total_hours": round(total_hours, 2),
            "period": period,
        }

    @api.model
    def _tool_log_timesheet(self, args, user, permission):
        Task = self.env["project.task"].sudo()
        task_ref = args["task"]

        if isinstance(task_ref, int) or (isinstance(task_ref, str) and task_ref.isdigit()):
            task = Task.browse(int(task_ref)).exists()
        else:
            task = Task.search([("name", "ilike", task_ref)], limit=1)

        if not task:
            return {"error": f"Tarefa '{task_ref}' nao encontrada"}

        ts_date = args.get("date", date.today().isoformat())
        ts = self.env["account.analytic.line"].sudo().create({
            "task_id": task.id,
            "project_id": task.project_id.id,
            "name": args["description"],
            "unit_amount": args["hours"],
            "date": ts_date,
            "user_id": user.id,
        })

        return {
            "id": ts.id,
            "task": task.name,
            "project": task.project_id.name,
            "hours": args["hours"],
            "date": ts_date,
        }

    @api.model
    def _tool_create_task(self, args, user, permission):
        Project = self.env["project.project"].sudo()
        project_ref = args["project"]

        if isinstance(project_ref, int) or (isinstance(project_ref, str) and project_ref.isdigit()):
            project = Project.browse(int(project_ref)).exists()
        else:
            project = Project.search([("name", "ilike", project_ref)], limit=1)

        if not project:
            return {"error": f"Projeto '{project_ref}' nao encontrado"}

        vals = {
            "name": args["name"],
            "project_id": project.id,
            "description": args.get("description", ""),
        }

        if args.get("assignee"):
            assignee = self.env["res.users"].sudo().search(
                [("name", "ilike", args["assignee"])], limit=1
            )
            if assignee:
                vals["user_ids"] = [(6, 0, [assignee.id])]

        if args.get("deadline"):
            vals["date_deadline"] = args["deadline"]
        if args.get("priority"):
            vals["priority"] = args["priority"]

        task = self.env["project.task"].sudo().create(vals)
        return {
            "id": task.id,
            "name": task.name,
            "project": project.name,
            "stage": task.stage_id.name,
        }

    # ==========================================
    # CONTACTS
    # ==========================================

    @api.model
    def _tool_find_contact(self, args, user, permission):
        Partner = self.env["res.partner"].sudo()
        query = args["query"]

        domain = [
            "|", "|", "|",
            ("name", "ilike", query),
            ("email", "ilike", query),
            ("phone", "ilike", query),
            ("vat", "ilike", query),
        ]
        if args.get("is_company"):
            domain.append(("is_company", "=", True))
        if args.get("customer"):
            domain.append(("customer_rank", ">", 0))
        if args.get("supplier"):
            domain.append(("supplier_rank", ">", 0))

        partners = Partner.search(domain, limit=10)
        results = []
        for p in partners:
            data = {
                "id": p.id,
                "name": p.name,
                "email": p.email or "",
                "phone": p.phone or "",
                "mobile": p.mobile or "",
                "is_company": p.is_company,
                "city": p.city or "",
                "state": p.state_id.name if p.state_id else "",
                "country": p.country_id.name if p.country_id else "",
                "vat": p.vat or "",
            }
            # Sales info
            sales = self.env["sale.order"].sudo().search_count([
                ("partner_id", "=", p.id), ("state", "=", "sale"),
            ])
            data["sale_count"] = sales
            data["total_receivable"] = round(p.credit, 2) if hasattr(p, "credit") else 0
            results.append(data)

        return {"count": len(results), "contacts": results}

    @api.model
    def _tool_create_contact(self, args, user, permission):
        vals = {
            "name": args["name"],
            "is_company": args.get("is_company", False),
            "email": args.get("email", ""),
            "phone": args.get("phone", ""),
            "mobile": args.get("mobile", ""),
            "street": args.get("street", ""),
            "city": args.get("city", ""),
            "zip": args.get("zip", ""),
            "vat": args.get("vat", ""),
        }

        if args.get("state"):
            state = self.env["res.country.state"].sudo().search([
                ("code", "=", args["state"].upper()), ("country_id.code", "=", "BR"),
            ], limit=1)
            if state:
                vals["state_id"] = state.id
                vals["country_id"] = state.country_id.id

        if args.get("company"):
            parent = self.env["res.partner"].sudo().search([
                ("name", "ilike", args["company"]), ("is_company", "=", True),
            ], limit=1)
            if parent:
                vals["parent_id"] = parent.id

        partner = self.env["res.partner"].sudo().create(vals)
        return {"id": partner.id, "name": partner.name, "display_name": partner.display_name}

    # ==========================================
    # PURCHASE
    # ==========================================

    @api.model
    def _tool_purchase_summary(self, args, user, permission):
        PO = self.env["purchase.order"].sudo()
        period = args.get("period", "month")
        state = args.get("state", "all")

        domain = []
        if state != "all":
            domain.append(("state", "=", state))
        else:
            domain.append(("state", "!=", "cancel"))
        domain += _period_domain("date_order", period)

        orders = PO.search(domain)
        total = sum(orders.mapped("amount_total"))
        draft = orders.filtered(lambda o: o.state == "draft")
        confirmed = orders.filtered(lambda o: o.state == "purchase")

        # Top suppliers
        supplier_totals = {}
        for o in confirmed:
            name = o.partner_id.name
            supplier_totals[name] = supplier_totals.get(name, 0) + o.amount_total
        top_suppliers = sorted(supplier_totals.items(), key=lambda x: -x[1])[:5]

        return {
            "period": period,
            "total_orders": len(orders),
            "draft_rfq": len(draft),
            "confirmed_orders": len(confirmed),
            "total_amount": round(total, 2),
            "currency": "BRL",
            "top_suppliers": [{"name": n, "total": round(t, 2)} for n, t in top_suppliers],
        }

    # ==========================================
    # INVENTORY
    # ==========================================

    @api.model
    def _tool_stock_levels(self, args, user, permission):
        Quant = self.env["stock.quant"].sudo()
        domain = [("location_id.usage", "=", "internal")]

        if args.get("product"):
            domain.append(("product_id.name", "ilike", args["product"]))
        if args.get("warehouse"):
            domain.append(("location_id.warehouse_id.name", "ilike", args["warehouse"]))

        limit = args.get("limit", 20)
        quants = Quant.search(domain, limit=limit, order="quantity desc")

        products = {}
        for q in quants:
            pid = q.product_id.id
            if pid not in products:
                products[pid] = {
                    "id": pid,
                    "name": q.product_id.name,
                    "code": q.product_id.default_code or "",
                    "qty_on_hand": 0,
                    "location": q.location_id.complete_name,
                }
            products[pid]["qty_on_hand"] += q.quantity

        result = list(products.values())

        if args.get("low_stock"):
            low = []
            for p in result:
                product = self.env["product.product"].sudo().browse(p["id"])
                reorder = self.env["stock.warehouse.orderpoint"].sudo().search([
                    ("product_id", "=", p["id"]),
                ], limit=1)
                if reorder and p["qty_on_hand"] <= reorder.product_min_qty:
                    p["min_qty"] = reorder.product_min_qty
                    low.append(p)
            result = low

        return {"count": len(result), "products": result[:limit]}

    @api.model
    def _tool_stock_moves(self, args, user, permission):
        Picking = self.env["stock.picking"].sudo()
        period = args.get("period", "week")

        domain = [("state", "!=", "cancel")]
        domain += _period_domain("scheduled_date", period)

        if args.get("product"):
            domain.append(("move_ids.product_id.name", "ilike", args["product"]))
        if args.get("picking_type") == "incoming":
            domain.append(("picking_type_id.code", "=", "incoming"))
        elif args.get("picking_type") == "outgoing":
            domain.append(("picking_type_id.code", "=", "outgoing"))
        elif args.get("picking_type") == "internal":
            domain.append(("picking_type_id.code", "=", "internal"))

        limit = args.get("limit", 20)
        pickings = Picking.search(domain, limit=limit, order="scheduled_date desc")

        return {
            "count": len(pickings),
            "moves": [
                {
                    "id": p.id,
                    "name": p.name,
                    "type": p.picking_type_id.name,
                    "partner": p.partner_id.name or "",
                    "state": p.state,
                    "scheduled_date": str(p.scheduled_date) if p.scheduled_date else "",
                    "products": [
                        {"name": m.product_id.name, "qty": m.product_uom_qty}
                        for m in p.move_ids[:5]
                    ],
                }
                for p in pickings
            ],
        }

    # ==========================================
    # HR
    # ==========================================

    @api.model
    def _tool_employees(self, args, user, permission):
        Emp = self.env["hr.employee"].sudo()
        domain = []

        if args.get("name"):
            domain.append(("name", "ilike", args["name"]))
        if args.get("department"):
            domain.append(("department_id.name", "ilike", args["department"]))
        if args.get("job"):
            domain.append(("job_id.name", "ilike", args["job"]))

        employees = Emp.search(domain, limit=30)
        return {
            "count": len(employees),
            "employees": [
                {
                    "id": e.id,
                    "name": e.name,
                    "job": e.job_id.name or "",
                    "department": e.department_id.name or "",
                    "work_email": e.work_email or "",
                    "work_phone": e.work_phone or "",
                    "manager": e.parent_id.name if e.parent_id else "",
                }
                for e in employees
            ],
        }

    # ==========================================
    # CALENDAR
    # ==========================================

    @api.model
    def _tool_calendar(self, args, user, permission):
        Event = self.env["calendar.event"].sudo()
        period = args.get("period", "week")

        today = date.today()
        if period == "today":
            start = today
            end = today + timedelta(days=1)
        elif period == "tomorrow":
            start = today + timedelta(days=1)
            end = today + timedelta(days=2)
        elif period == "week":
            start = today
            end = today + timedelta(days=7)
        elif period == "month":
            start = today
            end = today + timedelta(days=30)
        else:
            start = today
            end = today + timedelta(days=7)

        domain = [("start", ">=", start.isoformat()), ("start", "<", end.isoformat())]

        if args.get("user"):
            target_user = self.env["res.users"].sudo().search(
                [("name", "ilike", args["user"])], limit=1
            )
            if target_user:
                domain.append(("partner_ids", "in", [target_user.partner_id.id]))
        elif permission == "freela":
            domain.append(("partner_ids", "in", [user.partner_id.id]))

        events = Event.search(domain, order="start asc", limit=20)
        return {
            "period": period,
            "count": len(events),
            "events": [
                {
                    "id": e.id,
                    "name": e.name,
                    "start": str(e.start),
                    "stop": str(e.stop),
                    "all_day": e.allday,
                    "attendees": [a.display_name for a in e.attendee_ids[:5]],
                    "location": e.location or "",
                }
                for e in events
            ],
        }

    @api.model
    def _tool_create_event(self, args, user, permission):
        vals = {
            "name": args["name"],
            "start": args["start"],
            "stop": args["stop"],
            "description": args.get("description", ""),
            "user_id": user.id,
        }

        partner_ids = [user.partner_id.id]
        for attendee_ref in args.get("attendees", []):
            att_user = self.env["res.users"].sudo().search([
                "|", ("name", "ilike", attendee_ref), ("email", "ilike", attendee_ref),
            ], limit=1)
            if att_user and att_user.partner_id.id not in partner_ids:
                partner_ids.append(att_user.partner_id.id)

        vals["partner_ids"] = [(6, 0, partner_ids)]
        event = self.env["calendar.event"].sudo().create(vals)
        return {
            "id": event.id,
            "name": event.name,
            "start": str(event.start),
            "stop": str(event.stop),
            "attendees": [a.display_name for a in event.attendee_ids],
        }

    # ==========================================
    # EXPENSES
    # ==========================================

    @api.model
    def _tool_expenses(self, args, user, permission):
        Expense = self.env["hr.expense"].sudo()
        period = args.get("period", "month")
        state = args.get("state", "all")

        domain = []
        if state != "all":
            domain.append(("state", "=", state))
        domain += _period_domain("date", period)

        if args.get("employee"):
            domain.append(("employee_id.name", "ilike", args["employee"]))
        elif permission == "freela":
            emp = self.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)
            if emp:
                domain.append(("employee_id", "=", emp.id))

        expenses = Expense.search(domain, limit=30, order="date desc")
        total = sum(expenses.mapped("total_amount"))

        return {
            "count": len(expenses),
            "total_amount": round(total, 2),
            "currency": "BRL",
            "expenses": [
                {
                    "id": e.id,
                    "name": e.name,
                    "employee": e.employee_id.name,
                    "amount": e.total_amount,
                    "date": str(e.date) if e.date else "",
                    "state": e.state,
                }
                for e in expenses
            ],
        }
