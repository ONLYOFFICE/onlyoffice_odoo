/** @odoo-module */
// Copyright (C) 2026 Ascensio System SIA

import { FormGallery } from "@onlyoffice_odoo/views/form_gallery/form_gallery"
import { useService } from "@web/core/utils/hooks"
import { KanbanController } from "@web/views/kanban/kanban_controller"
import { HelpDialog } from "./onlyoffice_dialog_help"

export class OnlyofficeKanbanController extends KanbanController {
  static template = "onlyoffice_odoo_templates.KanbanView.Buttons"

  setup() {
    super.setup()
    this.action = useService("action")
    this.orm = useService("orm")
    this.notificationService = useService("notification")
    this.dialog = useService("dialog")
    this.openedFormGallery = false
  }

  async openFormGallery() {
    const download = (form) => {
      if (form) {
        this.action.doAction({
          context: {
            default_hide_file_field: true,
            default_name: form.attributes.name_form,
            url: form.attributes.file_oform.data[0].attributes.url,
          },
          res_model: "onlyoffice.odoo.templates",
          target: "current",
          type: "ir.actions.act_window",
          view_mode: "form",
          views: [[false, "form"]],
        })
      }
    }
    this.dialog.add(FormGallery, {
      onDownload: download,
      showType: false,
    })
  }

  async help() {
    this.dialog.add(HelpDialog, {})
  }
}
