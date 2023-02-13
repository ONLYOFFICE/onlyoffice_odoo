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

        async fetchOnlyofficeCard() {
            const res = await this.messaging.rpc({
                route: `/onlyoffice/file/card/${this.id}`,
            }, { shadow: true });

            const values = { onlyofficeFormat: res };

            this.update(values);
        }
    },
    fields: {
        onlyofficeFormat: attr({
            compute() {
                this.fetchOnlyofficeCard();
                return false;
            }
        }),
        onlyofficeEditorUrl: attr({
            compute() {
                const accessTokenQuery = this.accessToken ? `?access_token=${this.accessToken}` : '';
                return `/onlyoffice/editor/${this.id}${accessTokenQuery}`;
            },
        }),
        onlyofficeCanEdit: attr({
            compute() {
                return this.onlyofficeFormat && this.onlyofficeFormat.canEdit;
            },
        }),
        onlyofficeCanView: attr({
            compute() {
                return this.onlyofficeFormat && this.onlyofficeFormat.canView;
            },
        }),
    }
});