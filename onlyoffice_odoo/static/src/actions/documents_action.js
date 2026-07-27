/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { cookie } from "@web/core/browser/cookie"
import { registry } from "@web/core/registry"
import { useService } from "@web/core/utils/hooks"

const { Component, onMounted } = owl

export class DocumentsAction extends Component {
  setup() {
    super.setup()
    this.rpc = useService("rpc")
    this.orm = useService("orm")
    this.actionService = useService("action")
    this.router = useService("router")

    onMounted(async () => {
      try {
        const args = {}
        if (this.props.action.params.document_id) {
          const document_id = this.props.action.params.document_id
          args.document_id = document_id
          this.router.pushState({ document_id: document_id })
        } else if (this.props.action.params.attachment_id) {
          const attachment_id = this.props.action.params.attachment_id
          args.attachment_id = attachment_id
          this.router.pushState({ attachment_id: attachment_id })
        }
        const response = await this.rpc("/onlyoffice/editor/get_config", args)
        const config = response.editorConfig
        const theme = cookie.get("color_scheme")
        config.editorConfig.customization = {
          ...config.editorConfig.customization,
          uiTheme: theme ? `default-${theme}` : "default-light",
        }

        // Register ODOO custom functions (ODOO_LIST, ODOO_PIVOT, ...) when the
        // document contains them. Same wiring as the standalone editor page.
        // The init script is loaded raw (not via the assets bundle): the asset
        // minifier strips the JSDoc comments Api.AddCustomFunction relies on.
        if (response.has_odoo_formulas) {
          if (!window.initializeOdooCustomFunctions) {
            await this.loadScript("/onlyoffice_odoo/static/src/js/odoo_custom_functions_init.js")
          }
          window.odooDocumentId = response.document_id
          window.odooJwtToken = response.jwt_token
          window.odooFilterValues = JSON.parse(response.filter_values_json || "{}")
          window._odooRetryCount = 0
          window._odooPollCount = 0
          config.events = config.events || {}
          const originalOnReady = config.events.onDocumentReady
          config.events.onDocumentReady = () => {
            if (originalOnReady) {
              originalOnReady()
            }
            window.initializeOdooCustomFunctions()
          }
        } else {
          delete window.odooDocumentId
          delete window.odooJwtToken
          delete window.odooFilterValues
        }

        this.config = config

        this.docApiJS = response.docApiJS
        if (!window.DocsAPI) {
          await this.loadDocsAPI(this.docApiJS)
        }
        if (window.DocsAPI) {
          window.docEditor = new DocsAPI.DocEditor("doceditor", this.config)
        } else {
          document.getElementById("error").classList.remove("d-none")
          throw new Error("window.DocsAPI is null")
        }
      } catch (error) {
        console.error("onMounted Editor error:", error)
        document.getElementById("error").classList.remove("d-none")
      }
    })
  }

  async loadDocsAPI(DocsAPI) {
    return this.loadScript(DocsAPI)
  }

  async loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script")
      script.src = src
      script.onload = resolve
      script.onerror = reject
      document.body.appendChild(script)
      this.script = script
    })
  }
}

DocumentsAction.template = "onlyoffice_odoo.Editor"

registry.category("actions").add("onlyoffice_editor", DocumentsAction, { force: true })
