import { patch } from "@web/core/utils/patch";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";
import { AccountReportHeader } from "@account_reports/components/account_report/header/header";

patch(AccountReportHeader.prototype, {
    async onCategoryChange(ev) {
        const val = ev.target.value;
        const categoryId = val ? parseInt(val, 10) : false;
        this.controller.cachedFilterOptions.product_category_id = categoryId;
        await this.controller.reload("product_category_id", this.controller.cachedFilterOptions);
    },
});

patch(AccountReportFilters.prototype, {
    async onTopCategorySelect(categoryId) {
        this.controller.cachedFilterOptions.product_category_id = categoryId || false;
        await this.controller.reload("product_category_id", this.controller.cachedFilterOptions);
    },
});
