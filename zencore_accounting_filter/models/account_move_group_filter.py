# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL


class AccountMoveGroupFilter(models.Model):
    _inherit = 'account.move'

    def _read_group_select(self, aggregate_spec, query):
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
        """Enhance multi-level grouping (Product, Category, Division, District, Thana)
        with accurate line-level RINV quantities and amounts at every hierarchy level.
        """
        rinv_field_names = ('rinv_qty', 'rinv_qty_amount')
        rinv_aggregates = tuple(
            agg for agg in aggregates if agg.split(':', 1)[0] in rinv_field_names
        )
        rinv_in_unfold = bool(
            unfold_read_specification
            and any(f in unfold_read_specification for f in rinv_field_names)
        )

        result = super().web_read_group(
            domain=domain,
            groupby=groupby,
            aggregates=aggregates,
            limit=limit,
            offset=offset,
            order=order,
            auto_unfold=auto_unfold,
            opening_info=opening_info,
            unfold_read_specification=unfold_read_specification,
            unfold_read_default_limit=unfold_read_default_limit,
            groupby_read_specification=groupby_read_specification,
        )

        if not rinv_aggregates and not rinv_in_unfold:
            return result

        groups = result.get('groups', [])
        if not groups:
            return result

        # Extract parent filter context from the active domain
        parent_ctx = self._extract_domain_group_context(domain)

        # Collect all move IDs matching domain to preload line data in bulk
        all_moves = self.search(domain)
        if not all_moves:
            return result

        # Pre-load line and geography data in bulk (3 fast queries max)
        all_lines = self._prepare_group_line_cache(all_moves)

        # Recursively enhance all group levels, subgroups, and unfolded leaf records
        self._recursive_enhance_groups(groups, all_lines, parent_ctx)

        return result

    @api.model
    @api.readonly
    def web_search_read(
        self,
        domain,
        specification,
        offset=0,
        limit=None,
        order=None,
        count_limit=None,
    ):
        """Ensure leaf records unfolded via web_search_read display correct product-level
        RINV quantity and amount matching the active filter context.
        """
        res = super().web_search_read(
            domain=domain,
            specification=specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )
        if not res or not res.get('records'):
            return res

        rinv_field_names = ('rinv_qty', 'rinv_qty_amount')
        has_rinv = any(f in specification for f in rinv_field_names)
        if not has_rinv:
            return res

        filter_ctx = self._extract_domain_group_context(domain)
        if not filter_ctx:
            return res

        rec_ids = [r['id'] for r in res['records'] if 'id' in r]
        if not rec_ids:
            return res

        moves = self.browse(rec_ids)
        all_lines = self._prepare_group_line_cache(moves)

        for rec in res['records']:
            m_id = rec.get('id')
            matching_lines = [
                line
                for line in all_lines
                if line['move_id'] == m_id
                and ('product_group_ids' not in filter_ctx or line['product_id'] == filter_ctx['product_group_ids'])
                and ('product_categ_group_ids' not in filter_ctx or line['categ_id'] == filter_ctx['product_categ_group_ids'])
                and ('state_id' not in filter_ctx or line['state_id'] == filter_ctx['state_id'])
                and ('district_id' not in filter_ctx or line['district_id'] == filter_ctx['district_id'])
                and ('thana_id' not in filter_ctx or line['thana_id'] == filter_ctx['thana_id'])
            ]
            if 'rinv_qty' in specification:
                rec['rinv_qty'] = sum(l['quantity'] for l in matching_lines)
            if 'rinv_qty_amount' in specification:
                rec['rinv_qty_amount'] = sum(l['price_subtotal'] for l in matching_lines)

        return res

    @api.model
    def _extract_domain_group_context(self, domain):
        """Extract existing group filter values from domain."""
        context = {}
        if not domain:
            return context
        target_fields = (
            'product_group_ids',
            'product_categ_group_ids',
            'state_id',
            'district_id',
            'thana_id',
        )
        try:
            for cond in Domain(domain).iter_conditions():
                if cond.field_expr in target_fields and cond.operator in ('=', 'in'):
                    val = cond.value
                    if isinstance(val, (list, tuple)) and len(val) == 1:
                        val = val[0]
                    context[cond.field_expr] = val
        except Exception:
            pass
        return context

    @api.model
    def _prepare_group_line_cache(self, moves):
        """Pre-fetch all relevant invoice lines and their geographical dimensions in bulk."""
        all_move_ids = moves.ids
        if not all_move_ids:
            return []

        moves_geo = {
            m['id']: m
            for m in moves.read(['id', 'state_id', 'district_id', 'thana_id'])
        }

        lines_read = self.env['account.move.line'].search_read(
            domain=[
                ('move_id', 'in', all_move_ids),
                ('display_type', '=', 'product'),
            ],
            fields=['id', 'move_id', 'product_id', 'quantity', 'price_subtotal'],
        )

        prod_ids = list({l['product_id'][0] for l in lines_read if l.get('product_id')})
        prod_read = self.env['product.product'].browse(prod_ids).read(['id', 'categ_id'])
        prod_categ = {
            p['id']: (p['categ_id'][0] if p['categ_id'] else False)
            for p in prod_read
        }

        all_lines = []
        for l in lines_read:
            m_id = l['move_id'][0]
            p_id = l['product_id'][0] if l.get('product_id') else False
            c_id = prod_categ.get(p_id, False)
            m_geo = moves_geo.get(m_id, {})
            s_id = m_geo.get('state_id')[0] if m_geo.get('state_id') else False
            d_id = m_geo.get('district_id')[0] if m_geo.get('district_id') else False
            t_id = m_geo.get('thana_id')[0] if m_geo.get('thana_id') else False

            all_lines.append({
                'move_id': m_id,
                'product_id': p_id,
                'categ_id': c_id,
                'state_id': s_id,
                'district_id': d_id,
                'thana_id': t_id,
                'quantity': l.get('quantity') or 0.0,
                'price_subtotal': l.get('price_subtotal') or 0.0,
            })

        return all_lines

    @api.model
    def _recursive_enhance_groups(self, groups, all_lines, parent_ctx=None):
        """Recursively update group headers, subgroups, and unfolded records with line-level metrics."""
        if not groups:
            return
        parent_ctx = dict(parent_ctx or {})
        target_fields = (
            'product_group_ids',
            'product_categ_group_ids',
            'state_id',
            'district_id',
            'thana_id',
        )

        for group in groups:
            ctx = dict(parent_ctx)
            for fname in target_fields:
                val = group.get(fname)
                if val is not None and val is not False:
                    val_id = val[0] if isinstance(val, (list, tuple)) else val
                    ctx[fname] = val_id

            matching_lines = [
                line
                for line in all_lines
                if ('product_group_ids' not in ctx or line['product_id'] == ctx['product_group_ids'])
                and ('product_categ_group_ids' not in ctx or line['categ_id'] == ctx['product_categ_group_ids'])
                and ('state_id' not in ctx or line['state_id'] == ctx['state_id'])
                and ('district_id' not in ctx or line['district_id'] == ctx['district_id'])
                and ('thana_id' not in ctx or line['thana_id'] == ctx['thana_id'])
            ]

            group['rinv_qty:sum'] = sum(l['quantity'] for l in matching_lines)
            group['rinv_qty_amount:sum'] = sum(l['price_subtotal'] for l in matching_lines)

            # Patch unfolded leaf records within this group
            if '__records' in group:
                for rec in group['__records']:
                    m_id = rec.get('id')
                    rec_lines = [l for l in matching_lines if l['move_id'] == m_id]
                    rec['rinv_qty'] = sum(l['quantity'] for l in rec_lines)
                    rec['rinv_qty_amount'] = sum(l['price_subtotal'] for l in rec_lines)

            # Recurse down subgroups
            subgroups_data = group.get('__groups')
            if subgroups_data and 'groups' in subgroups_data:
                self._recursive_enhance_groups(subgroups_data['groups'], all_lines, ctx)

