/** @odoo-module */
import { registry } from "@web/core/registry"
import { kanbanView } from "@web/views/kanban/kanban_view"
import { OnlyofficeKanbanRenderer } from "./onlyoffice_kanban_renderer"

export const onlyofficeKanbanView = {
  ...kanbanView,
  Renderer: OnlyofficeKanbanRenderer,
}

registry.category("views").add("onlyoffice_kanban", onlyofficeKanbanView)
