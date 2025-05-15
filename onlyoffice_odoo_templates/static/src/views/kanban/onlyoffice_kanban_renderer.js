/** @odoo-module **/

import { KanbanRenderer } from "@web/views/kanban/kanban_renderer"
import { OnlyofficeKanbanRecord } from "./onlyoffice_kanban_record"

export class OnlyofficeKanbanRenderer extends KanbanRenderer {
  setup() {
    super.setup(...arguments)
  }

  /**
   * @override
   **/
  canQuickCreate() {
    return false
  }

  /**
   * @override
   **/
  canCreateGroup() {
    return false
  }
}

OnlyofficeKanbanRenderer.components = {
  ...KanbanRenderer.components,
  KanbanRecord: OnlyofficeKanbanRecord,
}
