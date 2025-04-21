/** @odoo-module **/
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"
import { useService } from "@web/core/utils/hooks"
import { CANCEL_GLOBAL_CLICK, KanbanRecord } from "@web/views/kanban/kanban_record"

export class OnlyofficeKanbanRecord extends KanbanRecord {
  setup() {
    super.setup()
    this.orm = useService("orm")
    this.actionService = useService("action")
  }

  /**
   * @override
   */
  triggerAction(params) {
    const env = this.env
    const { group, list, openRecord, record } = this.props
    const { type } = params
    switch (type) {
      case "edit": {
        return openRecord(record, "edit")
      }
      case "delete": {
        const listOrGroup = group || list
        if (listOrGroup.deleteRecords) {
          this.dialog.add(ConfirmationDialog, {
            body: env._t("Are you sure you want to delete this record?"),
            cancel: () => {
              return
            },
            confirm: async () => {
              await listOrGroup.deleteRecords([record])
              this.props.record.model.load()
              this.props.record.model.notify()
              return this.notification.add(env._t("Template removed"), {
                sticky: false,
                type: "info",
              })
            },
          })
        }
        return
      }
      default: {
        return this.notification.add(env._t("Kanban: no action for type: ") + type, { type: "danger" })
      }
    }
  }

  /**
   * @override
   */
  async onGlobalClick(ev) {
    if (ev.target.closest(CANCEL_GLOBAL_CLICK) && !ev.target.classList.contains("o_onlyoffice_download")) {
      return
    }
    if (ev.target.classList.contains("o_onlyoffice_download")) {
      window.location.href = `/onlyoffice/template/download/${this.props.record.data.attachment_id[0]}`
      return
    }
    return this.editTemplate()
  }

  async editTemplate() {
    const action = {
      params: {
        attachment_id: this.props.record.data.attachment_id[0],
        id: this.props.record.data.id,
        template_model_model: this.props.record.data.template_model_model,
      },
      tag: "onlyoffice_template_editor",
      target: "current",
      type: "ir.actions.client",
    }
    return this.actionService.doAction(action, { props: this.props.record.data })
  }
}
