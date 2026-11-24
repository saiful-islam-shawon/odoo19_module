from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible_ids = super()._visible_menu_ids(debug=debug)
        # This database is deployed as a dedicated VAT application.  The
        # underlying accounting, stock, purchase and sales modules remain
        # installed because ZSL VAT uses their business objects, but their app
        # entries must not be exposed in the user interface.
        if self.env.su:
            return visible_ids
        vat_menu = self.env.ref('zsl_vat.menu_zsl_vat_root', raise_if_not_found=False)
        if not vat_menu:
            return set()
        allowed_ids = set(self.search([('id', 'child_of', vat_menu.id)]).ids)
        return set(visible_ids) & allowed_ids

    @api.model
    def cleanup_obsolete_vat_settings_shortcuts(self):
        """Remove duplicate shortcuts introduced by an earlier workspace UI.

        The related actions remain available from their proper functional
        module: Customer/Vendor under Parties and HS Code/Price under Product
        & Service.  Missing external IDs are intentionally harmless on a
        fresh installation.
        """
        xmlids = (
            'zsl_vat_portal_branding.menu_vat_settings_customers',
            'zsl_vat_portal_branding.menu_vat_settings_vendors',
            'zsl_vat_portal_branding.menu_vat_settings_customer',
            'zsl_vat_portal_branding.menu_vat_settings_hs_codes',
            'zsl_vat_portal_branding.menu_vat_settings_price_declarations',
            'zsl_vat_portal_branding.menu_vat_settings_products',
            'zsl_vat_portal_branding.menu_vat_settings_dashboard',
        )
        for xmlid in xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menu.unlink()
        return True
