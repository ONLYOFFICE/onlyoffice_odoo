/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { Component, proxy, signal, useProps } from "@odoo/owl"
import { Dialog } from "@web/core/dialog/dialog"

import { useHotkey } from "@web/core/hotkeys/hotkey_hook"
import { _t } from "@web/core/l10n/translation"
import { rpc } from "@web/core/network/rpc"
import { KeepLast } from "@web/core/utils/concurrency"
import { useAutofocus, useService } from "@web/core/utils/hooks"
import { useSubEnv } from "@web/owl2/utils"
import { getDefaultConfig } from "@web/views/view"

export class CreateDialog extends Component {
  inputRef = signal.ref()

  props = useProps()

  setup() {
    this.orm = useService("orm")
    this.rpc = rpc
    this.viewService = useService("view")
    this.notificationService = useService("notification")
    this.actionService = useService("action")
    useAutofocus({ ref: this.inputRef })
    this.documentService = useService("document.document")

    this.data = this.env.dialogData
    useHotkey("escape", () => this.data.close())

    this.dialogTitle = _t("Create with ONLYOFFICE")
    this.state = proxy({
      isCreating: false,
      isOpen: true,
      selectedFormat: "docx",
      title: _t("New Document"),
    })
    useSubEnv({ config: { ...getDefaultConfig() } })
    this.keepLast = new KeepLast()

    if (this.inputRef()) {
      this.inputRef().focus()
    }
  }

  async _createFile(configureAccess = false) {
    if (this._buttonDisabled()) {
      return
    }
    this.state.isCreating = true
    const selectedFormat = this.state.selectedFormat
    const title = this.state.title

    const json = await this.rpc("/onlyoffice/documents/file/create", {
      folder_id: this.props.folderId,
      supported_format: selectedFormat,
      title: title,
    })

    const result = this._parseJsonOrNotify(json)
    if (!result) {
      return
    }

    this.props.model.load()
    this.props.model.notify()

    if (result.error) {
      this.notificationService.add(result.error, {
        sticky: false,
        type: "danger",
      })
    } else {
      this.notificationService.add(_t("New document created in Documents"), {
        sticky: false,
        type: "info",
      })

      if (configureAccess) {
        await new Promise((resolve) => setTimeout(resolve, 500))
        this.data.close()
        await this.documentService.openSharingDialog(result.document_id)
      } else {
        const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")
        const sameTabPayload = this._parseJsonOrNotify(await this.orm.call("onlyoffice.odoo", "get_same_tab"))
        if (!sameTabPayload) {
          return
        }
        const { same_tab } = sameTabPayload
        this.data.close()
        if (same_tab && !isDesktopEditor) {
          const action = {
            params: { document_id: result.document_id },
            tag: "onlyoffice_editor",
            target: "current",
            type: "ir.actions.client",
          }
          return this.actionService.doAction(action)
        }
        return this._openEditorTab(result.document_id)
      }
    }
  }

  _selectedFormat(format) {
    this.state.selectedFormat = format
  }

  _isSelected(format) {
    return this.state.selectedFormat === format
  }

  _hasSelection() {
    return Boolean(this.state.selectedFormat)
  }

  _parseJsonOrNotify(payload) {
    try {
      return JSON.parse(payload)
    } catch {
      this.notificationService.add(_t("Unexpected server response"), { type: "danger" })
      return null
    }
  }

  _openEditorTab(documentId) {
    documentId = Number(documentId)
    if (!Number.isInteger(documentId) || documentId <= 0) {
      this.notificationService.add(_t("Invalid document reference returned by the server"), { type: "danger" })
      return
    }
    const target = new URL(`/onlyoffice/editor/document/${documentId}`, window.location.origin)
    if (target.origin !== window.location.origin) {
      this.notificationService.add(_t("Invalid document reference returned by the server"), { type: "danger" })
      return
    }
    return this.actionService.doAction({
      type: "ir.actions.act_url",
      target: "new",
      url: target.href,
    })
  }

  _buttonDisabled() {
    return this.state.isCreating || !this._hasSelection() || !this.state.title
  }
}
CreateDialog.components = { Dialog }
CreateDialog.template = "onlyoffice_odoo_documents.CreateDialog"
