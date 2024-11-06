/** @odoo-module **/
import { Dialog } from "@web/core/dialog/dialog";
import { Pager } from "@web/core/pager/pager";
import { KeepLast } from "@web/core/utils/concurrency";
import { SearchModel } from "@web/search/search_model";
import { useService } from "@web/core/utils/hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { getDefaultConfig } from "@web/views/view";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { rpc } from "@web/core/network/rpc";

import { _t } from "@web/core/l10n/translation";

const { Component, useState, useSubEnv, useChildSubEnv, onWillStart } = owl;

export class TemplateDialog extends Component {
  setup() {
    this.orm = useService("orm");
    this.rpc = rpc;
    this.viewService = useService("view");
    this.notificationService = useService("notification");
    this.dialog = useService("dialog");

    this.data = this.env.dialogData;
    useHotkey("escape", () => this.data.close());

    this.dialogTitle = _t("Print from template");
    this.limit = 8;
    this.state = useState({
      isOpen: true,
      templates: [],
      totalTemplates: 0,
      selectedTemplateId: null,
      currentOffset: 0,
      isProcessing: false,
    });

    useSubEnv({
      config: {
        ...getDefaultConfig(),
      },
    });

    this.model = new SearchModel(this.env, {
      orm: this.orm,
      view: useService("view"),
    });

    useChildSubEnv({
      searchModel: this.model,
    });

    this.dp = new KeepLast();

    onWillStart(async () => {
      const { resModel } = this.props;
      const views = await this.viewService.loadViews({
        resModel: "onlyoffice.odoo.templates",
        context: this.props.context,
        views: [[false, "search"]],
      });
      await this.model.load({
        resModel: "onlyoffice.odoo.templates",
        domain: [["template_model_model", "=", resModel]],
        context: this.props.context,
        orderBy: "id",
        searchMenuTypes: [],
        searchViewArch: views.views.search.arch,
        searchViewId: views.views.search.id,
        searchViewFields: views.fields,
      });
      await this.fetchTemplates();
    });
  }

  async createTemplate() {
    //TODO: create template from dialog
  }

  async fetchTemplates(offset = 0) {
    const { domain, context } = this.model;
    const records = await this.orm.searchRead(
      "onlyoffice.odoo.templates",
      domain,
      ["name", "create_date", "create_uid", "attachment_id", "mimetype"],
      { context, order: 'id', limit: this.limit, offset }
    );
    this.state.templates = records;
    const length = await this.orm.searchCount("onlyoffice.odoo.templates", domain, { context });
    if (!length) {
      this.dialog.add(AlertDialog, {
        title: this.dialogTitle,
        body: _t("You don't have any templates yet. Please go to the ONLYOFFICE Templates app to create a new template or ask your admin to create it."),
      });
      return this.data.close();
    } else {
      this.state.totalTemplates = length;
    }
  }

  async fillTemplate() {
    this.state.isProcessing = true;

    const templateId = this.state.selectedTemplateId;
    const { resId, resModel } = this.props;

    const response = await this.rpc("/onlyoffice/template/get_filled_template", {
      template_id: templateId,
      record_id: resId,
      model_name: resModel,
    });

    if (!response) {
      this.notificationService.add(_t("Unknown error"), { type: "danger" });
    } else if (response.href) {
      window.location.href = response.href;
    } else if (response.error) {
      this.notificationService.add(_t(response.error), { type: "danger" });
    }
    this.data.close();
  }

  selectTemplate(templateId) {
    this.state.selectedTemplateId = templateId;
  }

  isSelected(templateId) {
    return this.state.selectedTemplateId === templateId;
  }

  onPagerChange({ offset }) {
    this.state.currentOffset = offset;
    this.state.selectedTemplateId = null;
    return this.fetchTemplates(this.state.currentOffset);
  }

  isButtonDisabled() {
    return this.state.isProcessing || this.state.selectedTemplateId === null;
  }
}

TemplateDialog.template = "onlyoffice_odoo_templates.TemplateDialog";
TemplateDialog.components = { Dialog, Pager };
