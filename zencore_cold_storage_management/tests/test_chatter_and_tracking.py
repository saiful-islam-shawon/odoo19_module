# -*- coding: utf-8 -*-
from datetime import date, timedelta
from odoo.tests.common import TransactionCase


class TestChatterAndTracking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = date.today()

        # Models
        cls.Season = cls.env['cold.storage.season']
        cls.Team = cls.env['cold.storage.team']
        cls.MasterSetup = cls.env['cold.storage.master.setup']
        cls.Inward = cls.env['cold.storage.inward']
        cls.Plotting = cls.env['cold.storage.inward.plotting']
        cls.Scrap = cls.env['cold.storage.inward.scrap']
        cls.Release = cls.env['cold.storage.inward.release']

        cls.Chamber = cls.env['cold.storage.chamber']
        cls.Floor = cls.env['cold.storage.floor']
        cls.Line = cls.env['cold.storage.line']
        cls.Pocket = cls.env['cold.storage.pocket']
        cls.Employee = cls.env['hr.employee']
        cls.Partner = cls.env['res.partner']

        # Master data
        cls.employee = cls.Employee.create({'name': 'Manager Karim'})
        cls.partner = cls.Partner.create({'name': 'Test Farmer'})

        cls.chamber = cls.Chamber.create({'name': 'Chamber Chatter'})
        cls.floor = cls.Floor.create({'name': 'Floor Chatter'})
        cls.line = cls.Line.create({'name': 'Line Chatter'})
        cls.pocket = cls.Pocket.create({'name': 'Pocket Chatter'})

        cls.slot = cls.MasterSetup.create({
            'chamber_id': cls.chamber.id,
            'floor_id': cls.floor.id,
            'line_id': cls.line.id,
            'pocket_id': cls.pocket.id,
        })

        cls.season = cls.Season.create({
            'name': 'Chatter Test Season 2026',
            'date_start': cls.today,
            'date_end': cls.today + timedelta(days=90),
            'default_bag_rate': 100.0,
        })

    def test_01_models_inherit_mail_thread_and_activity(self):
        """TC-51: Verify all 7 designated models inherit mail.thread and mail.activity.mixin."""
        models_to_check = [
            'cold.storage.season',
            'cold.storage.team',
            'cold.storage.master.setup',
            'cold.storage.inward',
            'cold.storage.inward.plotting',
            'cold.storage.inward.scrap',
            'cold.storage.inward.release',
        ]
        for model_name in models_to_check:
            model = self.env[model_name]
            self.assertIn('message_ids', model._fields, f"{model_name} must inherit mail.thread (message_ids field missing)")
            self.assertIn('activity_ids', model._fields, f"{model_name} must inherit mail.activity.mixin (activity_ids field missing)")
            self.assertTrue(hasattr(model, 'message_post'), f"{model_name} must have message_post method")
            self.assertTrue(hasattr(model, 'activity_schedule'), f"{model_name} must have activity_schedule method")

    def test_02_dimension_models_do_not_inherit_mail_thread(self):
        """TC-54: Verify dimension models (Chamber, Floor, Line, Pocket) do NOT have chatter."""
        dimensions = ['cold.storage.chamber', 'cold.storage.floor', 'cold.storage.line', 'cold.storage.pocket']
        for dim_model in dimensions:
            model = self.env[dim_model]
            self.assertNotIn('message_ids', model._fields, f"{dim_model} should NOT have chatter (message_ids)")
            self.assertNotIn('activity_ids', model._fields, f"{dim_model} should NOT have activity_ids")

    def test_03_message_post_on_season_and_inward(self):
        """TC-53a: Verify posting a message/log note creates mail.message on records."""
        # Season message post
        msg = self.season.message_post(body="Season opened for early potato booking.", message_type='comment')
        self.assertTrue(msg, "Message should be created on season")
        self.assertIn("early potato booking", msg.body)

        # Inward message post
        inward = self.Inward.create({
            'partner_id': self.partner.id,
            'product_name': 'Diamond Potato',
            'bag_quantity': 50,
            'bag_rate': 120.0,
            'season_id': self.season.id,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=60),
        })
        inward_msg = inward.message_post(body="Special storage conditions requested.", message_type='comment')
        self.assertTrue(inward_msg, "Message should be created on inward")
        self.assertIn("Special storage conditions", inward_msg.body)

    def test_04_activity_scheduling_on_inward(self):
        """TC-53b: Verify scheduling an activity on inward lot."""
        inward = self.Inward.create({
            'partner_id': self.partner.id,
            'product_name': 'Cardinal Potato',
            'bag_quantity': 30,
            'bag_rate': 110.0,
            'season_id': self.season.id,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=60),
        })
        mail_activity_type = self.env['mail.activity.type'].search([], limit=1)
        if mail_activity_type:
            activity = inward.activity_schedule(
                activity_type_id=mail_activity_type.id,
                summary="Quality inspection",
                note="Inspect bags on arrival",
            )
            self.assertTrue(activity, "Activity should be scheduled successfully")
            self.assertEqual(activity.res_model, 'cold.storage.inward')
            self.assertEqual(activity.res_id, inward.id)

    def test_05_field_tracking_audit_log(self):
        """TC-53c: Verify tracked field changes generate mail.tracking.value logs."""
        self.env.cr.precommit.run()
        initial_msg_count = len(self.season.message_ids)
        self.season.action_close()
        self.assertEqual(self.season.state, 'closed')
        self.env.cr.precommit.run()
        self.assertGreater(len(self.season.message_ids), initial_msg_count, "Tracking should create a message on state change")
        tracking_messages = self.season.message_ids.filtered(lambda m: bool(m.tracking_value_ids))
        self.assertTrue(tracking_messages, "At least one message should contain tracking values")

    def test_06_form_views_contain_chatter_widget(self):
        """TC-52: Verify XML form views of all 7 models include the <chatter/> tag."""
        form_view_xml_ids = [
            'zencore_cold_storage_management.view_cold_storage_season_form',
            'zencore_cold_storage_management.view_cold_storage_team_form',
            'zencore_cold_storage_management.view_cold_storage_master_setup_form',
            'zencore_cold_storage_management.view_cold_storage_inward_form',
            'zencore_cold_storage_management.view_cold_storage_inward_plotting_form',
            'zencore_cold_storage_management.view_cold_storage_inward_scrap_form',
            'zencore_cold_storage_management.view_cold_storage_inward_release_form',
        ]
        for xml_id in form_view_xml_ids:
            view = self.env.ref(xml_id)
            self.assertTrue(view, f"View {xml_id} must exist")
            self.assertIn('<chatter', view.arch, f"View {xml_id} arch must contain <chatter/>")
