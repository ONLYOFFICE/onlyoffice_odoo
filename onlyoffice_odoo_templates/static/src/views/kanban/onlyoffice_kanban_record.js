/** @odoo-module **/
import { useService } from "@web/core/utils/hooks"
import { KanbanRecord } from "@web/views/kanban/kanban_record"

export class OnlyofficeKanbanRecord extends KanbanRecord {
  setup() {
    super.setup(...arguments)
    this.orm = useService("orm")
    this.actionService = useService("action")
  }

  /**
   * @override
   */
  async onGlobalClick() {
    return this.editTemplate()
  }

  async editTemplate() {
    const action = {
      tag: "onlyoffice_odoo_templates.TemplateEditor",
      target: "current",
      type: "ir.actions.client",
    }
    return this.actionService.doAction(action, { props: this.props.record.data })
  }
}
