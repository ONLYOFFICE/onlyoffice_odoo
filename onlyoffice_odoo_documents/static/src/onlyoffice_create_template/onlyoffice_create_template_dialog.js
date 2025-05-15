/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog"

import { useHotkey } from "@web/core/hotkeys/hotkey_hook"
import { useService } from "@web/core/utils/hooks"
import { getDefaultConfig } from "@web/views/view"
import { DropPrevious } from "web.concurrency"
import { _t } from "web.core"

const { Component, useState, useSubEnv } = owl

export class CreateDialog extends Component {
  setup() {
    this.orm = useService("orm")
    this.rpc = useService("rpc")
    this.viewService = useService("view")
    this.notificationService = useService("notification")
    this.actionService = useService("action")

    this.data = this.env.dialogData
    useHotkey("escape", () => this.data.close())

    this.dialogTitle = this.env._t("Create with ONLYOFFICE")
    this.state = useState({
      isCreating: false,
      isOpen: true,
      selectedFormat: "docx",
      title: this.env._t("New Document"),
    })
    useSubEnv({ config: { ...getDefaultConfig() } })
    this.dp = new DropPrevious()
  }

  async _createFile() {
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

    const result = JSON.parse(json)

    this.props.model.load()
    this.props.model.notify()

    if (result.error) {
      this.notificationService.add(result.error, {
        sticky: false,
        type: "error",
      })
    } else {
      this.notificationService.add(_t("New document created in Documents"), {
        sticky: false,
        type: "info",
      })

      const { same_tab } = JSON.parse(await this.orm.call("onlyoffice.odoo", "get_same_tab"))
      if (same_tab) {
        const action = {
          params: { attachment_id: result.file_id },
          tag: "onlyoffice_editor",
          target: "current",
          type: "ir.actions.client",
        }
        return this.actionService.doAction(action)
      }
      window.open(`/onlyoffice/editor/${result.file_id}`, "_blank")
    }

    this.data.close()
  }

  _selectedFormat(format) {
    this.state.selectedFormat = format
  }

  _isSelected(format) {
    return this.state.selectedFormat === format
  }

  _hasSelection() {
    // eslint-disable-next-line no-constant-binary-expression, no-implicit-coercion
    return !!this.state.selectedFormat !== null
  }

  _buttonDisabled() {
    return this.state.isCreating || !this._hasSelection() || !this.state.title
  }
}
CreateDialog.components = { Dialog }
CreateDialog.template = "onlyoffice_odoo_documents.CreateDialog"
