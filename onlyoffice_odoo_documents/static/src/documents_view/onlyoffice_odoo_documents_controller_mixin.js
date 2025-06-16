/** @odoo-module **/

import { ShareDialog } from "@onlyoffice_odoo_documents/documents_view/share/advanced_share"
import { CreateDialog } from "@onlyoffice_odoo_documents/onlyoffice_create_template/onlyoffice_create_template_dialog"
import { useService } from "@web/core/utils/hooks"

export const OnlyofficeDocumentsControllerMixin = {
  setup() {
    this._super(...arguments)
    this.action = useService("action")
    this.dialogService = useService("dialog")
    this.notification = useService("notification")
  },

  // eslint-disable-next-line sort-keys
  async onClickCreateOnlyoffice() {
    this.dialogService.add(CreateDialog, {
      context: this.props.context,
      folderId: this.env.searchModel.getSelectedFolderId(),
      model: this.env.model,
      onShare: (document_id) => this.onClickAdvancedShare(document_id),
    })
  },
  // eslint-disable-next-line sort-keys
  async onClickAdvancedShare(document_id) {
    this.dialogService.add(ShareDialog, {
      document_id: document_id || (await this.env.model.root.getResIds(true)),
      folderId: this.env.searchModel.getSelectedFolderId(),
      onChangesSaved: () => this.env.searchModel.trigger("update"),
    })
  },
}
