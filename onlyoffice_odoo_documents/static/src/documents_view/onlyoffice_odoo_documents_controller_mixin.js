/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { ShareDialog } from "@onlyoffice_odoo_documents/documents_view/share/advanced_share"
import { _t } from "@web/core/l10n/translation"
import { useService } from "@web/core/utils/hooks"
import { ConvertDialog } from "./convert_dialog/convert_dialog"
import { CreateModeDialog } from "./create_mode_dialog/create_mode_dialog"

export const OnlyofficeDocumentsControllerMixin = () => ({
  setup() {
    super.setup(...arguments)
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
  async onClickAdvancedShare(document_id = null, openEditor = false) {
    if (!document_id) {
      const selection = this.env.model.root.selection
      document_id = selection.filter((rec) => rec._values.type !== "empty").map((rec) => rec.resId)
    }
    this.dialogService.add(ShareDialog, {
      document_id: document_id,
      openEditor,
    })
  },

  async onClickConvert() {
    const selection = this.env.model.root.selection.filter((rec) => rec._values.type !== "empty")
    if (selection.length !== 1) {
      this.notification.add(_t("Please select exactly one document to convert"), { type: "warning" })
      return
    }
    const record = selection[0]
    this.dialogService.add(ConvertDialog, {
      documentId: record.resId,
      filename: record.data.display_name || record.data.name,
      model: this.env.model,
    })
  },
})
