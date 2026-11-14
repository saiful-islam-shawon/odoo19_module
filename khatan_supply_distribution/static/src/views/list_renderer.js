/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

patch(ListRenderer.prototype, {
    computeAggregates() {
        const aggregates = super.computeAggregates(...arguments);
        if (!aggregates) {
            return aggregates;
        }
        for (const [fieldName, agg] of Object.entries(aggregates)) {
            if (agg && agg.help && typeof agg.help === "string" && agg.help.includes("=")) {
                let prefix = agg.help.trim();
                prefix = prefix.replace(/\s*=\s*$/, " =");
                const currentVal = String(agg.value || "").trim();
                if (!currentVal.startsWith(prefix)) {
                    agg.value = `${prefix} ${currentVal}`;
                }
            }
        }
        return aggregates;
    },
});
