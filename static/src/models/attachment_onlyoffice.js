/** @odoo-module **/

import { registerPatch } from '@mail/model/model_core';
import { attr, many, one } from '@mail/model/model_field';
import { clear, insert } from '@mail/model/model_field_command';

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
    }
});