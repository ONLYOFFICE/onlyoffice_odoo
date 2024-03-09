/** @odoo-module **/
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useService } from "@web/core/utils/hooks";
import { _t } from "web.core";

const { useState, onWillStart } = owl;

export class CustomKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.notificationService = useService("notification");
        this.action = useService("action");
        console.log("CustomKanbanController", this.props);

        this.state = useState({
            json: {}
        });
        onWillStart(async () => await this.test());
    }

    async test() {
        try {
            const parameters = JSON.parse(await this.orm.call("onlyoffice.template", "get_parameter", []));
            const array = [];
            let i = 0;
            Object.keys(parameters).forEach(model => {
                const fields = parameters[model];
                Object.keys(fields).forEach(fieldName => {
                    const field = fields[fieldName];
                    array.push({
                        model: model,
                        name: field.name,
                        string: field.string,
                        type: field.type,
                        key: i
                    });
                    i++;
                });
            });
            console.log("array", array)
            this.state.json = array;
        } catch (error) {
            console.error("Ошибка при выполнении RPC:", error);
        }
    }

    async clickOnLi (el) {
        const iframe = document.querySelector("iframe");
        iframe.contentWindow.postMessage("123", "http://192.168.0.100:8069");
    }

    async _onButtonNewTemplate() { 
        const result = await this.rpc(`/onlyoffice/template/file/create`);
        if (result.error) {
            this.notificationService.add(result.error, {type: "error", sticky: false}); 
        } else {
            this.notificationService.add(_t("New template created in Documents"), {type: "info", sticky: false});
            window.open(`/onlyoffice/editor/${result.file_id}`, '_blank');
            //this._embedIframe(result);
        }
        this.model.load()
        this.model.notify()
    }

    _embedIframe(result) {
        const iframeContainer = document.querySelector(".o_content");
        iframeContainer.innerHTML = `<iframe src="/onlyoffice/editor/${result.file_id}" frameborder="0" style="width:100%; height:600px;"></iframe>`;
    }
}

CustomKanbanController.template = "onlyoffice_template.CustomKanbanController";