/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class VatDashboard extends Component {
    static template = "zsl_vat.VatDashboard";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: {}, loaded: false });
        onWillStart(async () => {
            this.state.data = await this.orm.call("vat.return", "get_dashboard_data", []);
            this.state.loaded = true;
        });
    }
    format(value) {
        return new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
    }
    openReturns() { this.action.doAction("zsl_vat.action_vat_return"); }
    openVds() { this.action.doAction("zsl_vat.action_vds_certificate"); }
    openPeriods() { this.action.doAction("zsl_vat.action_vat_period"); }
    openTreasury() { this.action.doAction("zsl_vat.action_vat_treasury_payment"); }
    openSales() { this.action.doAction("account.action_move_out_invoice_type"); }
    openPurchases() { this.action.doAction("account.action_move_in_invoice_type"); }
}
registry.category("actions").add("zsl_vat.dashboard", VatDashboard);
