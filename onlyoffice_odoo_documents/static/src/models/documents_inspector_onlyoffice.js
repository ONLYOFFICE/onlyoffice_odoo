/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2023
 *
*/

import { patch } from 'web.utils';
import { DocumentsInspector } from '@documents/views/inspector/documents_inspector';

const oo_editable_formats = [
    "docx",
    "docxf",
    "xlsx",
    "pptx",
]

const oo_viewable_formats = [
    "djvu",
    "doc",
    "docm",
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
    "pdf",
    "rtf",
    "txt",
    "xps",
    "xml",
    "oform",
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

patch(DocumentsInspector.prototype, "ONLYOFFICE_patch", {
    showOnlyofficeButton(records) {
        if (records.length !== 1) return false;
        const ext = records[0].data.display_name.split('.').pop()
        return records.length === 1 && 
            (this.onlyofficeCanEdit(ext) || this.onlyofficeCanView(ext));
    },
    onlyofficeCanEdit(extension) {
        return oo_editable_formats.includes(extension);
    },
    onlyofficeCanView(extension) {
        return oo_viewable_formats.includes(extension);  
    },
    onlyofficeEditorUrl(id) {
        window.open(`/onlyoffice/editor/document/${id}`, '_blank');
    }
});