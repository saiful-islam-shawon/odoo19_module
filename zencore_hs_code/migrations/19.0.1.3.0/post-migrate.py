from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Earlier versions added the HS duty into the purchase order total.

    Recompute the standard totals so existing orders show
    Total = Untaxed Amount + taxes, as in standard Odoo.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    PurchaseOrder = env["purchase.order"]
    orders = PurchaseOrder.with_context(active_test=False).search([])
    for fname in ("amount_untaxed", "amount_tax", "amount_total", "amount_total_cc"):
        env.add_to_compute(PurchaseOrder._fields[fname], orders)
    env.flush_all()
