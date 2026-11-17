import { Component, onWillUnmount, useRef } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class PdfPreviewDialog extends Component {
    static template = "pdf_preview_direct_print.PdfPreviewDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        blob: { type: Object },
        blobUrl: { type: String },
        fileName: { type: String },
        title: { type: String },
    };

    setup() {
        this.pdfFrame = useRef("pdfFrame");
        onWillUnmount(() => {
            // Free the object URL once the dialog is gone.
            URL.revokeObjectURL(this.props.blobUrl);
        });
    }

    get frameSrc() {
        // Hide the sidebar of the built-in browser PDF viewer, keep the toolbar.
        return `${this.props.blobUrl}#pagemode=none&navpanes=0`;
    }

    /** Send the previewed PDF to the browser's native print dialog. */
    print() {
        const frame = this.pdfFrame.el;
        try {
            frame.contentWindow.focus();
            frame.contentWindow.print();
        } catch (error) {
            console.warn("[pdf_preview_direct_print] print() failed, opening in a tab", error);
            window.open(this.props.blobUrl, "_blank");
        }
    }

    /** Save a copy of the PDF. */
    download() {
        const link = document.createElement("a");
        link.href = this.props.blobUrl;
        link.download = this.props.fileName;
        document.body.appendChild(link);
        link.click();
        link.remove();
    }
}
