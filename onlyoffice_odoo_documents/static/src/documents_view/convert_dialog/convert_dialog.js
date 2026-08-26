/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { Dialog } from "@web/core/dialog/dialog"
import { _t } from "@web/core/l10n/translation"
import { rpc } from "@web/core/network/rpc"
import { useService } from "@web/core/utils/hooks"

const { Component, useState, onWillStart } = owl

export class ConvertDialog extends Component {
  static components = { Dialog }

  static template = "onlyoffice_odoo_documents.ConvertDialog"

  setup() {
    this.rpc = rpc
    this.notification = useService("notification")
    this.ui = useService("ui")

    this.dialogTitle = _t("Convert with ONLYOFFICE")
    this.sourceExt = (this.props.filename.split(".").pop() || "").toLowerCase()

    this.state = useState({
      converting: false,
      formats: [],
      saveToDocuments: true,
      targetFormat: null,
    })

    onWillStart(async () => {
      try {
        const response = await fetch("/onlyoffice_odoo/static/assets/document_formats/onlyoffice-docs-formats.json")
        const allFormats = await response.json()
        const currentFormat = allFormats.find((f) => f.name === this.sourceExt)
        const targets = (currentFormat && currentFormat.convert) || []
        this.state.formats = [...targets].sort()
        this.state.targetFormat = this.state.formats[0] || null
      } catch (error) {
        console.error("Error loading formats data:", error)
      }
    })
  }

  onFormatChange(ev) {
    this.state.targetFormat = ev.target.value
  }

  onSaveToDocumentsChange(ev) {
    this.state.saveToDocuments = ev.target.checked
  }

  get confirmDisabled() {
    return this.state.converting || !this.state.targetFormat
  }

  async onConvert() {
    if (this.confirmDisabled) {
      return
    }
    this.state.converting = true
    this.ui.block()
    try {
      const json = await this.rpc("/onlyoffice/documents/file/convert", {
        document_id: this.props.documentId,
        save_to_documents: this.state.saveToDocuments,
        target_format: this.state.targetFormat,
      })
      const result = JSON.parse(json)
      if (result.error) {
        this.notification.add(result.error, { type: "danger" })
        return
      }
      if (result.saved) {
        if (this.props.model) {
          this.props.model.load()
          this.props.model.notify()
        }
        this.notification.add(_t("Document converted and saved to Documents"), { type: "success" })
      } else {
        this.downloadFile(result.data, result.filename)
        this.notification.add(_t("Document converted successfully"), { type: "success" })
      }
      this.props.close()
    } catch (error) {
      console.error("Error converting document:", error)
      this.notification.add(_t("Error converting document"), { type: "danger" })
    } finally {
      this.state.converting = false
      this.ui.unblock()
    }
  }

  downloadFile(base64Data, filename) {
    const byteChars = atob(base64Data)
    const byteNumbers = new Array(byteChars.length)
    for (let i = 0; i < byteChars.length; i += 1) {
      byteNumbers[i] = byteChars.charCodeAt(i)
    }
    const blob = new Blob([new Uint8Array(byteNumbers)])
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }
}
