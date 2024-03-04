/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2024
 *
*/

import { registerPatch } from '@mail/model/model_core';
import { attr } from '@mail/model/model_field';
import { _t } from "@web/core/l10n/translation";

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

        async onClickOnlyofficeEdit(ev) {
            ev.stopPropagation();
            var demo = await this.messaging.rpc({
                model: 'ir.config_parameter',
                method: 'get_param',
                args: ['onlyoffice_connector.doc_server_demo']
            });
            var demoDate = await this.messaging.rpc({
                model: 'ir.config_parameter',
                method: 'get_param',
                args: ['onlyoffice_connector.doc_server_demo_date']
            });
            demoDate = new Date(Date.parse(demoDate))
            if (demo && demoDate && demoDate instanceof Date) {
                const today = new Date();
                const difference = Math.floor((today - new Date(Date.parse(demoDate))) / (1000 * 60 * 60 * 24));
                if (difference > 30) {
                    this.messaging.userNotificationManager.sendNotification({
                        message: this.env._t("The 30-day test period is over, you can no longer connect to demo ONLYOFFICE Docs server"),
                        title: this.env._t("ONLYOFFICE Docs server"),
                        type: 'warning',
                    });
                    return;
                }
            }
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