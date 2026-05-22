/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { Dialog } from "@web/core/dialog/dialog"
import { useHotkey } from "@web/core/hotkeys/hotkey_hook"
import { _t } from "@web/core/l10n/translation"
import { rpc } from "@web/core/network/rpc"

const { Component, useState, onWillStart } = owl

export class FolderSelectionDialog extends Component {
  setup() {
    this.rpc = rpc
    this.data = this.env.dialogData
    useHotkey("escape", () => this.data.close())

    this.state = useState({
      folders: [],
      selectedFolderId: null,
      isLoading: true,
    })

    onWillStart(async () => {
      await this.fetchFolders()
    })
  }

  async fetchFolders() {
    this.state.isLoading = true
    try {
      const folders = await this.rpc("/onlyoffice/template/documents/folders", {})
      this.state.folders = folders
    } catch (e) {
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

  async onConfirm() {
    if (this.state.selectedFolderId && this.props.onFolderSelected) {
      await this.props.onFolderSelected(this.state.selectedFolderId)
    }
    this.data.close()
  }

  isConfirmDisabled() {
    return this.state.selectedFolderId === null
  }
}

FolderSelectionDialog.template = "onlyoffice_odoo_templates.FolderSelectionDialog"
FolderSelectionDialog.components = { Dialog }
