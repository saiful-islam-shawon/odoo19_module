def migrate(cr, version):
    """Disable the old base-report extensions before their records are replaced."""
    cr.execute(
        """
        UPDATE ir_ui_view AS view
           SET active = FALSE
          FROM ir_model_data AS data
         WHERE data.model = 'ir.ui.view'
           AND data.res_id = view.id
           AND data.module = 'systech_report'
           AND data.name IN (
                'invoice_external_layout_clean',
                'report_invoice_restore_standard_address',
                'report_invoice_use_clean_layout',
                'invoice_white_table_header_color',
                'report_invoice_document_inherit_due',
                'report_invoice_document_inherit_signature'
           )
        """
    )
