/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { Component, proxy, useProps } from "@odoo/owl"
import { FormGallery } from "@onlyoffice_odoo/views/form_gallery/form_gallery"
import { CreateDialog } from "@onlyoffice_odoo_documents/onlyoffice_create_template/onlyoffice_create_template_dialog"
import { Dialog } from "@web/core/dialog/dialog"
import { useHotkey } from "@web/core/hotkeys/hotkey_hook"
import { _t } from "@web/core/l10n/translation"
import { rpc } from "@web/core/network/rpc"
import { useService } from "@web/core/utils/hooks"

export class CreateModeDialog extends Component {
  props = useProps()

  setup() {
    this.orm = useService("orm")
    this.rpc = rpc
    this.data = this.env.dialogData
    useHotkey("escape", () => this.data.close())

    this.dialogTitle = _t("Create with ONLYOFFICE")
    this.state = proxy({
      isChosen: false,
      selectedMode: null,
    })
    this.dialogService = useService("dialog")
    this.notification = useService("notification")
    this.actionService = useService("action")
  }

  async _choiceDialog() {
    if (this._buttonDisabled()) {
      return
    }
    this.state.isChosen = true
    const selectedMode = this.state.selectedMode
    if (selectedMode === "blank") {
      this.create()
    } else if (selectedMode === "template") {
      this.formGallery()
    }
    return
  }

  create() {
    this.dialogService.add(CreateDialog, {
      context: this.props.context,
      folderId: this.props.folderId,
      model: this.props.model,
      onShare: this.props.onShare,
    })
    this.data.close()
  }

  formGallery() {
    const download = async (form) => {
      const json = await this.rpc("/onlyoffice/documents/file/create", {
        folder_id: this.props.folderId,
        supported_format: form.attributes.file_oform.data[0].attributes.url.split(".").pop(),
        title: form.attributes.name_form,
        url: form.attributes.file_oform.data[0].attributes.url,
      })
      const result = this._parseJsonOrNotify(json)
      if (!result) {
        return
      }
      if (result.error) {
        this.notification.add(result.error, {
          sticky: false,
          type: "error",
        })
      } else {
        this.props.model.load()
        this.props.model.notify()
        this.notification.add(_t("New document created in Documents"), {
          sticky: false,
          type: "info",
        })
        const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")
        const sameTabPayload = this._parseJsonOrNotify(await this.orm.call("onlyoffice.odoo", "get_same_tab"))
        if (!sameTabPayload) {
          return
        }
        const { same_tab } = sameTabPayload
        if (same_tab && !isDesktopEditor) {
          this.data.close()
          const action = {
            params: { document_id: result.document_id },
            tag: "onlyoffice_editor",
            target: "current",
            type: "ir.actions.client",
          }
          await this.actionService.doAction(action)
        } else {
          this._openEditorTab(result.document_id)
        }
      }
    }
    this.dialogService.add(
      FormGallery,
      {
        onDownload: download,
        showType: true,
      },
      {
        onClose: () => {
          this.data.close()
        },
      },
    )
  }

  _selectedMode(format) {
    this.state.selectedMode = format
  }

  _parseJsonOrNotify(payload) {
    try {
      return JSON.parse(payload)
    } catch {
      this.notification.add(_t("Unexpected server response"), { type: "error" })
      return null
    }
  }

  _openEditorTab(documentId) {
    documentId = Number(documentId)
    if (!Number.isInteger(documentId) || documentId <= 0) {
      this.notification.add(_t("Invalid document reference returned by the server"), { type: "error" })
      return
    }
    const target = new URL(`/onlyoffice/editor/document/${documentId}`, window.location.origin)
    if (target.origin !== window.location.origin) {
      this.notification.add(_t("Invalid document reference returned by the server"), { type: "error" })
      return
    }
    return this.actionService.doAction({
      type: "ir.actions.act_url",
      target: "new",
      url: target.href,
    })
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
