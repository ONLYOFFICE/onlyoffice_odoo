/** @odoo-module **/
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { useService } from "@web/core/utils/hooks";

export class CustomKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        console.log("CustomKanbanRecord", this.props.record)
    }

    getCreateDate() {
        if (this.props.record.data?.create_date?.ts)
            return new Date(this.props.record.data.create_date.ts).toLocaleDateString()
        return ""
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
            return array
        } catch (error) {
            console.error("Ошибка при выполнении RPC:", error);
        }
    }

    async onGlobalClick(ev) {
        const iframeContainer = document.querySelector(".iframe");
        iframeContainer.innerHTML = `<iframe src="/onlyoffice/editor/${this.props.record.data.attachment_id[0]}" frameborder="0" style="width:100%; height:600px;"></iframe>`;

        /*let a = await this.test();
        const iframe = document.querySelector("iframe");
        console.log("iframe", iframe)
        iframe.onload = function() {
            console.log("отправил")
            iframe.contentWindow.postMessage(JSON.stringify(a), "*");
        };*/

        /*this.action.doActionButton({
            name: "action_download",
            type: "object",
            resModel: this.props.record.resModel,
            resId: this.props.record.resId,
            context: this.props.record.context,
        });*/
    } 
}

CustomKanbanRecord.template = "onlyoffice_template.CustomKanbanRecord";

// Загрузка дополнительных данных для каждой записи
/*if (this.props.record.resId) {
    const additionalData = await this.orm.call(
        this.props.record.resModel,
        'read',
        [this.props.record.resId],
        ['mimetype'], // Список полей для загрузки
    );*/