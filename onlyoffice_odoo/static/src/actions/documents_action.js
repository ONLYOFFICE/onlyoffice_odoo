/** @odoo-module **/
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
    this.cookies = useService("cookie")

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
        const config = JSON.parse(response.editorConfig)
        const theme = this.cookies.current.color_scheme
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
    return new Promise((resolve, reject) => {
      const script = document.createElement("script")
      script.src = DocsAPI
      script.onload = resolve
      script.onerror = reject
      document.body.appendChild(script)
      this.script = script
    })
  }
}

DocumentsAction.template = "onlyoffice_odoo.Editor"

registry.category("actions").add("onlyoffice_editor", DocumentsAction, { force: true })
