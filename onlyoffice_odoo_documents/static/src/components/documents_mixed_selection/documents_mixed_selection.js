/** @odoo-module **/

// prettier-ignore
import { DocumentsMixedSelectionField,
         documentsMixedSelectionField } from "@documents/views/fields/documents_selection_mixed/documents_mixed_selection_field" // eslint-disable-line @stylistic/max-len
import { registry } from "@web/core/registry"
import { SelectionField, selectionField } from "@web/views/fields/selection/selection_field"

const ROLES_BY_EXTENSION = {
  docx: ["commenter", "reviewer"],
  pdf: ["commenter", "form_filling"],
  pptx: ["commenter"],
  xlsx: ["commenter", "custom_filter"],
}

const CUSTOM_ROLES = ["commenter", "reviewer", "form_filling", "custom_filter"]

function filterCustomRoles(options, fileExtension, includeWrite = true) {
  // Multiple selection: remove all custom roles
  if (!fileExtension) {
    const writeRoles = CUSTOM_ROLES.map((r) => `write_${r}`)
    const allRoles = includeWrite ? [...CUSTOM_ROLES, ...writeRoles] : CUSTOM_ROLES
    return options.filter(([value]) => !allRoles.includes(value))
  }

  const allowedRoles = ROLES_BY_EXTENSION[fileExtension] || []
  const allRoles = includeWrite ? [...CUSTOM_ROLES, ...CUSTOM_ROLES.map((r) => `write_${r}`)] : CUSTOM_ROLES

  return options.filter(([value]) => {
    if (!allRoles.includes(value)) {
      return true
    }
    const cleanValue = value.replace("write_", "")
    return allowedRoles.includes(cleanValue)
  })
}

export class OnlyofficeSelectionField extends DocumentsMixedSelectionField {
  get options() {
    const options = super.options
    const fileExtension = this.props.record.data.oo_file_extension
    return filterCustomRoles(options, fileExtension, true)
  }
}

export class OnlyofficeInviteRoleField extends SelectionField {
  get options() {
    const options = super.options
    const fileExtension = this.props.record.data.oo_file_extension
    const filtered = options.filter(([value]) => !value.startsWith("write_") && value !== "none" && value !== "mixed")
    return filterCustomRoles(filtered, fileExtension, false)
  }
}

export const onlyofficeSelectionField = {
  ...documentsMixedSelectionField,
  component: OnlyofficeSelectionField,
}

export const onlyofficeInviteRoleField = {
  ...selectionField,
  component: OnlyofficeInviteRoleField,
}

registry.category("fields").add("onlyoffice_selection", onlyofficeSelectionField)
registry.category("fields").add("onlyoffice_invite_role", onlyofficeInviteRoleField)
