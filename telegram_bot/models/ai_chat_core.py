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

        # Timesheets (only if hr_timesheet is installed)
        total_hours = 0
        try:
            AAL = self.env["account.analytic.line"].sudo()
            # Check if project_id field exists (hr_timesheet adds it)
            if "project_id" in AAL._fields:
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
        except Exception:
            pass

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
        AAL = self.env["account.analytic.line"].sudo()
        if "project_id" not in AAL._fields:
            return {"error": "Modulo hr_timesheet nao instalado. Instale para registrar horas."}

        Task = self.env["project.task"].sudo()
        task_ref = args["task"]

        if isinstance(task_ref, int) or (isinstance(task_ref, str) and task_ref.isdigit()):
            task = Task.browse(int(task_ref)).exists()
        else:
            task = Task.search([("name", "ilike", task_ref)], limit=1)

        if not task:
            return {"error": f"Tarefa '{task_ref}' nao encontrada"}

        ts_date = args.get("date", date.today().isoformat())
        ts = AAL.create({
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

    # ------------------------------------------------------------------
    # INVOICE WRITE TOOLS
    # ------------------------------------------------------------------

    def _tool_create_invoice(self, args, user, permission, **kw):
        """Create a customer or vendor invoice."""
        partner = _resolve_partner(self.env, args["partner"])
        if not partner:
            return {"error": f"Partner not found: {args['partner']}"}

        move_type = args.get("type", "out_invoice")
        invoice_lines = []
        for line in args.get("lines", []):
            vals = {
                "name": line.get("description", ""),
                "quantity": line.get("qty", 1),
                "price_unit": line.get("price", 0),
            }
            if line.get("product"):
                prod = _resolve_product(self.env, line["product"])
                if prod:
                    vals["product_id"] = prod.id
                    if not vals["name"]:
                        vals["name"] = prod.name
                    if not vals["price_unit"]:
                        vals["price_unit"] = prod.lst_price
            invoice_lines.append((0, 0, vals))

        Move = self.env["account.move"].sudo()
        invoice = Move.create({
            "move_type": move_type,
            "partner_id": partner.id,
            "ref": args.get("ref", ""),
            "invoice_line_ids": invoice_lines,
        })

        return {
            "id": invoice.id,
            "name": invoice.name or "Draft",
            "type": move_type,
            "partner": partner.name,
            "amount_total": invoice.amount_total,
            "state": invoice.state,
            "url": f"/odoo/accounting/{invoice.id}",
        }

    def _tool_register_payment(self, args, user, permission, **kw):
        """Register payment on an invoice."""
        Move = self.env["account.move"].sudo()
        ref = args["invoice"]

        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            invoice = Move.browse(int(ref)).exists()
        else:
            invoice = Move.search([
                "|", ("name", "ilike", ref), ("ref", "ilike", ref),
                ("move_type", "in", ("out_invoice", "in_invoice")),
            ], limit=1)

        if not invoice:
            return {"error": f"Invoice not found: {ref}"}
        if invoice.payment_state == "paid":
            return {"error": f"Invoice {invoice.name} is already paid"}
        if invoice.state != "posted":
            return {"error": f"Invoice {invoice.name} is not posted (state: {invoice.state})"}

        amount = args.get("amount", invoice.amount_residual)

        journal_domain = [("type", "in", ("bank", "cash"))]
        if args.get("journal"):
            journal_domain.append(("name", "ilike", args["journal"]))
        journal = self.env["account.journal"].sudo().search(journal_domain, limit=1)
        if not journal:
            return {"error": "No payment journal found"}

        PaymentRegister = self.env["account.payment.register"].sudo()
        wizard = PaymentRegister.with_context(
            active_model="account.move",
            active_ids=invoice.ids,
        ).create({
            "amount": amount,
            "journal_id": journal.id,
        })
        wizard.action_create_payments()

        return {
            "invoice": invoice.name,
            "amount_paid": amount,
            "journal": journal.name,
            "remaining": invoice.amount_residual,
            "payment_state": invoice.payment_state,
        }

    # ------------------------------------------------------------------
    # PURCHASE WRITE TOOLS
    # ------------------------------------------------------------------

    def _tool_create_purchase_order(self, args, user, permission, **kw):
        """Create a purchase order (RFQ)."""
        partner = _resolve_partner(self.env, args["partner"])
        if not partner:
            return {"error": f"Supplier not found: {args['partner']}"}

        order_lines = []
        for line in args.get("lines", []):
            prod = _resolve_product(self.env, line["product"])
            if not prod:
                return {"error": f"Product not found: {line['product']}"}
            order_lines.append((0, 0, {
                "product_id": prod.id,
                "name": prod.name,
                "product_qty": line.get("qty", 1),
                "price_unit": line.get("price", prod.standard_price or 0),
                "product_uom": prod.uom_po_id.id or prod.uom_id.id,
            }))

        PO = self.env["purchase.order"].sudo()
        po = PO.create({
            "partner_id": partner.id,
            "order_line": order_lines,
        })

        return {
            "id": po.id,
            "name": po.name,
            "partner": partner.name,
            "amount_total": po.amount_total,
            "state": po.state,
            "url": f"/odoo/purchase/{po.id}",
        }

    # ------------------------------------------------------------------
    # PRODUCT TOOLS
    # ------------------------------------------------------------------

    def _tool_find_product(self, args, user, permission, **kw):
        """Search products by name, reference or barcode."""
        Product = self.env["product.product"].sudo()
        query = args["query"]
        domain = ["|", "|",
            ("name", "ilike", query),
            ("default_code", "ilike", query),
            ("barcode", "ilike", query),
        ]
        if args.get("category"):
            domain.append(("categ_id.name", "ilike", args["category"]))
        if args.get("type"):
            domain.append(("detailed_type", "=", args["type"]))

        limit = args.get("limit", 10)
        products = Product.search(domain, limit=limit)

        return {
            "count": len(products),
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "default_code": p.default_code or "",
                    "barcode": p.barcode or "",
                    "type": p.detailed_type,
                    "list_price": p.lst_price,
                    "standard_price": p.standard_price,
                    "qty_available": p.qty_available,
                    "virtual_available": p.virtual_available,
                    "category": p.categ_id.name,
                    "active": p.active,
                }
                for p in products
            ],
        }

    def _tool_create_product(self, args, user, permission, **kw):
        """Create a product."""
        Product = self.env["product.product"].sudo()
        vals = {
            "name": args["name"],
            "detailed_type": args.get("type", "consu"),
        }
        if args.get("list_price"):
            vals["lst_price"] = args["list_price"]
        if args.get("standard_price"):
            vals["standard_price"] = args["standard_price"]
        if args.get("default_code"):
            vals["default_code"] = args["default_code"]
        if args.get("barcode"):
            vals["barcode"] = args["barcode"]
        if args.get("description"):
            vals["description"] = args["description"]

        product = Product.create(vals)
        return {
            "id": product.id,
            "name": product.name,
            "default_code": product.default_code or "",
            "list_price": product.lst_price,
            "type": product.detailed_type,
        }

    # ------------------------------------------------------------------
    # HR WRITE TOOLS
    # ------------------------------------------------------------------

    def _tool_create_expense(self, args, user, permission, **kw):
        """Create an expense."""
        Expense = self.env["hr.expense"].sudo()
        emp = self.env["hr.employee"].sudo().search([("user_id", "=", user.id)], limit=1)
        if not emp:
            return {"error": "No employee record found for your user"}

        vals = {
            "name": args["name"],
            "employee_id": emp.id,
            "total_amount": args["amount"],
            "date": args.get("date", date.today().isoformat()),
        }
        if args.get("product"):
            prod = self.env["product.product"].sudo().search([
                ("name", "ilike", args["product"]),
                ("can_be_expensed", "=", True),
            ], limit=1)
            if prod:
                vals["product_id"] = prod.id

        expense = Expense.create(vals)
        return {
            "id": expense.id,
            "name": expense.name,
            "amount": expense.total_amount,
            "employee": emp.name,
            "state": expense.state,
        }

    # ------------------------------------------------------------------
    # DISCUSS / MESSAGING TOOLS
    # ------------------------------------------------------------------

    def _tool_send_message(self, args, user, permission, **kw):
        """Send an internal message via Odoo Discuss."""
        Partner = self.env["res.partner"].sudo()
        body = args["body"]
        subject = args.get("subject", "")
        sent_to = []

        for recipient in args.get("to", []):
            partner = Partner.search([
                "|", ("name", "ilike", recipient), ("email", "ilike", recipient),
            ], limit=1)
            if partner:
                channel = self.env["discuss.channel"].sudo().search([
                    ("channel_type", "=", "chat"),
                    ("channel_member_ids.partner_id", "in", [user.partner_id.id, partner.id]),
                ], limit=1)
                if not channel:
                    channel = self.env["discuss.channel"].sudo().channel_get([partner.id])

                channel.message_post(
                    body=body,
                    subject=subject or False,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                    author_id=user.partner_id.id,
                )
                sent_to.append(partner.name)
            else:
                sent_to.append(f"{recipient} (not found)")

        return {"sent_to": sent_to, "body_preview": body[:100]}

    # ------------------------------------------------------------------
    # REPORT / ANALYTICS TOOLS
    # ------------------------------------------------------------------

    def _tool_sales_by_product(self, args, user, permission, **kw):
        """Ranking of best-selling products."""
        period = args.get("period", "month")
        limit = args.get("limit", 10)
        order_by = args.get("order_by", "revenue")

        domain = [("state", "in", ("sale", "done"))]
        domain += _period_domain("date_order", period)

        SOL = self.env["sale.order.line"].sudo()
        lines = SOL.search(domain)

        product_data = {}
        for line in lines:
            pid = line.product_id.id
            if pid not in product_data:
                product_data[pid] = {
                    "name": line.product_id.name,
                    "default_code": line.product_id.default_code or "",
                    "qty": 0,
                    "revenue": 0,
                }
            product_data[pid]["qty"] += line.product_uom_qty
            product_data[pid]["revenue"] += line.price_subtotal

        key = "revenue" if order_by == "revenue" else "qty"
        ranked = sorted(product_data.values(), key=lambda x: x[key], reverse=True)[:limit]

        return {
            "period": period,
            "order_by": order_by,
            "products": [
                {**p, "qty": round(p["qty"], 2), "revenue": round(p["revenue"], 2)}
                for p in ranked
            ],
        }

    def _tool_sales_by_salesperson(self, args, user, permission, **kw):
        """Ranking of salespeople by revenue."""
        period = args.get("period", "month")
        limit = args.get("limit", 10)

        domain = [("state", "in", ("sale", "done"))]
        domain += _period_domain("date_order", period)

        SO = self.env["sale.order"].sudo()
        orders = SO.search(domain)

        sp_data = {}
        for o in orders:
            uid = o.user_id.id if o.user_id else 0
            name = o.user_id.name if o.user_id else "Unassigned"
            if uid not in sp_data:
                sp_data[uid] = {"name": name, "orders": 0, "revenue": 0}
            sp_data[uid]["orders"] += 1
            sp_data[uid]["revenue"] += o.amount_total

        ranked = sorted(sp_data.values(), key=lambda x: x["revenue"], reverse=True)[:limit]
        return {
            "period": period,
            "salespeople": [
                {**s, "revenue": round(s["revenue"], 2)} for s in ranked
            ],
        }

    def _tool_overdue_invoices(self, args, user, permission, **kw):
        """List overdue invoices."""
        days = args.get("days_overdue", 1)
        limit = args.get("limit", 20)
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        Move = self.env["account.move"].sudo()
        invoices = Move.search([
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")),
            ("invoice_date_due", "<=", cutoff),
        ], limit=limit, order="invoice_date_due asc")

        today = date.today()
        return {
            "count": len(invoices),
            "total_overdue": round(sum(invoices.mapped("amount_residual")), 2),
            "invoices": [
                {
                    "id": inv.id,
                    "name": inv.name,
                    "partner": inv.partner_id.name,
                    "amount_total": inv.amount_total,
                    "amount_residual": inv.amount_residual,
                    "date_due": str(inv.invoice_date_due),
                    "days_overdue": (today - inv.invoice_date_due).days,
                }
                for inv in invoices
            ],
        }

    # ------------------------------------------------------------------
    # RECRUITMENT TOOLS
    # ------------------------------------------------------------------

    def _tool_recruitment(self, args, user, permission, **kw):
        """List open positions and applicants."""
        if not self.env["ir.module.module"].sudo().search([
            ("name", "=", "hr_recruitment"), ("state", "=", "installed"),
        ]):
            return {"error": "Module hr_recruitment is not installed"}

        Job = self.env["hr.job"].sudo()
        job_domain = [("no_of_recruitment", ">", 0)]
        if args.get("department"):
            job_domain.append(("department_id.name", "ilike", args["department"]))
        if args.get("job"):
            job_domain.append(("name", "ilike", args["job"]))

        jobs = Job.search(job_domain, limit=20)

        Applicant = self.env["hr.applicant"].sudo()
        applicants = Applicant.search([
            ("job_id", "in", jobs.ids),
        ], limit=50, order="create_date desc")

        return {
            "open_positions": len(jobs),
            "total_applicants": len(applicants),
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "department": j.department_id.name or "",
                    "vacancies": j.no_of_recruitment,
                    "hired": j.no_of_hired_employee,
                    "applicants": len(Applicant.search([("job_id", "=", j.id)])),
                }
                for j in jobs
            ],
        }

    # ------------------------------------------------------------------
    # WEBSITE / EVENTS TOOLS
    # ------------------------------------------------------------------

    def _tool_events(self, args, user, permission, **kw):
        """List website events."""
        if not self.env["ir.module.module"].sudo().search([
            ("name", "=", "event"), ("state", "=", "installed"),
        ]):
            return {"error": "Module event is not installed"}

        Event = self.env["event.event"].sudo()
        domain = []
        if args.get("upcoming", True):
            domain.append(("date_end", ">=", datetime.now().isoformat()))
        if args.get("name"):
            domain.append(("name", "ilike", args["name"]))

        events = Event.search(domain, limit=20, order="date_begin asc")

        return {
            "count": len(events),
            "events": [
                {
                    "id": ev.id,
                    "name": ev.name,
                    "date_begin": str(ev.date_begin) if ev.date_begin else "",
                    "date_end": str(ev.date_end) if ev.date_end else "",
                    "location": ev.address_id.name if ev.address_id else "",
                    "seats_available": ev.seats_available,
                    "seats_reserved": ev.seats_reserved,
                    "seats_used": ev.seats_used,
                    "state": ev.stage_id.name if ev.stage_id else "",
                }
                for ev in events
            ],
        }

    # ------------------------------------------------------------------
    # SYSTEM / UTILITY TOOLS
    # ------------------------------------------------------------------

    def _tool_installed_modules(self, args, user, permission, **kw):
        """List installed modules."""
        Module = self.env["ir.module.module"].sudo()
        state = args.get("state", "installed")
        domain = [("state", "=", state)]
        if args.get("name"):
            domain.append(("name", "ilike", args["name"]))
        if args.get("apps_only", True):
            domain.append(("application", "=", True))

        modules = Module.search(domain, order="name asc")
        return {
            "count": len(modules),
            "modules": [
                {
                    "name": m.name,
                    "shortdesc": m.shortdesc or "",
                    "state": m.state,
                    "installed_version": m.installed_version or "",
                    "application": m.application,
                }
                for m in modules
            ],
        }

    def _tool_system_info(self, args, user, permission, **kw):
        """Return system information."""
        import odoo
        Users = self.env["res.users"].sudo()
        active_users = Users.search_count([("active", "=", True), ("share", "=", False)])
        portal_users = Users.search_count([("active", "=", True), ("share", "=", True)])

        db_name = self.env.cr.dbname

        model_counts = {}
        for model_name in ("res.partner", "sale.order", "account.move", "project.task", "crm.lead", "product.product"):
            try:
                model_counts[model_name] = self.env[model_name].sudo().search_count([])
            except Exception:
                pass

        return {
            "odoo_version": odoo.release.version,
            "database": db_name,
            "active_users": active_users,
            "portal_users": portal_users,
            "record_counts": model_counts,
        }

    def _tool_user_activity(self, args, user, permission, **kw):
        """Show user activity and last login."""
        Users = self.env["res.users"].sudo()
        domain = [("active", "=", True), ("share", "=", False)]

        if args.get("user"):
            domain.append(("name", "ilike", args["user"]))
        if args.get("active_today"):
            today_str = date.today().isoformat()
            domain.append(("login_date", ">=", today_str))

        users = Users.search(domain, limit=30, order="login_date desc")

        today = date.today()
        return {
            "count": len(users),
            "users": [
                {
                    "id": u.id,
                    "name": u.name,
                    "login": u.login,
                    "last_login": str(u.login_date) if u.login_date else "never",
                    "days_since_login": (today - u.login_date.date()).days if u.login_date else None,
                    "groups": ", ".join(u.groups_id.filtered(lambda g: g.category_id).mapped("full_name")[:5]),
                }
                for u in users
            ],
        }
