/** @odoo-module **/

import { ShareFormViewDialog } from "@documents/views/helper/share_form_view_dialog"
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
      onShare: (document_id) => this.onShareButtonClick(document_id),
    })
  },
  async onShareButtonClick(document_id) {
    const action = await this.env.model.orm.call("onlyoffice.odoo.documents", "open_advanced_share_popup", [
      {
        document_ids: document_id || (await this.env.model.root.getResIds(true)),
        folder_id: this.env.searchModel.getSelectedFolderId(),
      },
    ])

    let saved = false

    const close = this.dialogService.add(
      ShareFormViewDialog,
      {
        context: action.context,
        onDiscard: () => {
          close()
        },
        onSave: async (_record) => {
          saved = true
          this.notification.add(this.env._t("TODO"), { type: "success" })
          close()
        },
        resId: action.res_id,
        resModel: "onlyoffice.odoo.documents",
        title: this.env._t("Advanced Share"),
      },
      {
        onClose: async () => {
          if (!saved) {
            await this.env.model.orm.unlink("onlyoffice.odoo.documents", [action.res_id])
          }
        },
      },
    )
  },
}
