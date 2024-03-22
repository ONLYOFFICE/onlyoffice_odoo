/** @odoo-module **/
import { ControlPanel } from "@web/search/control_panel/control_panel";

export class CustomControlPanel extends ControlPanel {
    setup() {
        super.setup();
    }

    async onTestClick() {
        console.log(this);
    }
}

CustomControlPanel.template = "onlyoffice_template.CustomControlPanel";