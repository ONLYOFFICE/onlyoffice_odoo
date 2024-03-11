/** @odoo-module **/
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { useService } from "@web/core/utils/hooks";

export class CustomKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    }

    getCreateDate() {
        if (this.props.record.data?.create_date?.ts)
            return new Date(this.props.record.data.create_date.ts).toLocaleDateString();
        return ""
    }

    async onGlobalClick() {
        this.env.bus.trigger("template-click", this.props.record.data);
    }
}

CustomKanbanRecord.template = "onlyoffice_template.CustomKanbanRecord";