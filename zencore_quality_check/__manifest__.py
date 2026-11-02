# -*- coding: utf-8 -*-
{
    'name': 'Zencore Quality Check',
    'version': '19.0.2.0.0',
    'category': 'Quality Management',
    'summary': 'Seed Physical Arrival, Gate Receiving, Physical & Laboratory Quality Testing',
    'description': """
Zencore Quality Check Management
================================
- Seed arrival and physical gate receipt registration.
- Physical quality inspection (torn bags, pest infestation, dampness, label matching).
- Laboratory quality testing with dynamic parameter table (Moisture, Purity, Germination, etc.).
- 3-tier review and approval lifecycle: Technician (Submit) -> Checker (Verify/Return) -> Approver (Approve/Return/Reject).
- Strict Segregation of Duties and permanent terminal state locking.
- Mandatory rejection reason wizards.
- Dedicated Menu: Quality Check -> Seed Receiving & Lab Testing.
    """,
    'author': 'Antigravity / Zencore',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'product',
    ],
    'data': [
        'security/zencore_quality_groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/ir_sequence_data.xml',
        'wizard/seed_receipt_reject_wizard_views.xml',
        'wizard/seed_lab_test_reject_wizard_views.xml',
        'views/seed_receipt_views.xml',
        'views/seed_lab_test_views.xml',
        'views/zencore_quality_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
