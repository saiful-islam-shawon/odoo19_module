# -*- coding: utf-8 -*-
{
    'name': 'QC',
    'version': '19.0.6.0.0',
    'category': 'Quality Management',
    'summary': 'Seed Receiving, QC Lab Testing, Processing, Post-QC, Cold Storage, Retest & Scrap',
    'description': """
Zencore Quality Check Management
================================
- Seed arrival and physical gate receipt registration.
- Physical quality inspection (torn bags, pest infestation, dampness, label matching).
- Laboratory quality testing with dynamic parameter table (Moisture, Purity, Germination, etc.).
- 3-tier review and approval lifecycle: Technician (Submit) -> Checker (Verify/Return) -> Approver (Approve/Return/Reject).
- Strict Segregation of Duties and permanent terminal state locking.
- Mandatory rejection reason wizards.
- Strict 1-to-1 Seed Receipt Linkage & Duplicate Prevention.
- Seed Processing Batch Lifecycle: Draft -> Drying -> Grading -> Packing -> Done.
- Dynamic Multi-Product Grading with Format 1 Auto-Lot Numbering (LOT/YYYY/00001).
- Processing Summary Smart Buttons (Produced Lots, Good Yield, Waste).
- Processed Seed QC (Post-Processing Quality Assurance) with 1-to-1 non-waste lot testing.
- Cold Storage Preservation with Storage & Validity Date Tracking.
- Validity Expiration Control & Mandatory Retesting before Release.
- Retest Workflow with Lab Parameters (Pass & Release vs Fail & Scrap).
- Isolated Cold Storage Scrap Registry.
- Dedicated Menus: Quality Check -> Seed Receiving, Lab Testing, Seed Processing, Processed Seed QC, Cold Storage, Retest & Scrap.
    """,
    'author': 'Antigravity / Zencore',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'product',
        'stock',
    ],
    'data': [
        'security/zencore_quality_groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/ir_sequence_data.xml',
        'wizard/seed_receipt_reject_wizard_views.xml',
        'wizard/seed_lab_test_reject_wizard_views.xml',
        'wizard/processed_seed_qc_reject_wizard_views.xml',
        'wizard/seed_retest_scrap_wizard_views.xml',
        'views/seed_receipt_views.xml',
        'views/seed_lab_test_views.xml',
        'views/seed_processing_batch_views.xml',
        'views/processed_seed_qc_views.xml',
        'views/seed_cold_storage_views.xml',
        'views/seed_retest_views.xml',
        'views/seed_cold_storage_scrap_views.xml',
        'views/zencore_quality_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
