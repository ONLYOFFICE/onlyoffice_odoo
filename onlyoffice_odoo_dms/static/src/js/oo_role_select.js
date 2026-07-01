/** @odoo-module **/
/**
 * Copyright (C) 2026 Data Dance s.r.o., Ascensio System SIA
 * License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
 *
 * Dynamic-select field widget for ONLYOFFICE role assignment.
 * Extends Odoo's built-in SelectionField so that focus, navigation
 * and editable-list behaviour work identically to a normal selection
 * field.  The only difference is that the option list is fetched at
 * runtime via an ORM call and refreshed when context changes.
 */

import { onWillStart, onWillUpdateProps } from "@odoo/owl"
import { _t } from "@web/core/l10n/translation"
import { registry } from "@web/core/registry"
import { SelectionField, selectionField } from "@web/views/fields/selection/selection_field"

class OoRoleSelect extends SelectionField {
  static props = {
    ...SelectionField.props,
    method: { type: String },
    context: { type: Object },
  }

  setup() {
    super.setup()
    this._dynamicItems = []

    const load = async (props) => {
      const { resModel } = props.record.model.config
      this._dynamicItems = await props.record.model.orm.call(resModel, props.method, [], { context: props.context })
    }

    onWillStart(() => load(this.props))

    onWillUpdateProps((next) => {
      if (this.props.context.depending_on !== next.context.depending_on) {
        return load(next)
      }
    })
  }

  get options() {
    return this._dynamicItems
  }
}

registry.category("fields").add("oo_role_select", {
  ...selectionField,
  component: OoRoleSelect,
  displayName: _t("Role Select"),
  supportedTypes: ["char", "selection"],
  extractProps: (fieldInfo, dynamicInfo) => ({
    ...selectionField.extractProps(fieldInfo, dynamicInfo),
    method: fieldInfo.options?.values,
    context: dynamicInfo.context,
  }),
})
