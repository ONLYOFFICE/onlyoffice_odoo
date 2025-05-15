/** @odoo-module **/

import { CreateDialog } from "@onlyoffice_odoo_documents/onlyoffice_create_template/onlyoffice_create_template_dialog"
import { useService } from "@web/core/utils/hooks"

export const OnlyofficeDocumentsControllerMixin = {
  setup() {
    this._super(...arguments)
    this.action = useService("action")
    this.dialogService = useService("dialog")
  },

  // eslint-disable-next-line sort-keys
  async onClickCreateOnlyoffice() {
    this.dialogService.add(CreateDialog, {
      context: this.props.context,

      folderId: this.env.searchModel.getSelectedFolderId(),
      model: this.env.model,
    })
  },
}
