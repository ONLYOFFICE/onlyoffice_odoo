/** @odoo-module **/
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";

export class CustomKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    getCreateDate() {
        if (this.props.record.data?.create_date?.ts)
            return new Date(this.props.record.data.create_date.ts).toLocaleDateString();
        return ""
    }

    async _editTemplate() {
        this.env.bus.trigger("template-click", this.props.record.data);
    }

    async _deleteTemplate() {
        this.dialog.add(ConfirmationDialog, {
            body: this.env._t("Are you sure you want to delete this template?"),
            confirm: async () => {
                try {
                    this.orm.call(
                        "onlyoffice.template",
                        "action_delete_attachment",
                        [this.props.record.data.id]
                    ).then(() => {
                        this.props.record.model.load();
                        this.props.record.model.notify();
                    });
                } catch (error) {
                    console.error("error deleting: ", error);
                }
            },
            cancel: () => {},
        });
    }
}

CustomKanbanRecord.template = "onlyoffice_template.CustomKanbanRecord";