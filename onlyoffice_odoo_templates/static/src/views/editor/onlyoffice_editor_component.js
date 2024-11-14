/** @odoo-module **/
import { Component, useState } from "@odoo/owl"

export class EditorComponent extends Component {
  setup() {
    this.state = useState({ isExpanded: false })
  }

  toggleExpand() {
    this.state.isExpanded = !this.state.isExpanded
  }

  onFieldClick(field) {
    this.env.bus.trigger("onlyoffice-template-field-click", field)
  }
}
EditorComponent.components = {
  ...Component.components,
  EditorComponent,
}
EditorComponent.template = "onlyoffice_odoo_templates.EditorComponent"
EditorComponent.props = ["model", "searchString", "level"]
