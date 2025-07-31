/** @odoo-module **/

import { FormGalleryDialog } from "@onlyoffice_odoo_documents/documents_view/form_gallery_dialog/form_gallery_dialog"
import { CreateDialog } from "@onlyoffice_odoo_documents/onlyoffice_create_template/onlyoffice_create_template_dialog"
import { Dialog } from "@web/core/dialog/dialog"
import { useHotkey } from "@web/core/hotkeys/hotkey_hook"
import { useService } from "@web/core/utils/hooks"

const { Component, useState } = owl

export class CreateModeDialog extends Component {
  setup() {
    this.data = this.env.dialogData
    useHotkey("escape", () => this.data.close())

    this.dialogTitle = this.env._t("Create with ONLYOFFICE")
    this.state = useState({
      isChosen: false,
      selectedMode: null,
    })
    this.dialogService = useService("dialog")
  }

  async _choiceDialog() {
    if (this._buttonDisabled()) {
      return
    }
    this.state.isChosen = true
    const selectedMode = this.state.selectedMode
    if (selectedMode === null) {
      return
    }
    if (selectedMode === "blank") {
      this.dialogService.add(CreateDialog, {
        context: this.props.context,
        folderId: this.props.folderId,
        model: this.props.model,
        onShare: this.props.onShare,
      })
    } else if (selectedMode === "template") {
      this.dialogService.add(FormGalleryDialog, {
        context: this.props.context,
        folderId: this.props.folderId,
        model: this.props.model,
      })
    }
    this.data.close()
    return
  }

  _selectedMode(format) {
    this.state.selectedMode = format
  }

  _isSelected(format) {
    return this.state.selectedMode === format
  }

  _buttonDisabled() {
    return this.state.isChosen || this.state.selectedMode === null
  }
}
CreateModeDialog.components = { Dialog }
CreateModeDialog.template = "onlyoffice_odoo_documents.CreateModeDialog"
