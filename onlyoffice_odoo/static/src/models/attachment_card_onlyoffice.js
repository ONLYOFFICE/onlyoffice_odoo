/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2024
 *
*/

import { AttachmentList } from "@mail/core/common/attachment_list";
import { patch } from "@web/core/utils/patch";

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

patch(AttachmentList.prototype, {
    onlyofficeCanOpen(attachment) {
        return oo_editable_formats.includes(attachment.extension) || oo_viewable_formats.includes(attachment.extension);
    },
    openOnlyoffice(attachment) {
        const accessTokenQuery = attachment.accessToken ? `?access_token=${attachment.accessToken}` : '';
        window.open(`/onlyoffice/editor/${attachment.id}${accessTokenQuery}`, '_blank');
    }
});