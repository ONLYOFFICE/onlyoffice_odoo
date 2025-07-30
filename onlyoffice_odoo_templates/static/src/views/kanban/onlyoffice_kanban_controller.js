/** @odoo-module */
import { useService } from "@web/core/utils/hooks"
import { KanbanController } from "@web/views/kanban/kanban_controller"
import { HelpDialog } from "./onlyoffice_dialog_help"
import { FormGalleryDialog } from "./onlyoffice_form_gallery_dialog"

export class OnlyofficeKanbanController extends KanbanController {
  setup() {
    super.setup()
    this.orm = useService("orm")
    this.notificationService = useService("notification")
    this.dialog = useService("dialog")
    this.openedFormGallery = false
  }

  async openFormGallery() {
    if (!this.openedFormGallery) {
      this.openedFormGallery = true
      this.dialog.add(FormGalleryDialog, {}, { onClose: () => (this.openedFormGallery = false) })
    }
  }

  async help() {
    this.dialog.add(HelpDialog, {})
  }
}
