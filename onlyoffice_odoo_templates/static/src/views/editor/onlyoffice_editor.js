/** @odoo-module **/

import { cookie } from "@web/core/browser/cookie";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { EditorComponent } from "./onlyoffice_editor_component";

import { _t } from "@web/core/l10n/translation";

const { Component, useState, onMounted, onWillUnmount } = owl;

class TemplateEditor extends Component {
  setup() {
    super.setup(...arguments);
    this.orm = useService("orm");
    this.rpc = rpc;
    this.viewService = useService("view");
    this.EditorComponent = EditorComponent;
    this.notificationService = useService("notification");
    
    this.state = useState({
      models: null,
      searchString: "",
    });

    this.config = null;
    this.docApiJS = null;
    this.documentReady = false;
    this.hasLicense = false;
    this.script = null;
    this.unchangedModels = {};

    useBus(this.env.bus, "onlyoffice-template-field-click", (field) => this.onFieldClick(field.detail));

    onMounted(async () => {
      try {
        if (!this.props.id) {
          const urlParams = new URLSearchParams(window.location.hash);
          let id = urlParams.get('id');
          if (!id) return
          this.props.id = id;
        }

        const [{ template_model_model, attachment_id }] = await this.orm.read("onlyoffice.odoo.templates", [parseInt(this.props.id)], ["template_model_model", "attachment_id"]);

        // Set id to URL
        if (!new URLSearchParams(window.location.hash).has("id")) {
          const newUrl = window.location.href + `&id=${this.props.id}`;
          history.replaceState(null, null, newUrl);
        }

        const models = JSON.parse(
          await this.orm.call("onlyoffice.odoo.templates", "get_fields_for_model", [template_model_model]),
        );

        // Add keys to field
        const formattedModels = this.formatModels(models);
        this.unchangedModels = formattedModels;

        const response = await this.rpc(`/onlyoffice/template/editor`, {
          attachment_id: attachment_id[0],
        });
        const config = JSON.parse(response.editorConfig);
        config.events = {
          onDocumentReady: () => {
            if (window.docEditor && 'createConnector' in window.docEditor) {
              window.connector = docEditor.createConnector();
              window.connector.executeMethod("GetVersion", [], (_version) => {
                this.hasLicense = true;
              });
            }
            // Render fields
            this.state.models = formattedModels;
            this.documentReady = true;
          },
        };
        const theme = cookie.get("color_scheme");
        config.editorConfig.customization = {
          ...config.editorConfig.customization,
          uiTheme: theme ? `theme-${theme}` : "theme-light",
        };
        this.config = config;

        this.docApiJS = response.docApiJS;
        if (!window.DocsAPI) {
          await this.loadDocsAPI(this.docApiJS);
        }
        if (window.DocsAPI) {
          window.docEditor = new DocsAPI.DocEditor("doceditor", this.config);
        } else {
          throw new Error("window.DocsAPI is null");
        }
      } catch (error) {
        console.error("onMounted TemplateEditor error:", error);
        document.getElementById("error").classList.remove("d-none");
      }
    });

    onWillUnmount(() => {
      if (window.connector) {
        window.connector.disconnect();
        delete window.connector;
      }
      if (window.docEditor) {
        window.docEditor.destroyEditor();
        delete window.docEditor;
      }
      if (this.script && this.script.parentNode) {
        this.script.parentNode.removeChild(this.script);
      }
      if (window.DocsAPI) {
        delete window.DocsAPI;
      }
    });
  }

