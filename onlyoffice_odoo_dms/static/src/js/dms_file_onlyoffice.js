/** @odoo-module **/
/**
 * Copyright (C) 2026 Data Dance s.r.o.
 * License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).
 */

import { FileKanbanView } from "@dms/js/views/file_kanban_view.esm"
import { FileListView } from "@dms/js/views/file_list_view.esm"
import { Component, useState, useEffect } from "@odoo/owl"
import { Dialog } from "@web/core/dialog/dialog"
import { _t } from "@web/core/l10n/translation"
import { registry } from "@web/core/registry"
import { useService } from "@web/core/utils/hooks"
import { patch } from "@web/core/utils/patch"
import { KanbanController } from "@web/views/kanban/kanban_controller"
import { ListController } from "@web/views/list/list_controller"

const FORMATS = [
  {
    ext: "docx",
    icon: "docx.svg",
    label: "Document",
  },
  {
    ext: "xlsx",
    icon: "xlsx.svg",
    label: "Spreadsheet",
  },
  {
    ext: "pptx",
    icon: "pptx.svg",
    label: "Presentation",
  },
  {
    ext: "pdf",
    icon: "pdf.svg",
    label: "PDF Form",
  },
]

/**
 * Dialog that lets a user create a blank ONLYOFFICE document inside a DMS directory.
 */
export class DmsCreateOnlyofficeDialog extends Component {
  static template = "onlyoffice_odoo_dms.DmsCreateOnlyofficeDialog"

  static components = { Dialog }

  static props = {
    close: Function,
    directoryId: Number,
    onCreated: {
      optional: true,
      type: Function,
    },
  }

  setup() {
    this.rpc = useService("rpc")
    this.notification = useService("notification")
    this.state = useState({
      format: "docx",
      loading: false,
      title: "New Document",
    })
  }

  get formats() {
    return FORMATS
  }

  async onCreate() {
    if (!this.state.title.trim()) {
      this.notification.add(_t("Please enter a Document name."), { type: "warning" })
      return
    }
    this.state.loading = true
    try {
      const raw = await this.rpc("/onlyoffice/dms/file/create", {
        directory_id: this.props.directoryId,
        supported_format: this.state.format,
        title: this.state.title.trim(),
      })
      const result = JSON.parse(raw)
      if (result.error) {
        this.notification.add(result.error, { type: "danger" })
      } else {
        if (this.props.onCreated) {
          this.props.onCreated(result.file_id)
        }
        this.props.close()
      }
    } catch {
      this.notification.add(_t("An unexpected error occurred while creating the document."), { type: "danger" })
    } finally {
      this.state.loading = false
    }
  }
}

registry.category("dialogs").add("onlyoffice_dms_create_dialog", DmsCreateOnlyofficeDialog)

// ── Patch list + kanban controllers to expose openCreateOnlyofficeDialog ──────

function createOnlyofficeCreateExtension() {
  return {
    _ooGetDirectoryId() {
      if (!this.props.domain) {
        return false
      }
      for (const item of this.props.domain) {
        if (
          Array.isArray(item) &&
          item.length === 3 &&
          item[0] === "directory_id" &&
          ["=", "child_of"].includes(item[1])
        ) {
          return item[2]
        }
      }
      return false
    },

    openCreateOnlyofficeDialog() {
      const directoryId = this._ooGetDirectoryId()
      if (directoryId === false) {
        return
      }

      const controllerID = this.actionService.currentController.jsId
      this.dialogService.add(DmsCreateOnlyofficeDialog, {
        directoryId,
        onCreated: (fileId) => {
          this.actionService.restore(controllerID)
          this.actionService.doAction({
            context: {
              file_id: fileId,
              mode: "edit",
            },
            name: "Edit in ONLYOFFICE",
            tag: "onlyoffice_dms.editor",
            type: "ir.actions.client",
          })
        },
      })
    },

    setup() {
      super.setup()
      this.dialogService = useService("dialog")
      if (!this.notification) {
        this.notification = useService("notification")
      }
      const orm = useService("orm")
      this.ooState = useState({ canCreate: false })

      useEffect(
        () => {
          const directoryId = this._ooGetDirectoryId()
          if (directoryId === false) {
            this.ooState.canCreate = false
            return
          }
          orm.read("dms.directory", [directoryId], ["permission_create"]).then((result) => {
            this.ooState.canCreate = result[0]?.permission_create || false
          })
        },
        () => [this.props.domain],
      )
    },
  }
}

patch(ListController.prototype, createOnlyofficeCreateExtension())
patch(KanbanController.prototype, createOnlyofficeCreateExtension())

// Point the DMS views at our extended button templates
FileListView.buttonTemplate = "onlyoffice_odoo_dms.ListButtonsExtension"
FileKanbanView.buttonTemplate = "onlyoffice_odoo_dms.KanbanButtonsExtension"
