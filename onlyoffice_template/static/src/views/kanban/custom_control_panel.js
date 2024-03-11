/** @odoo-module **/
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { ActionMenus } from "@web/search/action_menus/action_menus";
import { useService } from "@web/core/utils/hooks";

export class CustomControlPanel extends ControlPanel {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.notificationService = useService("notification");
    }

    async onTestClick() {
        console.log(this);
    }
}

CustomControlPanel.template = "onlyoffice_template.CustomControlPanel";

CustomControlPanel.components = {
    ...ControlPanel.components,
    ActionMenus
};