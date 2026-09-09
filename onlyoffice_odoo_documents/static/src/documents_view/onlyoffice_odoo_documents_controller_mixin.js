/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { onWillStart } from "@odoo/owl"
import { loadBundle } from "@web/core/assets"
import { _t } from "@web/core/l10n/translation"
import { rpc } from "@web/core/network/rpc"
import { useService } from "@web/core/utils/hooks"
import { ConvertDialog } from "./convert_dialog/convert_dialog"
import { CreateModeDialog } from "./create_mode_dialog/create_mode_dialog"

export const OnlyofficeDocumentsControllerMixin = () => ({
  setup() {
    super.setup(...arguments)
    this.action = useService("action")
    this.dialogService = useService("dialog")
    this.notification = useService("notification")
    this.ui = useService("ui")
    this.http = useService("http")
    onWillStart(async () => (this.formats = await this.loadFormats()))
  },

  // eslint-disable-next-line sort-keys
  getTopBarActionMenuItems() {
    const menuItems = super.getTopBarActionMenuItems()
    const selectionCount = this.model.targetRecords.length
    const singleSelection = selectionCount === 1 && this.targetRecords[0]
    return {
      ...menuItems,
      onlyofficeConvertSpreadsheet: {
        callback: () => this.convertSpreadsheetViaDocBuilder(singleSelection),
        description: _t("Convert to ONLYOFFICE XLSX (with formulas)"),
        groupNumber: 1,
        isAvailable: () => this.documentService.userIsInternal && this.isOdooSpreadsheet(singleSelection),
        sequence: 53,
      },
      onlyofficeEdit: {
        callback: () => this.onlyofficeEditorUrl(singleSelection, this.isOdooSpreadsheet(singleSelection)),
        description: _t("Open in ONLYOFFICE"),
        groupNumber: 1,
        isAvailable: () => this.documentService.userIsInternal && this.showOnlyofficeButton(singleSelection),
        sequence: 52,
      },
    }
  },

  /**
   * Export the spreadsheet with the native o-spreadsheet engine, so charts
   * and other advanced formatting are kept. Throws if the export fails.
   * @param {Number} id documents.document id of the Odoo Spreadsheet.
   * @returns {Promise<{base64: string, name: string}>}
   */
  async _exportSpreadsheetNativeXlsx(id) {
    await loadBundle("spreadsheet.o_spreadsheet")
    const { createSpreadsheetModel, waitForDataLoaded } = odoo.loader.modules.get("@spreadsheet/helpers/model")
    // Documents.document has no join_spreadsheet_session RPC anymore; the data/revisions
    // are fetched the same way the native spreadsheet action does it.
    const { data, name, revisions } = await this.http.get(`/spreadsheet/data/documents.document/${id}`)
    const model = await createSpreadsheetModel({
      data,
      env: this.env,
      revisions,
    })
    await waitForDataLoaded(model)
    const xlsxData = model.exportXLSX()

    const formData = new URLSearchParams({
      files: JSON.stringify(xlsxData.files),
      zip_name: `${name}.xlsx`,
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
      name,
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
      return this.actionService.doAction(action)
    }
    window.open(`/onlyoffice/editor/document/${documentId}`, "_blank")
  },

  async _refreshDocumentsFolder() {
    await this.model.load()
    this.model.notify()
  },

  /**
   * "Способ 2" (see SPREADSHEET_TESTING_GUIDE.md): convert the Odoo
   * Spreadsheet to an XLSX file where ODOO.* formulas stay alive as
   * ODOO_* formulas, resolved server-side on demand.
   * @param {Object} doc the selected documents.document record
   */
  async convertSpreadsheetViaDocBuilder(doc) {
    this.ui.block({ message: _t("Converting spreadsheet to XLSX via DocBuilder...") })
    try {
      // Native export keeps charts/formatting; the server then patches the
      // ODOO.* cells into it. There is no fallback: if the native export
      // fails, the conversion fails.
      const nativeExport = await this._exportSpreadsheetNativeXlsx(doc.data.id)
      const payload = {
        document_id: doc.data.id,
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

  async loadFormats() {
    try {
      const response = await fetch("/onlyoffice_odoo/static/assets/document_formats/onlyoffice-docs-formats.json")
      return await response.json()
    } catch (error) {
      console.error("Error loading formats data:", error)
    }
  },

  async onClickConvert() {
    const selection = this.env.model.root.selection.filter((rec) => rec._values.type !== "empty")
    if (selection.length !== 1) {
      this.notification.add(_t("Please select exactly one document to convert"), { type: "warning" })
      return
    }
    const record = selection[0]
    this.dialogService.add(ConvertDialog, {
      documentId: record.resId,
      filename: record.data.display_name || record.data.name,
      model: this.env.model,
    })
  },

  async onClickCreateOnlyoffice() {
    this.dialogService.add(CreateModeDialog, {
      context: this.props.context,
      folderId: this.env.searchModel.getSelectedFolderId(),
      model: this.env.model,
      onShare: (document_id) => this.onClickAdvancedShare(document_id, true),
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

  async onlyofficeEditorUrl(doc, isSpreadsheet = false) {
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

    let openDocumentId = doc.data.id
    if (isSpreadsheet) {
      this.ui.block({ message: _t("Converting spreadsheet to XLSX...") })
      try {
        const { base64, name } = await this._exportSpreadsheetNativeXlsx(doc.data.id)
        const existingXlsx = await this.orm.searchRead(
          "documents.document",
          [["onlyoffice_spreadsheet_source_id", "=", doc.data.id]],
          ["id"],
          { limit: 1 },
        )
        if (existingXlsx.length > 0) {
          await this.orm.write("documents.document", [existingXlsx[0].id], { datas: base64 })
          openDocumentId = existingXlsx[0].id
        } else {
          openDocumentId = await this.orm.create("documents.document", [
            {
              datas: base64,
              folder_id: doc.data.folder_id.id,
              mimetype: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              name: `${name}.xlsx`,
              onlyoffice_spreadsheet_source_id: doc.data.id,
            },
          ])
        }
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
