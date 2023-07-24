/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2023
 *
*/

import { registerPatch } from '@mail/model/model_core';
import { attr } from '@mail/model/model_field';

registerPatch({
    name: 'AttachmentCard',
    fields: {
        showOnlyofficeButton: attr({
            compute() {
                return this.attachment.onlyofficeCanEdit || this.attachment.onlyofficeCanView;
            },
        }),
    },
});