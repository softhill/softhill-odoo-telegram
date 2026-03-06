from odoo import fields, models


class TelegramUserProfile(models.Model):
    _name = "telegram.user.profile"
    _description = "Telegram User Profile"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(
        default=10,
        help="Higher sequence = more permissions. Used to compare access levels.",
    )
    active = fields.Boolean(default=True)
    color = fields.Integer()
    description = fields.Text(
        translate=True,
        help="Description shown to admins when assigning profiles.",
    )
    group_id = fields.Many2one(
        "res.groups",
        string="Odoo Group",
        help="If set, users in this Odoo group automatically get this profile.",
    )
