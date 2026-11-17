import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { PdfPreviewDialog } from "./pdf_preview_dialog";
import { getResponseFileName } from "./utils";

const LOG = "[pdf_preview_direct_print]";

/**
 * Build the /report/pdf/... URL for a report action. Same shape as Odoo 19's
 * getReportUrl(), but the user context is always merged with the action
 * context (the standard download flow does the same through /report/download).
 */
function buildReportUrl(action) {
    let url = `/report/pdf/${action.report_name}`;
    const actionContext = action.context || {};
    const context = encodeURIComponent(
        JSON.stringify({ ...(user.context || {}), ...actionContext })
    );
    if (action.data && JSON.stringify(action.data) !== "{}") {
        // Wizard-driven reports pass their payload through `data`.
        const options = encodeURIComponent(JSON.stringify(action.data));
        url += `?options=${options}&context=${context}`;
    } else {
        if (actionContext.active_ids) {
            url += `/${actionContext.active_ids.join(",")}`;
        }
        url += `?context=${context}`;
    }
    return url;
}

async function pdfPreviewHandler(action, options, env) {
    if (action.report_type !== "qweb-pdf") {
        return false;
    }
    const url = buildReportUrl(action);
    let response;
    env.services.ui.block();
    try {
        response = await fetch(url, { credentials: "same-origin" });
    } catch (error) {
        console.warn(`${LOG} fetch failed, using standard download`, url, error);
        return false;
    } finally {
        env.services.ui.unblock();
    }
    const contentType = response.headers.get("Content-Type") || "";
    if (!response.ok || !contentType.includes("pdf")) {
        // wkhtmltopdf missing, access error, html fallback... let Odoo's
        // default behaviour take over so nothing ever breaks. Log WHY so it
        // is visible in the browser console (F12).
        let detail = "";
        try {
            detail = (await response.text()).slice(0, 500);
        } catch {
            // ignore
        }
        console.warn(
            `${LOG} not previewable: HTTP ${response.status}, Content-Type "${contentType}". ` +
                `Falling back to standard download.`,
            url,
            detail
        );
        return false;
    }
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    // NOTE: Odoo's action service already calls options.onClose() and handles
    // close_on_report_download once this handler returns true, so we must not
    // do it again when the dialog closes.
    env.services.dialog.add(PdfPreviewDialog, {
        blob,
        blobUrl,
        fileName: getResponseFileName(response, action.name || action.report_name),
        title: action.name || "Report Preview",
    });
    return true;
}

registry
    .category("ir.actions.report handlers")
    .add("pdf_preview_direct_print_handler", pdfPreviewHandler, { sequence: 20 });
