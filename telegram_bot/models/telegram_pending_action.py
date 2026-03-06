import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class TelegramPendingAction(models.Model):
    _name = "telegram.pending_action"
    _description = "Telegram Pending Confirmation"
    _order = "create_date desc"

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    chat_id = fields.Char(required=True, help="Telegram chat ID")
    action_type = fields.Selection(
        [
            ("create", "Criar"),
            ("update", "Atualizar"),
            ("delete", "Excluir"),
            ("execute", "Executar"),
        ],
        required=True,
    )
    model_name = fields.Char(required=True)
    record_id = fields.Integer()
    action_data = fields.Text(required=True, help="JSON with action parameters")
    summary = fields.Char(compute="_compute_summary", store=True)
    status = fields.Selection(
        [
            ("pending", "Pendente"),
            ("confirmed", "Confirmado"),
            ("cancelled", "Cancelado"),
            ("expired", "Expirado"),
        ],
        default="pending",
        required=True,
    )
    expires_at = fields.Datetime(required=True)
    result = fields.Text()

    @api.depends("action_type", "model_name", "record_id")
    def _compute_summary(self):
        labels = {"create": "Criar", "update": "Atualizar", "delete": "Excluir", "execute": "Executar"}
        for rec in self:
            label = labels.get(rec.action_type, rec.action_type)
            target = f"{rec.model_name}"
            if rec.record_id:
                target += f" #{rec.record_id}"
            rec.summary = f"{label} {target}"

    def execute_action(self):
        """Execute the pending action after confirmation."""
        self.ensure_one()
        if self.status != "pending":
            return {"error": f"Action already {self.status}"}

        from datetime import datetime
        if self.expires_at and fields.Datetime.now() > self.expires_at:
            self.status = "expired"
            return {"error": "Action expired"}

        try:
            data = json.loads(self.action_data)
            env = self.env

            if self.action_type == "create":
                record = env[self.model_name].sudo().create(data.get("values", {}))
                result = {"id": record.id, "display_name": record.display_name}

            elif self.action_type == "update":
                record = env[self.model_name].sudo().browse(self.record_id)
                if not record.exists():
                    result = {"error": f"{self.model_name} #{self.record_id} not found"}
                else:
                    record.write(data.get("values", {}))
                    result = {"id": record.id, "display_name": record.display_name, "updated": True}

            elif self.action_type == "delete":
                record = env[self.model_name].sudo().browse(self.record_id)
                if not record.exists():
                    result = {"error": f"{self.model_name} #{self.record_id} not found"}
                else:
                    name = record.display_name
                    record.unlink()
                    result = {"deleted": True, "display_name": name}

            elif self.action_type == "execute":
                record = env[self.model_name].sudo().browse(self.record_id)
                if not record.exists():
                    result = {"error": f"{self.model_name} #{self.record_id} not found"}
                else:
                    method = data.get("method")
                    getattr(record, method)()
                    result = {"executed": method, "display_name": record.display_name}
            else:
                result = {"error": f"Unknown action type: {self.action_type}"}

            self.write({"status": "confirmed", "result": json.dumps(result, default=str)})
            return result

        except Exception as e:
            _logger.exception("Error executing pending action %s", self.id)
            self.write({"status": "confirmed", "result": json.dumps({"error": str(e)})})
            return {"error": str(e)}

    def cancel_action(self):
        self.ensure_one()
        self.status = "cancelled"
