/** @odoo-module **/

import { CreateDialog } from "@onlyoffice_odoo_documents/onlyoffice_create_template/onlyoffice_create_template_dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export const OnlyofficeDocumentsControllerMixin = {
    setup() {
        this._super(...arguments);
        this.action = useService("action");
        this.dialogService = useService("dialog");
    },

    async onClickCreateOnlyoffice(ev) {
        this.dialogService.add(CreateDialog, {
            folderId: this.env.searchModel.getSelectedFolderId(),
            context: this.props.context,
        });
    },
};
