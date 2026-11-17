def migrate(cr, version):
    """Deactivate pre-1.0.3 views that rewrote the base invoice layout."""
    cr.execute(
        """
        UPDATE ir_ui_view AS view
           SET active = FALSE
          FROM ir_model_data AS data
         WHERE data.model = 'ir.ui.view'
           AND data.res_id = view.id
           AND data.module = 'systech_report'
           AND data.name = 'report_invoice_use_clean_layout'
        """
    )
