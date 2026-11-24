# ZSL VAT Dedicated Login — Odoo 19 setup

## Install

Copy `zsl_vat_portal_branding` to a configured addons_path and restart Odoo. Install after `zencore_hs_code` and `zsl_vat`.

Example, on an **existing, initialized staging database**:

```bash
./odoo-bin -c /etc/odoo19.conf -d zsl_vat_uat -i zsl_vat_portal_branding --stop-after-init
```

## Dedicated VAT users

In Settings > Users & Companies > Users, open a normal internal user and add **VAT Dedicated Workspace** to their access rights. Do **not** assign this restriction to the administrator; the admin must retain setup capability.

The user must also have the appropriate accounting/inventory rights *when they actually need to post invoices, purchase, stock or manufacturing entries*. Hiding menus does NOT grant model permissions.

Set user's **Home Action** to `VAT Dashboard` (technical XMLID `zsl_vat.action_vat_dashboard`) if available in that Odoo edition. To set it through an Odoo shell:

```python
u = env['res.users'].search([('login', '=', 'vat.user@example.com')], limit=1)
g = env.ref('zsl_vat_portal_branding.group_zsl_vat_dedicated')
a = env.ref('zsl_vat.action_vat_dashboard')
assert u and u.id != 1, 'Use an ordinary user account'
u.write({'groups_id': [(4, g.id)], 'action_id': a.id})
env.cr.commit()
```

With this setup the VAT user's backend app menu will show only ZSL VAT and its child menus, and successful login uses the configured Home Action. Other applications are **still installed** as dependencies.

## Constraints

* This is menu visibility, **not an authorization boundary**. Users with model access may still use permitted records/actions via internal links/API. Use dedicated record rules, model ACLs and restricted groups for true isolation.
* All users see the branded sign-in. Administrators and unrestricted users keep normal menus.
* On some login-page variants (e.g. a website replaces `web.login`) the view inheritance or styling may need an adjustment.
* Test Odoo 19 Community/Enterprise runtime installation and QWeb rendering before production. Not NBR certification.

## Tests

1. Open `/web/login` in a private window; confirm Zencore branding, errors, reset and login work.
2. Log in as dedicated VAT user; verify landing in VAT Dashboard and only ZSL VAT app on the app menu.
3. Confirm all children under ZSL VAT function with assigned permissions.
4. Log in as admin; confirm other apps still visible.
5. Log out, log in with invalid credentials; confirm default authentication error is preserved.
6. Confirm direct URL/API access matches ACL and record rules rather than relying on hidden menus.
7. Upgrade `zsl_vat_portal_branding` and retest; verify no change to core VAT logic.

## Odoo 19 login view compatibility fix (19.0.1.0.1)

The official Odoo 19 `web.login` template uses `t-attf-class` rather than `class` on its `<form>`. The former class-based XPath fails on installation. The inheritance now targets `//form[@role='form' and @method='post']`, retaining Odoo's own login processing, CSRF and password reset behavior.

On an installation that failed with the original ParseError, replace the addon directory, restart the server and click Install again. If the addon is installed already, upgrade it on a staging database.

This change is verified against the upstream Odoo 19 login template structure and via static XPath tests, but not executed in the user's Odoo database.
