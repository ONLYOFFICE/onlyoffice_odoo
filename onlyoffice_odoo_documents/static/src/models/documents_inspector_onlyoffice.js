/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { DocumentsInspector } from "@documents/views/inspector/documents_inspector"
import { useService } from "@web/core/utils/hooks"
import { patch } from "@web/core/utils/patch"
import { _t } from "@web/core/l10n/translation"
import { loadBundle } from "@web/core/assets"

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
  async onlyofficeEditorUrl(id, isSpreadsheet = false) {
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
      try {
        // Load spreadsheet bundle
        await loadBundle("spreadsheet.o_spreadsheet")

        // Get spreadsheet helpers
        const { createSpreadsheetModel, waitForDataLoaded } = odoo.loader.modules.get("@spreadsheet/helpers/model")

        // Join spreadsheet session to get data with revisions
        const record = await this.env.services.orm.call("documents.document", "join_spreadsheet_session", [id])

        // Create spreadsheet model with revisions
        const model = await createSpreadsheetModel({
          env: this.env,
          data: record.data,
          revisions: record.revisions,
        })
        await waitForDataLoaded(model)
        const xlsxData = model.exportXLSX()

        // Convert XLSX data using server endpoint
        const formData = new URLSearchParams({
          zip_name: `${record.name}.xlsx`,
          files: JSON.stringify(xlsxData.files),
        })

        // Add CSRF token
        if (odoo.csrf_token) {
          formData.append("csrf_token", odoo.csrf_token)
        }

        const response = await fetch("/spreadsheet/xlsx", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: formData,
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

        // Check if XLSX copy already exists
        const existingXlsx = await this.env.services.orm.searchRead(
          "documents.document",
          [["onlyoffice_spreadsheet_source_id", "=", id]],
          ["id"],
          { limit: 1 },
        )

        let xlsxId
        if (existingXlsx.length > 0) {
          // Update existing XLSX copy
          await this.env.services.orm.write("documents.document", [existingXlsx[0].id], { datas: xlsxBase64 })
          xlsxId = existingXlsx[0].id
        } else {
          // Get folder info
          const docInfo = await this.env.services.orm.read("documents.document", [id], ["folder_id"])

          // Create new XLSX document
          xlsxId = await this.env.services.orm.create("documents.document", [
            {
              name: `${record.name}.xlsx`,
              folder_id: docInfo[0].folder_id[0],
              datas: xlsxBase64,
              mimetype: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              onlyoffice_spreadsheet_source_id: id,
            },
          ])
        }

        // Use the XLSX document
        id = xlsxId
        this.notification.add(_t("Spreadsheet converted to XLSX for editing in ONLYOFFICE"), {
          type: "success",
        })

        // Refresh the documents folder so the new file appears
        const docModel = this.props.documents[0].model
        await docModel.load()
        docModel.notify()
      } catch (error) {
        console.error("Failed to convert spreadsheet:", error)
        this.notification.add(_t("Failed to convert spreadsheet: ") + error.message, {
          type: "danger",
        })
        return
      }
    }

    const { same_tab } = JSON.parse(await this.env.services.orm.call("onlyoffice.odoo", "get_same_tab"))
    if (same_tab) {
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
    // Check if it's an Odoo spreadsheet
    if (records[0].data.handler === "spreadsheet") {
      return true
    }
    const ext = records[0].data.display_name.split(".").pop()
    return records.length === 1 && (this.onlyofficeCanEdit(ext) || this.onlyofficeCanView(ext))
  },
  isOdooSpreadsheet(records) {
    return records.length === 1 && records[0].data.handler === "spreadsheet"
  },
  async convertSpreadsheetViaDocBuilder(id) {
    try {
      // Show loading notification
      this.notification.add(_t("Converting spreadsheet to XLSX via DocBuilder. This may take a few moments..."), {
        type: "info",
      })

      // Call server method to convert via DocBuilder
      const result = await this.env.services.rpc("/onlyoffice/documents/convert_spreadsheet_via_docbuilder", {
        document_id: id,
      })

      if (result.error) {
        this.notification.add(_t("Conversion failed: ") + result.error, {
          type: "danger",
        })
        return
      }

      if (result.xlsx_id) {
        this.notification.add(_t("Spreadsheet successfully converted to XLSX with formulas!"), {
          type: "success",
        })

        // Refresh the documents folder so the new file appears
        const docModel = this.props.documents[0].model
        await docModel.load()
        docModel.notify()

        // Open the converted XLSX in ONLYOFFICE
        const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")
        const { same_tab } = JSON.parse(await this.env.services.orm.call("onlyoffice.odoo", "get_same_tab"))

        if (same_tab && !isDesktopEditor) {
          const action = {
            params: { document_id: result.xlsx_id },
            tag: "onlyoffice_editor",
            target: "current",
            type: "ir.actions.client",
          }
          return this.actionService.doAction(action)
        }
        window.open(`/onlyoffice/editor/document/${result.xlsx_id}`, "_blank")
      }
    } catch (error) {
      console.error("Failed to convert spreadsheet via DocBuilder:", error)
      this.notification.add(_t("Conversion failed: ") + error.message, {
        type: "danger",
      })
    }
  },
})