  async loadDocsAPI(DocsAPI) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = DocsAPI;
      script.onload = resolve;
      script.onerror = reject;
      document.body.appendChild(script);
      this.script = script;
    });
  }

  formatModels(models, parentNames = []) {
    if (!models.fields) return models;
    models.fields = models.fields.map((field) => {
      const key = [...parentNames, field.name].join(" ");
      field.key = key;
      if (field.related_model) {
        field.related_model = this.formatModels(field.related_model, [...parentNames, field.name]);
      }
      return field;
    }).sort((a, b) => {
      if (a.related_model && !b.related_model) {
        return -1;
      }
      if (!a.related_model && b.related_model) {
        return 1;
      }
      return a.key.localeCompare(b.key);
    });
    return models;
  }

  setModelsFilter() {
    const searchAndExpand = (models) => {
      if (!models.fields) return;
      const searchString = this.state.searchString.toLowerCase();
      const filteredFields = models.fields.filter(field => {
        if (field.key.split(' ').pop().toLowerCase().includes(searchString)) {
          return true;
        } else if (field.related_model) {
          field.related_model = searchAndExpand(field.related_model);
          return field.related_model !== null;
        }
        return false;
      });
    
      if (filteredFields.length === 0) {
        return null;
      }
    
      return {
        ...models,
        fields: filteredFields
      };
    }
    const unchangedModels = structuredClone(this.unchangedModels);
    this.state.models = searchAndExpand(unchangedModels);
  }

  onCleanSearchClick() {
    if (this.documentReady) {
      this.state.searchString = "";
      this.state.models = this.unchangedModels;
    }
  }

  onSearchInput() {
    if (this.documentReady) {
      if (this.state.searchString) {
        this.setModelsFilter();
      } else {
        this.onCleanSearchClick();
      }
    }
  }

  onFieldClick(field) {
    if (this.documentReady) {
      if (!this.hasLicense) {
        this.notificationService.add(_t("Couldn't insert the field. Please check Automation API."), { type: "danger" });
        return;
      } else {
        const type = field.type;
        // TODO: add image form and other forms
        if (
          type === "char" ||
          type === "text" ||
          type === "selection" ||
          type === "integer" ||
          type === "float" ||
          type === "monetary" ||
          type === "date" ||
          type === "datetime" ||
          type === "many2one" ||
          type === "one2many" ||
          type === "many2many"
        ) {
          this.createTextForm(field);
        }
        if (type === "boolean") {
          this.createCheckBoxForm(field);
        }
        if (type === "binary") {
          this.createPictureForm(field);
        }
        window.docEditor.grabFocus();
      }
    }
  }

  createTextForm = (data) => {
    Asc.scope.data = data;
    window.connector.callCommand(() => {
      var oDocument = Api.GetDocument();
      var oTextForm = Api.CreateTextForm({
        key: Asc.scope.data.key,
        placeholder: Asc.scope.data.string,
        tip: Asc.scope.data.string,
        tag: Asc.scope.data.model,
      });
      var oParagraph = Api.CreateParagraph();
      oParagraph.AddElement(oTextForm);
      oDocument.InsertContent([oParagraph], true, { KeepTextOnly: true });
    });
  };

  createCheckBoxForm = (data) => {
    Asc.scope.data = data;
    window.connector.callCommand(() => {
      var oDocument = Api.GetDocument();
      var oCheckBoxForm = Api.CreateCheckBoxForm({
        key: Asc.scope.data.key,
        tip: Asc.scope.data.string,
        tag: Asc.scope.data.model,
      });
      oCheckBoxForm.ToInline();
      var oParagraph = Api.CreateParagraph();
      oParagraph.AddElement(oCheckBoxForm);
      oDocument.InsertContent([oParagraph], true, { KeepTextOnly: true });
    });
  };

  createPictureForm = (data) => {
    Asc.scope.data = data;
    window.connector.callCommand(() => {
      var oDocument = Api.GetDocument();
      var oPictureForm = Api.CreatePictureForm({
        key: Asc.scope.data.key,
        placeholder: Asc.scope.data.string,
        tip: Asc.scope.data.string,
        tag: Asc.scope.data.model,
      });
      var oParagraph = Api.CreateParagraph();
      oParagraph.AddElement(oPictureForm);
      oDocument.InsertContent([oParagraph], true, { KeepTextOnly: true });
    });
  };
}
TemplateEditor.components = {
  ...Component.components,
  EditorComponent,
};
TemplateEditor.template = "onlyoffice_odoo_templates.TemplateEditor";

registry.category("actions").add("onlyoffice_odoo_templates.TemplateEditor", TemplateEditor);
