/** @odoo-module **/

import { registry } from "@web/core/registry"
import { SelectionField } from "@web/views/fields/selection/selection_field"

export class FilteredSelectionField extends SelectionField {
  setup() {
    super.setup()
    this.name = this.props.name
    this.internal_access = this.props.record.context.default_internal_access
    this.link_access = this.props.record.context.default_link_access
  }

  /**
   * @override
   */
  get options() {
    let options = super.options

    if (this.name === "internal_access") {
      if (this.internal_access !== "mixed") {
        options = options.filter((item) => item[0] !== "mixed")
      }
    }

    if (this.name === "link_access") {
      if (this.link_access !== "mixed") {
        options = options.filter((item) => item[0] !== "mixed")
      }
    }
    console.log("this", this)
    console.log("options", options)
    return options
  }
}

registry.category("fields").add("filtered_selection", FilteredSelectionField)
