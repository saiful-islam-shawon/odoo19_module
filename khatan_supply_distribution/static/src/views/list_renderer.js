/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";
import { SectionAndNoteListRenderer } from "@account/components/section_and_note_fields_backend/section_and_note_fields_backend";
import { ProductLabelSectionAndNoteListRender } from "@account/components/product_label_section_and_note_field/product_label_section_and_note_field_o2m";

const totalLabelPatch = {
    get hasTotalLabel() {
        if (this.aggregates && Object.keys(this.aggregates).length > 0) {
            return true;
        }
        if (typeof this.getFirstAggregateIndex === "function" && this.getFirstAggregateIndex() > -1) {
            return true;
        }
        return false;
    },
};

patch(ListRenderer.prototype, totalLabelPatch);
patch(SectionAndNoteListRenderer.prototype, totalLabelPatch);
patch(ProductLabelSectionAndNoteListRender.prototype, totalLabelPatch);

