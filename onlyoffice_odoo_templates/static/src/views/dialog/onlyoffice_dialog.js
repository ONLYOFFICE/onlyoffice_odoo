/** @odoo-module **/
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog"
import { Dialog } from "@web/core/dialog/dialog"
import { useHotkey } from "@web/core/hotkeys/hotkey_hook"
import { _t } from "@web/core/l10n/translation"
import { download } from "@web/core/network/download"
import { rpc } from "@web/core/network/rpc"
import { Pager } from "@web/core/pager/pager"
import { KeepLast } from "@web/core/utils/concurrency"
import { useService } from "@web/core/utils/hooks"
import { SearchModel } from "@web/search/search_model"
import { getDefaultConfig } from "@web/views/view"
import { OnlyofficePDFPreview } from "../widget/onlyoffice_pdf_preview"

const { Component, useState, useSubEnv, useChildSubEnv, onWillStart } = owl

export class TemplateDialog extends Component {
  setup() {
    this.orm = useService("orm")
    this.rpc = rpc
    this.viewService = useService("view")
    this.notificationService = useService("notification")
    this.dialog = useService("dialog")

    this.data = this.env.dialogData
    useHotkey("escape", () => this.data.close())

    this.dialogTitle = _t("Print from template")
    this.limit = 8
    this.state = useState({
      currentOffset: 0,
      isOpen: true,
      isProcessing: false,
      selectedTemplateId: null,
      templates: [],
      totalTemplates: 0,
    })

    useSubEnv({ config: { ...getDefaultConfig() } })

    this.model = new SearchModel(this.env, {
      orm: this.orm,
      view: useService("view"),
    })

    useChildSubEnv({ searchModel: this.model })

    this.dp = new KeepLast()

    onWillStart(async () => {
      const { resModel } = this.props
      const views = await this.viewService.loadViews({
        context: this.props.context,
        resModel: "onlyoffice.odoo.templates",
        views: [[false, "search"]],
      })
      await this.model.load({
        context: this.props.context,
        domain: [["template_model_model", "=", resModel]],
        orderBy: "id",
        resModel: "onlyoffice.odoo.templates",
        searchMenuTypes: [],
        searchViewArch: views.views.search.arch,
        searchViewFields: views.fields,
        searchViewId: views.views.search.id,
      })
      await this.fetchTemplates()
    })
  }

  async createTemplate() {
    // TODO: create template from dialog
  }

  async fetchTemplates(offset = 0) {
    const { domain, context } = this.model
    const records = await this.orm.searchRead(
      "onlyoffice.odoo.templates",
      domain,
      ["display_name", "name", "create_date", "create_uid", "attachment_id", "mimetype"],
      {
        context,
        limit: this.limit,
        offset,
        order: "id",
      },
    )
    this.state.templates = records
    const length = await this.orm.searchCount("onlyoffice.odoo.templates", domain, { context })
    if (!length) {
      this.dialog.add(AlertDialog, {
        body: _t(
          // eslint-disable-next-line @stylistic/max-len
          "You don't have any templates yet. Please go to the ONLYOFFICE Templates app to create a new template or ask your admin to create it.",
        ),
        title: this.dialogTitle,
      })
      return this.data.close()
    }
    this.state.totalTemplates = length
  }

  async fillTemplate() {
    if (this.state.isProcessing) {
      return
    }
    this.state.isProcessing = true

    const templateId = this.state.selectedTemplateId
    const { resId } = this.props

    this.env.services.ui.block()
    try {
      await download({
        data: {
          record_ids: resId,
          template_id: templateId,
        },
        url: "/onlyoffice/template/fill",
      })
    } finally {
      this.env.services.ui.unblock()
    }
    this.env.services.ui.unblock()
    this.data.close()
  }

  selectTemplate(templateId) {
    this.state.selectedTemplateId = templateId
  }

  isSelected(templateId) {
    return this.state.selectedTemplateId === templateId
  }

  onPagerChange({ offset }) {
    this.state.currentOffset = offset
    this.state.selectedTemplateId = null
    return this.fetchTemplates(this.state.currentOffset)
  }

  isButtonDisabled() {
    return this.state.isProcessing || this.state.selectedTemplateId === null
  }

  previewTemplate() {
    const t = this.state.templates.find((item) => item.id === this.state.selectedTemplateId)
    const url = `/web/content/ir.attachment/${t.attachment_id[0]}/datas`

    this.env.services.dialog.add(
      OnlyofficePDFPreview,
      {
        close: () => {
          this.env.services.dialog.close()
        },
        title: t.display_name + ".pdf",
        url: url,
      },
      {
        onClose: () => {
          return
        },
      },
    )
  }
}

TemplateDialog.template = "onlyoffice_odoo_templates.TemplateDialog"
TemplateDialog.components = {
  Dialog,
  Pager,
}
