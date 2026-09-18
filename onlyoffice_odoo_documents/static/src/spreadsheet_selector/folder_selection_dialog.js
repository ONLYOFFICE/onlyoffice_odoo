/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { Dialog } from "@web/core/dialog/dialog"
import { useHotkey } from "@web/core/hotkeys/hotkey_hook"
import { _t } from "@web/core/l10n/translation"
import { useService } from "@web/core/utils/hooks"

const { Component, onWillStart, useState } = owl

/**
 * Asks for a workspace and a file name before a blank ONLYOFFICE spreadsheet is created.
 * The choice is reported through the onConfirmed prop; nothing is reported on cancel.
 */
export class FolderSelectionDialog extends Component {
  setup() {
    this.rpc = useService("rpc")
    this.data = this.env.dialogData
    useHotkey("escape", () => this.data.close())

    this.dialogTitle = _t("New ONLYOFFICE spreadsheet")
    this.state = useState({
      folders: [],
      isLoading: true,
      name: this.props.defaultName || _t("Untitled spreadsheet"),
      selectedFolderId: null,
    })

    onWillStart(() => this.fetchFolders())
  }

  async fetchFolders() {
    this.state.isLoading = true
    try {
      this.state.folders = await this.rpc("/onlyoffice/documents/folders", {})
    } catch {
      this.state.folders = []
    }
    this.state.isLoading = false
  }

  selectFolder(folderId) {
    this.state.selectedFolderId = folderId
  }

  isSelected(folderId) {
    return this.state.selectedFolderId === folderId
  }

  isConfirmDisabled() {
    return this.state.selectedFolderId === null || !this.state.name.trim()
  }

  onConfirm() {
    if (this.isConfirmDisabled()) {
      return
    }
    this.props.onConfirmed({
      folderId: this.state.selectedFolderId,
      name: this.state.name.trim(),
    })
    this.data.close()
  }
}

FolderSelectionDialog.components = { Dialog }
FolderSelectionDialog.template = "onlyoffice_odoo_documents.FolderSelectionDialog"
