/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2024
 *
 */

import { DocumentsControlPanel } from "@documents/views/search/documents_control_panel"

import { _t } from "@web/core/l10n/translation"
import { patch } from "@web/core/utils/patch"

let formats = []
const loadFormats = async () => {
  try {
    const response = await fetch("/onlyoffice_odoo/static/assets/document_formats/onlyoffice-docs-formats.json")
    formats = await response.json()
  } catch (error) {
    console.error("Error loading formats data:", error)
  }
}

loadFormats()

patch(DocumentsControlPanel.prototype, {
  showOnlyofficeButton(records) {
    if (records?.data?.display_name) {
      const ext = records?.data?.display_name.split(".").pop()
      return this.onlyofficeCanEdit(ext) || this.onlyofficeCanView(ext)
    }
    return false
  },
  // eslint-disable-next-line sort-keys
  onlyofficeCanEdit(extension) {
    const format = formats.find((f) => f.name === extension.toLowerCase())
    return format && format.actions && format.actions.includes("edit")
  },
  onlyofficeCanView(extension) {
    const format = formats.find((f) => f.name === extension.toLowerCase())
    return format && format.actions && (format.actions.includes("view") || format.actions.includes("edit"))
  },
  async onlyofficeEditorUrl() {
    const doc = this.env.model.root.selection[0]
    const demo = JSON.parse(await this.orm.call("onlyoffice.odoo", "get_demo"))
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
    const { same_tab } = JSON.parse(await this.orm.call("onlyoffice.odoo", "get_same_tab"))
    if (same_tab) {
      const action = {
        params: { document_id: doc.data.id },
        tag: "onlyoffice_editor",
        target: "current",
        type: "ir.actions.client",
      }
      return this.actionService.doAction(action)
    }
    window.open(`/onlyoffice/editor/document/${doc.data.id}`, "_blank")
  },
})
