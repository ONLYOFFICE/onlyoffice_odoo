/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2024
 *
 */

import { DocumentsInspector } from "@documents/views/inspector/documents_inspector"
import { useService } from "@web/core/utils/hooks"
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

patch(DocumentsInspector.prototype, {
  setup() {
    super.setup(...arguments)
    this.notification = useService("notification")
    this.actionService = useService("action")
    this.onlyofficeEditorUrl = this.onlyofficeEditorUrl.bind(this)
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
  async onlyofficeEditorUrl(id) {
    const demo = JSON.parse(await this.env.services.orm.call("onlyoffice.odoo", "get_demo"))
    if (demo && demo.mode && demo.date) {
      const isValidDate = (d) => d instanceof Date && !isNaN(d)
      demo.date = new Date(Date.parse(demo.date))
      if (isValidDate(demo.date)) {
        const today = new Date()
        const difference = Math.floor((today - demo.date) / (1000 * 60 * 60 * 24))
        if (difference > 30) {
          this.notification.add(
            this.env._t("The 30-day test period is over, you can no longer connect to demo ONLYOFFICE Docs server"),
            {
              title: this.env._t("ONLYOFFICE Docs server"),
              type: "warning",
            },
          )
          return
        }
      }
    }
    const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")
    const { same_tab } = JSON.parse(await this.env.services.orm.call("onlyoffice.odoo", "get_same_tab"))
    if (same_tab && !isDesktopEditor) {
      const action = {
        params: { document_id: id },
        tag: "onlyoffice_editor",
        target: "current",
        type: "ir.actions.client",
      }
      return this.actionService.doAction(action)
    }
    window.open(`/onlyoffice/editor/document/${id}`, "_blank")
  },
  showOnlyofficeButton(records) {
    if (records.length !== 1) {
      return false
    }
    const ext = records[0].data.display_name.split(".").pop()
    return records.length === 1 && (this.onlyofficeCanEdit(ext) || this.onlyofficeCanView(ext))
  },
})
