def migrate(cr, version):
    """Preserve customer codes from releases that named the field ``cmr``."""
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'res_partner'
           AND column_name IN ('cmr', 'customer_id')
        """
    )
    columns = {column for column, in cr.fetchall()}

    if 'cmr' in columns and 'customer_id' not in columns:
        cr.execute('ALTER TABLE res_partner RENAME COLUMN cmr TO customer_id')
    elif {'cmr', 'customer_id'} <= columns:
        cr.execute(
            """
            UPDATE res_partner
               SET customer_id = cmr
             WHERE NULLIF(customer_id, '') IS NULL
               AND NULLIF(cmr, '') IS NOT NULL
            """
        )
