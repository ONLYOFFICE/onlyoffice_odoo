/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { onWillStart } from "@odoo/owl"
import { _t } from "@web/core/l10n/translation"
import { useService } from "@web/core/utils/hooks"
import { CreateModeDialog } from "./create_mode_dialog/create_mode_dialog"

export const OnlyofficeDocumentsControllerMixin = () => ({
  setup() {
    super.setup(...arguments)
    this.action = useService("action")
    this.dialogService = useService("dialog")
    this.notification = useService("notification")
    onWillStart(async () => (this.formats = await this.loadFormats()))
  },

  // eslint-disable-next-line sort-keys
  getTopBarActionMenuItems() {
    const menuItems = super.getTopBarActionMenuItems()
    const selectionCount = this.model.targetRecords.length
    const singleSelection = selectionCount === 1 && this.targetRecords[0]
    return {
      ...menuItems,
      onlyofficeEdit: {
        callback: () => this.onlyofficeEditorUrl(singleSelection),
        description: _t("Open in ONLYOFFICE"),
        groupNumber: 1,
        isAvailable: () => this.documentService.userIsInternal && this.showOnlyofficeButton(singleSelection),
        sequence: 52,
      },
    }
  },

  async loadFormats() {
    try {
      const response = await fetch("/onlyoffice_odoo/static/assets/document_formats/onlyoffice-docs-formats.json")
      return await response.json()
    } catch (error) {
      console.error("Error loading formats data:", error)
    }
  },

  async onClickCreateOnlyoffice() {
    this.dialogService.add(CreateModeDialog, {
      context: this.props.context,
      folderId: this.env.searchModel.getSelectedFolderId(),
      model: this.env.model,
      onShare: (document_id) => this.documentService.openSharingDialog([document_id]),
    })
  },

  onlyofficeCanEdit(extension) {
    const format = this.formats.find((f) => f.name === extension.toLowerCase())
    return format && format.actions && format.actions.includes("edit")
  },

  onlyofficeCanView(extension) {
    const format = this.formats.find((f) => f.name === extension.toLowerCase())
    return format && format.actions && (format.actions.includes("view") || format.actions.includes("edit"))
  },

  _parseJsonOrNotify(payload) {
    try {
      return JSON.parse(payload)
    } catch {
      this.notification.add(_t("Unexpected server response"), { type: "danger" })
      return null
    }
  },

  _openEditorTab(documentId) {
    documentId = Number(documentId)
    if (!Number.isInteger(documentId) || documentId <= 0) {
      this.notification.add(_t("Invalid document reference returned by the server"), { type: "danger" })
      return
    }
    const target = new URL(`/onlyoffice/editor/document/${documentId}`, window.location.origin)
    if (target.origin !== window.location.origin) {
      this.notification.add(_t("Invalid document reference returned by the server"), { type: "danger" })
      return
    }
    return this.actionService.doAction({
      type: "ir.actions.act_url",
      target: "new",
      url: target.href,
    })
  },

  async onlyofficeEditorUrl(doc) {
    const demo = this._parseJsonOrNotify(await this.orm.call("onlyoffice.odoo", "get_demo"))
    if (!demo) {
      return
    }
    if (demo && demo.mode && demo.date) {
      const isValidDate = (d) => d instanceof Date && !isNaN(d)
      demo.date = new Date(Date.parse(demo.date))
      if (isValidDate(demo.date)) {
        const today = new Date()
        const difference = Math.floor((today - demo.date) / (1000 * 60 * 60 * 24))
        if (difference > 30) {
          this.notification.add(
            _t("The 30-day test period is over, you can no longer connect to demo ONLYOFFICE Docs server"),
            {
              title: _t("ONLYOFFICE Docs server"),
              type: "warning",
            },
          )
          return
        }
      }
    }
    const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")
    const sameTabPayload = this._parseJsonOrNotify(await this.orm.call("onlyoffice.odoo", "get_same_tab"))
    if (!sameTabPayload) {
      return
    }
    const { same_tab } = sameTabPayload
    if (same_tab && !isDesktopEditor) {
      const action = {
        params: { document_id: doc.data.id },
        tag: "onlyoffice_editor",
        target: "current",
        type: "ir.actions.client",
      }
      return this.actionService.doAction(action)
    }
    return this._openEditorTab(doc.data.id)
  },

  showOnlyofficeButton(records) {
    if (records?.data?.display_name) {
      const ext = records?.data?.display_name.split(".").pop()
      return this.onlyofficeCanEdit(ext) || this.onlyofficeCanView(ext)
    }
    return false
  },
})
