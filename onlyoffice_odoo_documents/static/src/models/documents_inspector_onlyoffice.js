/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2024
 *
*/

import { patch } from "@web/core/utils/patch";
import { DocumentsControlPanel } from "@documents/views/search/documents_control_panel";

import { _t } from "@web/core/l10n/translation";

const oo_editable_formats = [
    "docx",
    "xlsx",
    "pptx",
    "pdf",
]

const oo_viewable_formats = [
    "djvu",
    "doc",
    "docm",
    "docxf",
    "dot",
    "dotm",
    "dotx",
    "epub",
    "fb2",
    "fodt",
    "html",
    "mht",
    "odt",
    "ott",
    "oxps",
    "rtf",
    "txt",
    "xps",
    "xml",
    "csv",
    "fods",
    "ods",
    "ots",
    "xls",
    "xlsb",
    "xlsm",
    "xlt",
    "xltm",
    "xltx",
    "fodp",
    "odp",
    "otp",
    "pot",
    "potm",
    "potx",
    "pps",
    "ppsm",
    "ppsx",
    "ppt",
    "pptm",
];

patch(DocumentsControlPanel.prototype, {
    showOnlyofficeButton(records) {
        if (records?.data?.display_name) {
            const ext = records?.data?.display_name.split('.').pop()
            return (this.onlyofficeCanEdit(ext) || this.onlyofficeCanView(ext))
        } else {
            return false
        }
    },
    onlyofficeCanEdit(extension) {
        return oo_editable_formats.includes(extension);
    },
    onlyofficeCanView(extension) {
        return oo_viewable_formats.includes(extension);  
    },
    async onlyofficeEditorUrl() {
        const doc = this.env.model.root.selection[0];
        var demo = await this.orm.call('ir.config_parameter', 'get_param', ['onlyoffice_connector.doc_server_demo']);
        var demoDate = await this.orm.call('ir.config_parameter', 'get_param', ['onlyoffice_connector.doc_server_demo_date']);
        demoDate = new Date(Date.parse(demoDate))
        if (demo && demoDate && demoDate instanceof Date) {
            const today = new Date();
            const difference = Math.floor((today - new Date(Date.parse(demoDate))) / (1000 * 60 * 60 * 24));
            if (difference > 30) {
                this.notification.add(
                    _t(
                        "The 30-day test period is over, you can no longer connect to demo ONLYOFFICE Docs server"
                    ),
                    {
                        title: _t("ONLYOFFICE Docs server"),
                        type: 'warning',
                    }
                );
                return;
            }
        }
        window.open(`/onlyoffice/editor/document/${doc.data.id}`, '_blank');
    }
});