/** @odoo-module **/

import { ShareDialog } from "@onlyoffice_odoo_documents/documents_view/share/advanced_share"
import { useService } from "@web/core/utils/hooks"
import { CreateModeDialog } from "./create_mode_dialog/create_mode_dialog"

export const OnlyofficeDocumentsControllerMixin = {
  setup() {
    this._super(...arguments)
    this.action = useService("action")
    this.dialogService = useService("dialog")
    this.notification = useService("notification")
  },

  // eslint-disable-next-line sort-keys
  async onClickCreateOnlyoffice() {
    this.dialogService.add(CreateModeDialog, {
      context: this.props.context,
      folderId: this.env.searchModel.getSelectedFolderId(),
      model: this.env.model,
      onShare: (document_id) => this.onClickAdvancedShare(document_id, true),
    })
  },
  // eslint-disable-next-line sort-keys
  async onClickAdvancedShare(document_id, openEditor = false) {
    this.dialogService.add(ShareDialog, {
      document_id: document_id || (await this.env.model.root.getResIds(true)),
      openEditor,
    })
  },
}
