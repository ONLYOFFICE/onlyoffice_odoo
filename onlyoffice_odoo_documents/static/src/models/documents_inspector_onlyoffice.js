/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { DocumentsControlPanel } from "@documents/views/search/documents_control_panel"
import { loadBundle } from "@web/core/assets"
import { formatDateTime } from "@web/core/l10n/dates"
import { _t } from "@web/core/l10n/translation"
import { rpc } from "@web/core/network/rpc"
import { useService } from "@web/core/utils/hooks"
import { patch } from "@web/core/utils/patch"

const { DateTime } = luxon

const getFilenameTimestamp = () => formatDateTime(DateTime.now()).replace(/[\\/:*?"<>|\s]+/g, "_")

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
  setup() {
    super.setup(...arguments)
    this.ui = useService("ui")
  },

  /**
   * Export the spreadsheet with the native o-spreadsheet engine, so charts
   * and other advanced formatting are kept. Throws if the export fails.
   * @param {Number} id documents.document id of the Odoo Spreadsheet.
   * @returns {Promise<{base64: string, name: string}>}
   */
  // eslint-disable-next-line sort-keys
  async _exportSpreadsheetNativeXlsx(id) {
    await loadBundle("spreadsheet.o_spreadsheet")
    const { createSpreadsheetModel, waitForDataLoaded } = odoo.loader.modules.get("@spreadsheet/helpers/model")
    const record = await this.orm.call("documents.document", "join_spreadsheet_session", [id])
    const model = await createSpreadsheetModel({
      data: record.data,
      env: this.env,
      revisions: record.revisions,
    })
    await waitForDataLoaded(model)
    const xlsxData = model.exportXLSX()

    const formData = new URLSearchParams({
      files: JSON.stringify(xlsxData.files),
      zip_name: `${record.name}.xlsx`,
    })
    if (odoo.csrf_token) {
      formData.append("csrf_token", odoo.csrf_token)
    }

    const response = await fetch("/spreadsheet/xlsx", {
      body: formData,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      method: "POST",
    })
    if (!response.ok) {
      throw new Error("Failed to export spreadsheet to XLSX")
    }
    const xlsxBlob = await response.blob()

    const base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result.split(",")[1])
      reader.onerror = reject
      reader.readAsDataURL(xlsxBlob)
    })
    return {
      base64,
      name: record.name,
    }
  },

  async _openDocumentInOnlyoffice(documentId) {
    const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")
    const { same_tab } = JSON.parse(await this.orm.call("onlyoffice.odoo", "get_same_tab"))
    if (same_tab && !isDesktopEditor) {
      const action = {
        params: { document_id: documentId },
        tag: "onlyoffice_editor",
        target: "current",
        type: "ir.actions.client",
      }
      return this.action.doAction(action)
    }
    window.open(`/onlyoffice/editor/document/${documentId}`, "_blank")
  },
  async _refreshDocumentsFolder() {
    await this.env.model.load()
    this.env.model.notify()
  },
  async convertSpreadsheetViaDocBuilder(id) {
    this.ui.block({ message: _t("Converting spreadsheet to XLSX via DocBuilder...") })
    try {
      // Native export keeps charts/formatting; the server then patches the
      // ODOO.* cells into it. There is no fallback: if the native export
      // fails, the conversion fails.
      const nativeExport = await this._exportSpreadsheetNativeXlsx(id)
      const payload = {
        document_id: id,
        xlsx_base64: nativeExport.base64,
      }
      const result = await rpc("/onlyoffice/documents/convert_spreadsheet_via_docbuilder", payload)

      if (result.error) {
        this.notification.add(_t("Conversion failed: ") + result.error, { type: "danger" })
        return
      }

      if (result.xlsx_id) {
        this.notification.add(_t("Spreadsheet successfully converted to XLSX with formulas!"), { type: "success" })
        await this._refreshDocumentsFolder()
        await this._openDocumentInOnlyoffice(result.xlsx_id)
      }
    } catch (error) {
      console.error("Failed to convert spreadsheet via DocBuilder:", error)
      this.notification.add(_t("Conversion failed: ") + error.message, { type: "danger" })
    } finally {
      this.ui.unblock()
    }
  },
  isOdooSpreadsheet(record) {
    return Boolean(record?.data) && record.data.handler === "spreadsheet"
  },
  onlyofficeCanEdit(extension) {
    const format = formats.find((f) => f.name === extension.toLowerCase())
    return format && format.actions && format.actions.includes("edit")
  },
  onlyofficeCanView(extension) {
    const format = formats.find((f) => f.name === extension.toLowerCase())
    return format && format.actions && (format.actions.includes("view") || format.actions.includes("edit"))
  },
  async onlyofficeEditorUrl(id, isSpreadsheet = false) {
    let openDocumentId = id
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

    // If it's an Odoo spreadsheet, convert to xlsx first
    if (isSpreadsheet) {
      this.ui.block({ message: _t("Converting spreadsheet to XLSX...") })
      try {
        // Load spreadsheet bundle
        await loadBundle("spreadsheet.o_spreadsheet")

        // Get spreadsheet helpers
        const { createSpreadsheetModel, waitForDataLoaded } = odoo.loader.modules.get("@spreadsheet/helpers/model")

        // Join spreadsheet session to get data with revisions
        const record = await this.orm.call("documents.document", "join_spreadsheet_session", [id])

        // Create spreadsheet model with revisions
        const model = await createSpreadsheetModel({
          data: record.data,
          env: this.env,
          revisions: record.revisions,
        })
        await waitForDataLoaded(model)
        const xlsxData = model.exportXLSX()

        // Convert XLSX data using server endpoint
        const formData = new URLSearchParams({
          files: JSON.stringify(xlsxData.files),
          zip_name: `${record.name}.xlsx`,
        })

        // Add CSRF token
        if (odoo.csrf_token) {
          formData.append("csrf_token", odoo.csrf_token)
        }

        const response = await fetch("/spreadsheet/xlsx", {
          body: formData,
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          method: "POST",
        })

        if (!response.ok) {
          throw new Error("Failed to export spreadsheet to XLSX")
        }

        const xlsxBlob = await response.blob()

        // Convert blob to base64
        const xlsxBase64 = await new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onloadend = () => {
            const base64 = reader.result.split(",")[1]
            resolve(base64)
          }
          reader.onerror = reject
          reader.readAsDataURL(xlsxBlob)
        })

        // Get folder info
        const docInfo = await this.orm.read("documents.document", [id], ["folder_id"])

        // Create new XLSX document
        const uniqueSuffix = getFilenameTimestamp()
        const xlsxId = await this.orm.create("documents.document", [
          {
            datas: xlsxBase64,
            folder_id: docInfo[0].folder_id[0],
            mimetype: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            name: `${record.name}_${uniqueSuffix}.xlsx`,
            onlyoffice_spreadsheet_source_id: id,
          },
        ])

        // Use the XLSX document
        openDocumentId = xlsxId
        this.notification.add(_t("Spreadsheet converted to XLSX for editing in ONLYOFFICE"), { type: "success" })

        await this._refreshDocumentsFolder()
      } catch (error) {
        console.error("Failed to convert spreadsheet:", error)
        this.notification.add(_t("Failed to convert spreadsheet: ") + error.message, { type: "danger" })
        return
      } finally {
        this.ui.unblock()
      }
    }

    await this._openDocumentInOnlyoffice(openDocumentId)
  },
  showOnlyofficeButton(record) {
    if (!record?.data) {
      return false
    }
    if (this.isOdooSpreadsheet(record)) {
      return true
    }
    const ext = record.data.display_name.split(".").pop()
    return this.onlyofficeCanEdit(ext) || this.onlyofficeCanView(ext)
  },
})
