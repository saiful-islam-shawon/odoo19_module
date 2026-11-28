from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Refresh stored VAT totals created before product lines were finalized."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env['account.move'].with_context(active_test=False).search([
        ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
    ])
    move_model = env['account.move']
    for field_name in (
        'vat_taxable_amount', 'vat_output_amount', 'vat_input_amount',
        'vat_sd_amount', 'vat_is_high_value', 'vat_reverse_charge_amount',
    ):
        env.add_to_compute(move_model._fields[field_name], moves)
    env.flush_all()
