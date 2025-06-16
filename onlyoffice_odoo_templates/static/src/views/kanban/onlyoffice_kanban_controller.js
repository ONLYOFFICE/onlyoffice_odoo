/** @odoo-module */
import { useService } from "@web/core/utils/hooks"
import { KanbanController } from "@web/views/kanban/kanban_controller"
import { HelpDialog } from "./onlyoffice_dialog_help"

export class OnlyofficeKanbanController extends KanbanController {
  setup() {
    super.setup()
    this.orm = useService("orm")
    this.notificationService = useService("notification")
    this.dialog = useService("dialog")
  }

  async _test() {
    this.dialog.add(HelpDialog, {})
  }
}
