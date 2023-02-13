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
        onlyofficeFormat: attr(),
        onlyofficeEditorUrl: attr({
            compute() {
                const accessTokenQuery = this.accessToken ? `?access_token=${this.accessToken}` : '';
                return `/onlyoffice/editor/${this.id}${accessTokenQuery}`;
            },
        }),
        onlyofficeCanEdit: attr({
            compute() {
                if (!this.originThread || !this.originThread) return false;
                return this.originThread.hasWriteAccess && this.onlyofficeFormat && this.onlyofficeFormat.edit;
            },
        }),
        onlyofficeCanView: attr({
            compute() {
                if (!this.originThread || !this.originThread.onlyoffice_formats) return false;
                return this.originThread.hasReadAccess && this.onlyofficeFormat;
            },
        }),
    }
});