/** @odoo-module **/

import { cookie } from "@web/core/browser/cookie"
import { router } from "@web/core/browser/router"
import { _t } from "@web/core/l10n/translation"
import { rpc } from "@web/core/network/rpc"
import { registry } from "@web/core/registry"
import { useBus, useService } from "@web/core/utils/hooks"
import { ExportData } from "./onlyoffice_editor_export_data"

const { Component, useState, onMounted, onWillUnmount } = owl

class TemplateEditor extends Component {
  setup() {
    super.setup(...arguments)
    this.orm = useService("orm")
    this.rpc = rpc
    this.ExportData = ExportData
    this.notificationService = useService("notification")
    this.router = router

    this.state = useState({ resModel: "" })

    this.config = null
    this.docApiJS = null
    this.documentReady = false
    this.hasLicense = false
    this.script = null
    this.unchangedModels = {}

    useBus(this.env.bus, "onlyoffice-template-create-form", (field) => this.createForm(field.detail))

    onMounted(async () => {
      try {
        const attachment_id = this.props.action.params.attachment_id
        const template_model_model = this.props.action.params.template_model_model
        const id = this.props.action.params.id
        this.router.pushState({
          attachment_id: this.props.action.params.attachment_id,
          id: this.props.action.params.id,
          template_model_model: this.props.action.params.template_model_model,
        })

        await this.orm.call("onlyoffice.odoo.templates", "update_relationship", [id, template_model_model])

        const response = await this.rpc("/onlyoffice/template/editor", { attachment_id: attachment_id })
        const config = JSON.parse(response.editorConfig)
        config.events = {
          onDocumentReady: () => {
            if (window.docEditor && "createConnector" in window.docEditor) {
              window.connector = docEditor.createConnector()
              window.connector.executeMethod("GetVersion", [], () => {
                this.hasLicense = true
              })
            }
            // Render fields
            this.state.resModel = template_model_model
            this.documentReady = true
          },
        }
        const theme = cookie.get("color_scheme")
        config.editorConfig.customization = {
          ...config.editorConfig.customization,
          uiTheme: theme ? `theme-${theme}` : "theme-light",
        }
        this.config = config

        this.docApiJS = response.docApiJS
        if (!window.DocsAPI) {
          await this.loadDocsAPI(this.docApiJS)
        }
        if (window.DocsAPI) {
          window.docEditor = new DocsAPI.DocEditor("doceditor", this.config)
        } else {
          throw new Error("window.DocsAPI is null")
        }
      } catch (error) {
        console.error("onMounted TemplateEditor error:", error)
        document.getElementById("error").classList.remove("d-none")
      }
    })

    onWillUnmount(() => {
      if (window.connector) {
        window.connector.disconnect()
        delete window.connector
      }
      if (window.docEditor) {
        window.docEditor.destroyEditor()
        delete window.docEditor
      }
      if (this.script && this.script.parentNode) {
        this.script.parentNode.removeChild(this.script)
      }
      if (window.DocsAPI) {
        delete window.DocsAPI
      }
    })
  }

  async loadDocsAPI(DocsAPI) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script")
      script.src = DocsAPI
      script.onload = resolve
      script.onerror = reject
      document.body.appendChild(script)
      this.script = script
    })
  }

  createForm(field) {
    if (this.documentReady) {
      if (!this.hasLicense) {
        this.notificationService.add(_t("Couldn't insert the field. Please check Automation API."), { type: "danger" })
        return
      }
      Asc.scope.data = field
      window.connector.callCommand(() => {
        var oDocument = Api.GetDocument()
        var oForm = null
        if (
          [
            "char",
            "text",
            "selection",
            "integer",
            "float",
            "monetary",
            "date",
            "datetime",
            "many2one",
            "one2many",
            "many2many",
          ].includes(Asc.scope.data.field_type)
        ) {
          oForm = Api.CreateTextForm({
            key: Asc.scope.data.id.replaceAll("/", " "),
            placeholder: Asc.scope.data.formattedString,
            tip: Asc.scope.data.formattedString,
          })
        }
        if (Asc.scope.data.field_type === "boolean") {
          oForm = Api.CreateCheckBoxForm({
            key: Asc.scope.data.id.replaceAll("/", " "),
            tip: Asc.scope.data.formattedString,
          })
        }
        if (Asc.scope.data.field_type === "binary") {
          oForm = Api.CreatePictureForm({
            key: Asc.scope.data.id.replaceAll("/", " "),
            tip: Asc.scope.data.formattedString,
          })
        }
        var oParagraph = Api.CreateParagraph()
        oParagraph.AddElement(oForm)
        oDocument.InsertContent([oParagraph], true, { KeepTextOnly: true })
      })

      window.docEditor.grabFocus()
    }
  }
}
TemplateEditor.components = {
  ...Component.components,
  ExportData,
}
TemplateEditor.template = "onlyoffice_odoo_templates.TemplateEditor"

registry.category("actions").add("onlyoffice_template_editor", TemplateEditor)
