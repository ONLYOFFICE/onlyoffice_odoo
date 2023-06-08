/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2023
 *
 * This program is a free software product. You can redistribute it and/or
 * modify it under the terms of the GNU Affero General Public License (AGPL)
 * version 3 as published by the Free Software Foundation. In accordance with
 * Section 7(a) of the GNU AGPL its Section 15 shall be amended to the effect
 * that Ascensio System SIA expressly excludes the warranty of non-infringement
 * of any third-party rights.
 *
 * This program is distributed WITHOUT ANY WARRANTY; without even the implied
 * warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR  PURPOSE. For
 * details, see the GNU AGPL at: http://www.gnu.org/licenses/agpl-3.0.html
 *
 * You can contact Ascensio System SIA at 20A-12 Ernesta Birznieka-Upisha
 * street, Riga, Latvia, EU, LV-1050.
 *
 * The  interactive user interfaces in modified source and object code versions
 * of the Program must display Appropriate Legal Notices, as required under
 * Section 5 of the GNU AGPL version 3.
 *
 * Pursuant to Section 7(b) of the License you must retain the original Product
 * logo when distributing the program. Pursuant to Section 7(e) we decline to
 * grant you any rights under trademark law for use of our trademarks.
 *
 * All the Product's GUI elements, including illustrations and icon sets, as
 * well as technical writing content are licensed under the terms of the
 * Creative Commons Attribution-ShareAlike 4.0 International. See the License
 * terms at http://creativecommons.org/licenses/by-sa/4.0/legalcode
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
            (this.onlyofficeCanEdit(ext) || this. onlyofficeCanView(ext));
    },
    onlyofficeCanEdit(extension) {
        return oo_editable_formats.includes(extension);
    },
    onlyofficeCanView(extension) {
        return oo_viewable_formats.includes(extension);  
    },
    onlyofficeEditorUrl(id) {
        window.open(`/onlyoffice/editor/${id}`, '_blank');
    }
});