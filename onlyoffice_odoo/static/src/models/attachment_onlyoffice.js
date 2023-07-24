/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2023
 *
*/

import { registerPatch } from '@mail/model/model_core';
import { attr } from '@mail/model/model_field';

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

registerPatch({
    name: 'Attachment',
    recordMethods: {
        openOnlyofficeEditor() {
            window.open(this.onlyofficeEditorUrl, '_blank');
        },

        onClickOnlyofficeEdit(ev) {
            ev.stopPropagation();
            this.openOnlyofficeEditor();
        },
    },
    fields: {
        onlyofficeEditorUrl: attr({
            compute() {
                const accessTokenQuery = this.accessToken ? `?access_token=${this.accessToken}` : '';
                return `/onlyoffice/editor/${this.id}${accessTokenQuery}`;
            },
        }),
        onlyofficeCanEdit: attr({
            compute() {
                return oo_editable_formats.includes(this.extension);
            },
        }),
        onlyofficeCanView: attr({
            compute() {
                return oo_viewable_formats.includes(this.extension);
            },
        }),
    }
});