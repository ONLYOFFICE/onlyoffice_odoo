/** @odoo-module **/

import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { CustomKanbanRecord } from "./custom_kanban_record";

export class CustomKanbanRenderer extends KanbanRenderer {
    setup() {
        super.setup();
    }
}

CustomKanbanRenderer.components = {
    ...KanbanRenderer.components, 
    KanbanRecord: CustomKanbanRecord
};
