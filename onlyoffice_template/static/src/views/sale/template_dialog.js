/** @odoo-module **/
import { Dialog } from "@web/core/dialog/dialog";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { Pager } from "@web/core/pager/pager";
import { DropPrevious } from "web.concurrency";
import { SearchModel } from "@web/search/search_model";
import { useBus, useService } from "@web/core/utils/hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { getDefaultConfig } from "@web/views/view";
import { _t } from "web.core";

const { Component, useState, useSubEnv, useChildSubEnv, onWillStart } = owl;

export class TemplateDialog extends Component{
    setup() {
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.viewService = useService("view");

        this.data = this.env.dialogData;
        useHotkey("escape", () => this.data.close());

        this.dialogTitle = this.env._t("Print from template");
        this.limit = 9;
        this.state = useState({
            isOpen: true,
            templates: [],
            templatesCount: 0,
            selectedTemplateId: null,
            offset: 1,
            offset: 0,
            isCreating: false,
        });

        useSubEnv({
            config: {
                ...getDefaultConfig(),
            },
        });

        this.model = new SearchModel(this.env, {
            user: useService("user"),
            orm: this.orm,
            view: useService("view"),
        });

        useChildSubEnv({
            searchModel: this.model,
        });

        useBus(this.model, "update", () => this._fetchTemplates());
        this.dp = new DropPrevious();

        onWillStart(async () => {
            const views = await this.viewService.loadViews({
                resModel: "onlyoffice.template",
                context: this.props.context,
                views: [[false, "search"]],
            });
            await this.model.load({
                resModel: "onlyoffice.template",
                context: this.props.context,
                orderBy: "id",
                searchMenuTypes: [],
                searchViewArch: views.views.search.arch,
                searchViewId: views.views.search.id,
                searchViewFields: views.fields,
            });
            await this._fetchTemplates();
        });
    }

    async _fetchTemplates(offset = 0) {
        const { domain, context } = this.model;
        const { records, length } = await this.dp.add(
            this.rpc("/web/dataset/search_read", {
                model: "onlyoffice.template",
                fields: ["name", "file", "create_date", "create_uid", "attachment_id", "mimetype"],
                domain,
                context,
                offset,
                limit: this.limit,
                sort: "id"
            })
        );
        this.state.templates = records;
        this.state.templatesCount = length;
    }


    _selectTemplate(templateId) {
        console.log(templateId)
        this.state.selectedTemplateId = templateId;
    }

    _isSelected(templateId) {
        console.log(templateId)
        return this.state.selectedTemplateId === templateId;
    }

    _hasSelection() {
        return (
            this.state.templates.find(
                (template) => template.id === this.state.selectedTemplateId
            ) || this.state.selectedTemplateId === null
        );
    }

    _onPagerChanged({ offset }) {
        this.state.offset = offset;
        return this._fetchTemplates(this.state.offset);
    }

    _buttonDisabled() {
        console.log("_buttonDisabled", this.state.isCreating, !this._hasSelection())
        return this.state.isCreating || !this._hasSelection();
    }
}

TemplateDialog.template = "onlyoffice_template.TemplateDialog";
TemplateDialog.components = { Dialog, SearchBar, Pager };
