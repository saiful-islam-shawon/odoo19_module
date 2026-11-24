/** @odoo-module **/

/*
 * `mail_enterprise` is auto-installed in this database through web_mobile,
 * while the Community asset bundle intentionally has no `home_menu` service.
 * Its chat-window extension still requests that service, which prevents the
 * whole Owl web client from rendering.  Supply the small, no-home-menu API
 * expected by that extension.  When a real Enterprise service is present we
 * deliberately leave it untouched.
 */
import { registry } from "@web/core/registry";

const services = registry.category("services");

if (!services.contains("home_menu")) {
    services.add("home_menu", {
        start() {
            return {
                hasHomeMenu: false,
                show() {},
                hide() {},
                toggle() {},
            };
        },
    });
}
