/** @odoo-module **/
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useService } from "@web/core/utils/hooks";
import { _t } from "web.core";

const { useState } = owl;

export class CustomKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.notificationService = useService("notification");
        this.action = useService("action");
        console.log("CustomKanbanController", this.props);

        this.state = useState({
            fields: {},
            showEditor: false
        });

        this.env.bus.on('template-click', this, (data) => this.templateClick(data));
    }

    async templateClick(data) {
        console.log(data);
        await this._openTemplate(data.attachment_id[0]);
    }

    async onFieldElementClick() {
        const iframe = document.querySelector("iframe");
        iframe.contentWindow.postMessage("123", "http://192.168.0.100:8069");
    }

    async onButtonCreateTemplateClick() { 
        const result = await this.rpc(`/onlyoffice/template/file/create`);
        if (result.error) {
            this.notificationService.add(result.error, {type: "error", sticky: false}); 
        } else {
            this.notificationService.add(_t("New template created in Documents"), {type: "info", sticky: false});
            await this._openTemplate(result.file_id);
        }
        this.model.load();
        this.model.notify();
    }

    async _generateFieldsList() {
        try {
            const models = JSON.parse(await this.orm.call("onlyoffice.template", "get_fields", []));
            const array = [];
            let i = 0;
            Object.keys(models).forEach(model => {
                const fields = models[model];
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
            console.log("fields", array);
            this.state.fields = array;
        } catch (error) {
            console.error("RPC Error:", error);
        }
    }

    _embedIframe(id) {
        const iframeContainer = document.querySelector(".iframe");
        iframeContainer.innerHTML = `<iframe src="/onlyoffice/editor/${id}" frameborder="0" style="width:100%; height:100%;"></iframe>`;
    }

    async _openTemplate(id) {
        await this._generateFieldsList();
        this._embedIframe(id);
        this.state.showEditor = true;
    }
}

CustomKanbanController.template = "onlyoffice_template.CustomKanbanController";