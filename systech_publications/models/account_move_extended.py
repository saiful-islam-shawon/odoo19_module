from odoo import api, fields, models
from odoo.tools import SQL


class AccountMoveExtended(models.Model):
    _inherit = 'account.move'

    product_ids = fields.Many2one(
        'product.product',
        string='Product',
        compute='_compute_product_ids',
        store=True,
        index=True,
    )

    product_group_ids = fields.Many2many(
        'product.product',
        'account_move_product_group_rel',
        'move_id',
        'product_id',
        string='Product',
        compute='_compute_product_group_ids',
        store=True,
        index=True,
    )

    # no fixes needed
    product_categ_group_ids = fields.Many2many(
        'product.category',
        'account_move_categ_group_rel',
        'move_id',
        'categ_id',
        string='Product Category',
        compute='_compute_product_group_ids',
        store=True,
        index=True,
    )

    product_categ_ids = fields.Many2one(
        'product.category',
        string='Product Category',
        compute='_compute_product_ids',
        store=True,
        index=True,
    )

    @api.depends('invoice_line_ids.product_id')
    def _compute_product_ids(self):
        for move in self:
            products = move.invoice_line_ids.mapped('product_id')
            move.product_ids = [(6, 0, products.ids)]

            categories = products.mapped('categ_id')
            move.product_categ_ids = [(6, 0, categories.ids)]

    @api.depends('invoice_line_ids.product_id')
    def _compute_product_group_ids(self):
        for move in self:
            products = move.invoice_line_ids.mapped('product_id')
            move.product_group_ids = [(6, 0, products.ids)]

            categories = products.mapped('categ_id')
            move.product_categ_group_ids = [(6, 0, categories.ids)]

    country_id = fields.Many2one(
        'res.country',
        related='partner_id.country_id',
        store=True,
        string='Country',
        index=True,
    )

    state_id = fields.Many2one(
        'res.country.state',
        related='partner_id.state_id',
        store=True,
        string='Division',
        index=True,
    )

    district_id = fields.Many2one(
        'res.district',
        related='partner_id.district_id',
        store=True,
        string='District',
        index=True,
    )

    thana_id = fields.Many2one(
        'res.thana',
        related='partner_id.thana_id',
        store=True,
        string='Thana',
        index=True,
    )

    total_quantity = fields.Float(
        string='Quantity',
        compute='_compute_total_quantity',
        store=True,
    )

    rinv_qty = fields.Float(
        string='RINV QTY',
        compute='_compute_rinv_qty',
        aggregator='sum',
        help=(
            'When Credit Notes are grouped by Product, this column shows only '
            'the quantity of the product represented by the current group.'
        ),
    )

    rinv_qty_amount = fields.Float(
        string='RINV QTY Amount',
        compute='_compute_rinv_qty_amount',
        aggregator='sum',
        help=(
            'When Credit Notes are grouped by Product, this column shows only '
            'the amount (quantity x price) of the product represented by the '
            'current group.'
        ),
    )

    @api.depends('invoice_line_ids.quantity')
    def _compute_total_quantity(self):
        for move in self:
            move.total_quantity = sum(move.invoice_line_ids.mapped('quantity'))

    @api.depends('invoice_line_ids.quantity')
    def _compute_rinv_qty(self):
        """The value is meaningful only inside a Product group."""
        for move in self:
            move.rinv_qty = 0.0

    @api.depends('invoice_line_ids.quantity', 'invoice_line_ids.price_subtotal')
    def _compute_rinv_qty_amount(self):
        """The value is meaningful only inside a Product group."""
        for move in self:
            move.rinv_qty_amount = 0.0

    def _read_group_select(self, aggregate_spec, query):
        """Expose ``rinv_qty``/``rinv_qty_amount`` as aggregatable virtual fields.

        Odoo only asks ``web_read_group`` for aggregates that are declared as
        valid by the field metadata. Because these fields are non-stored, the
        standard ORM would otherwise remove their ``sum`` aggregator and the
        collapsed Product groups would display an empty cell. The real value
        is injected later by :meth:`web_read_group`.
        """
        if aggregate_spec in ('rinv_qty:sum', 'rinv_qty_amount:sum'):
            return SQL('0.0')
        return super()._read_group_select(aggregate_spec, query)

    @api.model
    @api.readonly
    def web_read_group(
        self,
        domain,
        groupby,
        aggregates=(),
        limit=None,
        offset=0,
        order=None,
        *,
        auto_unfold=False,
        opening_info=None,
        unfold_read_specification=None,
        unfold_read_default_limit=80,
        groupby_read_specification=None,
    ):
        """Return product-specific RINV quantity/amount in Product-grouped lists.

        A credit note can contain several products, while ``account.move`` has
        only one value per field. The web client also reuses the same move data
        when that move appears in several Many2many product groups. Therefore,
        the RINV quantity/amount must be injected into each returned product
        group and each group's copy of the unfolded record.
        """
        rinv_field_names = ('rinv_qty', 'rinv_qty_amount')
        rinv_aggregates = tuple(
            aggregate
            for aggregate in aggregates
            if aggregate.split(':', 1)[0] in rinv_field_names
        )
        clean_aggregates = tuple(
            aggregate for aggregate in aggregates if aggregate not in rinv_aggregates
        )

        result = super().web_read_group(
            domain=domain,
            groupby=groupby,
            aggregates=clean_aggregates,
            limit=limit,
            offset=offset,
            order=order,
            auto_unfold=auto_unfold,
            opening_info=opening_info,
            unfold_read_specification=unfold_read_specification,
            unfold_read_default_limit=unfold_read_default_limit,
            groupby_read_specification=groupby_read_specification,
        )

        if (
            not rinv_aggregates
            or not groupby
            or groupby[0].split(':', 1)[0] != 'product_group_ids'
        ):
            return result

        groups = result.get('groups', [])
        if not groups:
            return result

        rinv_qty_requested = any(
            aggregate.split(':', 1)[0] == 'rinv_qty' for aggregate in rinv_aggregates
        )
        rinv_amount_requested = any(
            aggregate.split(':', 1)[0] == 'rinv_qty_amount'
            for aggregate in rinv_aggregates
        )

        product_group_key = groupby[0]
        group_product_ids = {}
        product_ids = set()

        for group in groups:
            product_value = group.get(product_group_key)
            product_id = (
                product_value[0]
                if isinstance(product_value, (tuple, list)) and product_value
                else False
            )
            if product_id:
                group_product_ids[id(group)] = product_id
                product_ids.add(product_id)

        if not product_ids:
            return result

        line_aggregates = ['quantity:sum', 'price_subtotal:sum']

        # Compute the correct quantity/amount shown on each Product group header.
        move_ids = self.search(domain).ids
        quantity_by_product = {}
        amount_by_product = {}
        if move_ids:
            grouped_values = self.env['account.move.line']._read_group(
                domain=[
                    ('move_id', 'in', move_ids),
                    ('product_id', 'in', list(product_ids)),
                    ('display_type', '=', 'product'),
                ],
                groupby=['product_id'],
                aggregates=line_aggregates,
            )
            for product, quantity, amount in grouped_values:
                if not product:
                    continue
                quantity_by_product[product.id] = quantity
                amount_by_product[product.id] = amount

        # Gather all unfolded move/product pairs first, then calculate them in
        # one query. A copied dictionary is placed in every group because Odoo
        # may reuse the same record dictionary across several M2M groups.
        unfolded_pairs = set()

        def collect_pairs(group, product_id):
            for record_values in group.get('__records', []):
                move_id = record_values.get('id')
                if move_id:
                    unfolded_pairs.add((move_id, product_id))

            subgroup_data = group.get('__groups') or {}
            for subgroup in subgroup_data.get('groups', []):
                collect_pairs(subgroup, product_id)

        for group in groups:
            product_id = group_product_ids.get(id(group))
            if product_id:
                collect_pairs(group, product_id)

        quantity_by_move_product = {}
        amount_by_move_product = {}
        if unfolded_pairs:
            unfolded_move_ids = {move_id for move_id, _product_id in unfolded_pairs}
            unfolded_product_ids = {
                product_id for _move_id, product_id in unfolded_pairs
            }
            grouped_line_values = self.env['account.move.line']._read_group(
                domain=[
                    ('move_id', 'in', list(unfolded_move_ids)),
                    ('product_id', 'in', list(unfolded_product_ids)),
                    ('display_type', '=', 'product'),
                ],
                groupby=['move_id', 'product_id'],
                aggregates=line_aggregates,
            )
            for move, product, quantity, amount in grouped_line_values:
                if not move or not product:
                    continue
                quantity_by_move_product[(move.id, product.id)] = quantity
                amount_by_move_product[(move.id, product.id)] = amount

        def patch_records(group, product_id):
            if '__records' in group:
                patched_records = []
                for record_values in group['__records']:
                    patched_values = dict(record_values)
                    key = (record_values.get('id'), product_id)
                    if rinv_qty_requested:
                        patched_values['rinv_qty'] = quantity_by_move_product.get(
                            key, 0.0
                        )
                    if rinv_amount_requested:
                        patched_values['rinv_qty_amount'] = amount_by_move_product.get(
                            key, 0.0
                        )
                    patched_records.append(patched_values)
                group['__records'] = patched_records

            subgroup_data = group.get('__groups') or {}
            for subgroup in subgroup_data.get('groups', []):
                patch_records(subgroup, product_id)

        for group in groups:
            product_id = group_product_ids.get(id(group))
            if not product_id:
                continue

            if rinv_qty_requested:
                group['rinv_qty:sum'] = quantity_by_product.get(product_id, 0.0)
            if rinv_amount_requested:
                group['rinv_qty_amount:sum'] = amount_by_product.get(product_id, 0.0)

            patch_records(group, product_id)

        return result