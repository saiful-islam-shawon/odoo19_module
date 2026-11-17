def _pre_init_hook(env):
    """Neutralize stale invoice layout views before QWeb validates XML data."""
    env.cr.execute(
        """
        UPDATE ir_ui_view AS view
           SET active = FALSE
          FROM ir_model_data AS data
         WHERE data.model = 'ir.ui.view'
           AND data.res_id = view.id
           AND data.module = 'systech_report'
           AND (
                data.name = 'report_invoice_use_clean_layout'
                OR (
                    view.arch_db::text LIKE '%web.external_layout%'
                    AND view.arch_db::text LIKE '%invoice_main%'
                )
           )
        """
    )


from . import models
