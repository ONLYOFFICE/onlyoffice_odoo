/** @odoo-module **/
/* eslint-disable @stylistic/multiline-ternary */

import { ShareFormViewDialog } from "@documents/views/helper/share_form_view_dialog"
import { CreateDialog } from "@onlyoffice_odoo_documents/onlyoffice_create_template/onlyoffice_create_template_dialog"
import { x2ManyCommands } from "@web/core/orm_service"
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
    })
  },
  async onShareButtonClick() {
    const action = await this.env.model.orm.call("onlyoffice.odoo.documents", "open_advanced_share_popup", [
      {
        document_ids: this.env.model.root.selection.length
          ? [[6, 0, await this.env.model.root.getResIds(true)]]
          : false,
        domain: this.env.searchModel.domain,
        folder_id: this.env.searchModel.getSelectedFolderId(),
        tag_ids: [x2ManyCommands.replaceWith(this.env.searchModel.getSelectedTagIds())],
        type: this.env.model.root.selection.length ? "ids" : "domain",
      },
    ])
    const shareResId = action.res_id
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
        resId: shareResId,
        resModel: "onlyoffice.odoo.documents",
      },
      {
        onClose: async () => {
          if (!saved) {
            await this.env.model.orm.unlink("onlyoffice.odoo.documents", [shareResId])
          }
        },
      },
    )
  },
}
