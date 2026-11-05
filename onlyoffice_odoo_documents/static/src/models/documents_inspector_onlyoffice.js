/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { DocumentsInspector } from "@documents/views/inspector/documents_inspector"
import { loadBundle } from "@web/core/assets"
import { formatDateTime } from "@web/core/l10n/dates"
import { _t } from "@web/core/l10n/translation"
import { useService } from "@web/core/utils/hooks"
import { patch } from "@web/core/utils/patch"
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog"

const { DateTime } = luxon

// "/" is written as \x2F: babel's JS lexer ends the regex at "[\\/", and no string of this file gets into the .pot.
const getFilenameTimestamp = () => formatDateTime(DateTime.now()).replace(/[\\\x2F:*?"<>|\s]+/g, "_")

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
    this.ui = useService("ui")
    this.dialog = useService("dialog")
    this.onlyofficeEditorUrl = this.onlyofficeEditorUrl.bind(this)
  },

  /**
   * Export the spreadsheet with the native o-spreadsheet engine, so charts
   * and other advanced formatting are kept. Throws if the export fails.
   * @param {Number} id documents.document id of the Odoo Spreadsheet.
   * @returns {Promise<{base64: string, name: string, data: Object, sheetNames: string[]}>} the file, and the data
   * it was made from (revisions applied) with its sheet names as the export wrote them.
   */
  async _exportSpreadsheetNativeXlsx(id) {
    await loadBundle("spreadsheet.o_spreadsheet")
    const { createSpreadsheetModel, waitForDataLoaded } = odoo.loader.modules.get("@spreadsheet/helpers/model")
    const record = await this.env.services.orm.call("documents.document", "join_spreadsheet_session", [id])
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
    // Sheet names as written in the file: Excel cuts a name to 31 characters.
    const workbook = xlsxData.files.find((file) => file.path === "xl/workbook.xml")
    let sheetNames = []
    if (workbook) {
      const workbookXml = new DOMParser().parseFromString(workbook.content, "application/xml")
      sheetNames = Array.from(workbookXml.getElementsByTagName("sheet"), (sheet) => sheet.getAttribute("name"))
    }
    return {
      base64,
      data: model.exportData(),
      name: record.name,
      sheetNames,
    }
  },

  async _openDocumentInOnlyoffice(documentId) {
    const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")
    const { same_tab } = JSON.parse(await this.env.services.orm.call("onlyoffice.odoo", "get_same_tab"))
    if (same_tab && !isDesktopEditor) {
      const action = {
        params: { document_id: documentId },
        tag: "onlyoffice_editor",
        target: "current",
        type: "ir.actions.client",
      }
      return this.actionService.doAction(action)
    }
    window.open(`/onlyoffice/editor/document/${documentId}`, "_blank")
  },
  async _refreshDocumentsFolder() {
    const docModel = this.props.documents[0].model
    await docModel.load()
    docModel.notify()
  },
  canOnlyofficeFreeze(records) {
    return records.length === 1 && Boolean(records[0].data.onlyoffice_can_freeze)
  },
  async convertSpreadsheetViaDocBuilder(id) {
    this.ui.block({ message: _t("Converting spreadsheet to XLSX via ONLYOFFICE...") })
    try {
      // Native export keeps charts/formatting; the server then patches the
      // ODOO.* cells into it. There is no fallback: if the native export
      // fails, the conversion fails.
      const nativeExport = await this._exportSpreadsheetNativeXlsx(id)
      // The data with the revisions: what was inserted since the last snapshot is only there.
      const payload = {
        document_id: id,
        sheet_names: nativeExport.sheetNames,
        spreadsheet_data: nativeExport.data,
        xlsx_base64: nativeExport.base64,
      }
      const result = await this.env.services.rpc("/onlyoffice/documents/convert_spreadsheet_via_docbuilder", payload)

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
      console.error("Failed to convert spreadsheet via ONLYOFFICE:", error)
      this.notification.add(_t("Conversion failed: ") + error.message, { type: "danger" })
    } finally {
      this.ui.unblock()
    }
  },
  /**
   * "Freeze and share" of an XLSX with Odoo formulas, as Odoo freezes a spreadsheet: a read-only copy with the
   * values the user sees now, then the share dialog of Documents for that copy.
   * @param {Number} id documents.document id of the XLSX.
   */
  async freezeAndShareSpreadsheet(id) {
    const orm = this.env.services.orm
    this.ui.block({ message: _t("Freezing the spreadsheet...") })
    const frozen = await orm
      .call("documents.document", "action_onlyoffice_freeze_and_copy", [[id]])
      .finally(() => this.ui.unblock())
    await this._refreshDocumentsFolder()
    // As "Share" of Documents: a share of the frozen copy, its link copied once saved, dropped when cancelled.
    const action = await orm.call("documents.share", "open_share_popup", [
      {
        document_ids: [[6, 0, [frozen.id]]],
        folder_id: frozen.folder_id,
        type: "ids",
      },
    ])
    let saved = false
    this.dialog.add(
      FormViewDialog,
      {
        onRecordSaved: async (record) => {
          saved = true
          await navigator.clipboard.writeText(record.data.full_url)
          this.notification.add(_t("The share url has been copied to your clipboard."), { type: "success" })
        },
        resId: action.res_id,
        resModel: "documents.share",
      },
      {
        onClose: async () => {
          if (!saved) {
            await orm.unlink("documents.share", [action.res_id])
          }
        },
      },
    )
  },
  isOdooSpreadsheet(records) {
    return records.length === 1 && records[0].data.handler === "spreadsheet"
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
    const demo = JSON.parse(await this.env.services.orm.call("onlyoffice.odoo", "get_demo"))
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
        const record = await this.env.services.orm.call("documents.document", "join_spreadsheet_session", [id])

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
        const docInfo = await this.env.services.orm.read("documents.document", [id], ["folder_id"])

        // Create new XLSX document
        const uniqueSuffix = getFilenameTimestamp()
        const xlsxId = await this.env.services.orm.create("documents.document", [
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
  showOnlyofficeButton(records) {
    if (records.length !== 1) {
      return false
    }
    // Check if it's an Odoo spreadsheet
    if (records[0].data.handler === "spreadsheet") {
      return true
    }
    const ext = records[0].data.display_name.split(".").pop()
    return records.length === 1 && (this.onlyofficeCanEdit(ext) || this.onlyofficeCanView(ext))
  },
})
