# -*- coding: utf-8 -*-
from datetime import date, timedelta
from odoo.tests.common import TransactionCase


class TestReportingDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = date.today()

        # Models
        cls.Season = cls.env['cold.storage.season']
        cls.Chamber = cls.env['cold.storage.chamber']
        cls.Floor = cls.env['cold.storage.floor']
        cls.Line = cls.env['cold.storage.line']
        cls.Pocket = cls.env['cold.storage.pocket']
        cls.MasterSetup = cls.env['cold.storage.master.setup']
        cls.Inward = cls.env['cold.storage.inward']
        cls.Allocation = cls.env['cold.storage.inward.allocation']
        cls.Partner = cls.env['res.partner']

        # Setup Master Dimensions
        cls.chamber_1 = cls.Chamber.create({'name': 'Chamber 1'})
        cls.chamber_2 = cls.Chamber.create({'name': 'Chamber 2'})

        cls.floor_1 = cls.Floor.create({'name': '1st Floor'})
        cls.floor_2 = cls.Floor.create({'name': '2nd Floor'})

        cls.line_a = cls.Line.create({'name': 'Line A'})
        cls.line_b = cls.Line.create({'name': 'Line B'})

        cls.pocket_1 = cls.Pocket.create({'name': 'Pocket 101'})
        cls.pocket_2 = cls.Pocket.create({'name': 'Pocket 102'})

        # Setup Active Slots
        cls.slot_c1_f1 = cls.MasterSetup.create({
            'chamber_id': cls.chamber_1.id,
            'floor_id': cls.floor_1.id,
            'line_id': cls.line_a.id,
            'pocket_id': cls.pocket_1.id,
            'activate': True,
        })
        cls.slot_c1_f2 = cls.MasterSetup.create({
            'chamber_id': cls.chamber_1.id,
            'floor_id': cls.floor_2.id,
            'line_id': cls.line_a.id,
            'pocket_id': cls.pocket_2.id,
            'activate': True,
        })
        cls.slot_c2_f1 = cls.MasterSetup.create({
            'chamber_id': cls.chamber_2.id,
            'floor_id': cls.floor_1.id,
            'line_id': cls.line_b.id,
            'pocket_id': cls.pocket_1.id,
            'activate': True,
        })

        # Setup Customer & Season
        cls.customer = cls.Partner.create({'name': 'Farmer Reporting'})
        cls.season = cls.Season.create({
            'name': 'Potato Season Reports 2026',
            'date_start': cls.today,
            'date_end': cls.today + timedelta(days=90),
            'default_bag_rate': 120.0,
        })

    def test_01_reporting_menus_and_action_exist(self):
        """TC-56: Verify Reports menu and Storage Stock Analysis submenu exist with graph,pivot,list action."""
        reports_menu = self.env.ref('zencore_cold_storage_management.menu_cold_storage_reports')
        self.assertTrue(reports_menu, "Reports top menu must exist")
        self.assertEqual(reports_menu.name, 'Reports')

        submenu = self.env.ref('zencore_cold_storage_management.menu_cold_storage_stock_analysis')
        self.assertTrue(submenu, "Storage Stock Analysis submenu must exist")
        self.assertEqual(submenu.name, 'Storage Stock Analysis')

        action = self.env.ref('zencore_cold_storage_management.action_cold_storage_stock_analysis')
        self.assertTrue(action, "Stock analysis window action must exist")
        self.assertEqual(action.res_model, 'cold.storage.inward.allocation')
        self.assertIn('graph', action.view_mode)
        self.assertIn('pivot', action.view_mode)
        self.assertIn('list', action.view_mode)

    def test_02_reporting_views_structure(self):
        """TC-58, TC-59, TC-60: Verify Graph, Pivot, List, and Search views for stock analysis."""
        graph_view = self.env.ref('zencore_cold_storage_management.view_cold_storage_stock_analysis_graph')
        self.assertTrue(graph_view, "Graph view must exist")
        self.assertIn('<graph', graph_view.arch)
        self.assertIn('sample="1"', graph_view.arch)

        pivot_view = self.env.ref('zencore_cold_storage_management.view_cold_storage_stock_analysis_pivot')
        self.assertTrue(pivot_view, "Pivot view must exist")
        self.assertIn('<pivot', pivot_view.arch)
        self.assertIn('sample="1"', pivot_view.arch)

        list_view = self.env.ref('zencore_cold_storage_management.view_cold_storage_stock_analysis_list')
        self.assertTrue(list_view, "List view must exist")
        self.assertIn('<list', list_view.arch)

        search_view = self.env.ref('zencore_cold_storage_management.view_cold_storage_stock_analysis_search')
        self.assertTrue(search_view, "Search view must exist")
        self.assertIn('group_by_chamber', search_view.arch)
        self.assertIn('group_by_floor', search_view.arch)
        self.assertIn('filter_in_stock', search_view.arch)

    def test_03_stored_related_fields_on_allocation(self):
        """TC-57: Verify stored related fields on inward allocation automatically populate and store."""
        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'product_name': 'Granola Potato',
            'bag_quantity': 100,
            'bag_rate': 120.0,
            'season_id': self.season.id,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=90),
        })

        alloc = self.Allocation.create({
            'inward_id': inward.id,
            'slot_id': self.slot_c1_f1.id,
            'quantity': 60,
        })

        self.assertEqual(alloc.chamber_id, self.chamber_1, "Chamber related field must populate correctly")
        self.assertEqual(alloc.floor_id, self.floor_1, "Floor related field must populate correctly")
        self.assertEqual(alloc.line_id, self.line_a, "Line related field must populate correctly")
        self.assertEqual(alloc.pocket_id, self.pocket_1, "Pocket related field must populate correctly")
        self.assertEqual(alloc.partner_id, self.customer, "Customer related field must populate correctly")
        self.assertEqual(alloc.product_name, 'Granola Potato', "Product related field must populate correctly")
        self.assertEqual(alloc.season_id, self.season, "Season related field must populate correctly")

    def test_04_read_group_aggregations_by_chamber_and_floor(self):
        """TC-58b: Verify SQL aggregation (read_group) by Chamber and Floor accurately sums bag quantities."""
        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'product_name': 'Diamond Potato',
            'bag_quantity': 150,
            'bag_rate': 120.0,
            'season_id': self.season.id,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=90),
        })

        # Slot 1: Chamber 1, Floor 1 -> 50 bags
        self.Allocation.create({
            'inward_id': inward.id,
            'slot_id': self.slot_c1_f1.id,
            'quantity': 50,
        })
        # Slot 2: Chamber 1, Floor 2 -> 30 bags
        self.Allocation.create({
            'inward_id': inward.id,
            'slot_id': self.slot_c1_f2.id,
            'quantity': 30,
        })
        # Slot 3: Chamber 2, Floor 1 -> 40 bags
        self.Allocation.create({
            'inward_id': inward.id,
            'slot_id': self.slot_c2_f1.id,
            'quantity': 40,
        })

        # Modern Odoo 19 _read_group: returns list of tuples (group_values..., aggregate_values...)
        groups_by_chamber = self.Allocation._read_group(
            domain=[('inward_id', '=', inward.id)],
            groupby=['chamber_id'],
            aggregates=['quantity:sum']
        )
        chamber_quantities = {chamber.id: qty for chamber, qty in groups_by_chamber}
        self.assertEqual(chamber_quantities[self.chamber_1.id], 80, "Chamber 1 should aggregate 50 + 30 = 80 bags")
        self.assertEqual(chamber_quantities[self.chamber_2.id], 40, "Chamber 2 should aggregate 40 bags")

        # Aggregation by Chamber + Floor
        groups_by_chamber_floor = self.Allocation._read_group(
            domain=[('inward_id', '=', inward.id)],
            groupby=['chamber_id', 'floor_id'],
            aggregates=['quantity:sum']
        )
        cf_quantities = {(c.id, f.id): qty for c, f, qty in groups_by_chamber_floor}
        self.assertEqual(cf_quantities[(self.chamber_1.id, self.floor_1.id)], 50)
        self.assertEqual(cf_quantities[(self.chamber_1.id, self.floor_2.id)], 30)
