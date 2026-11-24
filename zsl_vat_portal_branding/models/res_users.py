from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """Make the VAT dashboard the home page for new internal users."""
        vat_action = self.env.ref('zsl_vat.action_vat_dashboard', raise_if_not_found=False)
        vat_group = self.env.ref('zsl_vat.group_vat_user', raise_if_not_found=False)
        if vat_action or vat_group:
            for values in vals_list:
                if not values.get('share'):
                    if vat_action:
                        values.setdefault('action_id', vat_action.id)
                    if vat_group:
                        groups = list(values.get('group_ids', []))
                        groups.append((4, vat_group.id))
                        values['group_ids'] = groups
        return super().create(vals_list)

    @api.model
    def set_vat_dashboard_as_home_action(self):
        """Apply the dedicated VAT landing page to existing internal users."""
        vat_action = self.env.ref('zsl_vat.action_vat_dashboard', raise_if_not_found=False)
        vat_group = self.env.ref('zsl_vat.group_vat_user', raise_if_not_found=False)
        if not vat_action or not vat_group:
            return False
        users = self.sudo().search([('share', '=', False)])
        users.write({
            'action_id': vat_action.id,
            'group_ids': [(4, vat_group.id)],
        })
        return True
