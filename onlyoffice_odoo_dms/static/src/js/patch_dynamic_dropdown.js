/** @odoo-module **/
/**
 * Copyright (C) 2026 Data Dance s.r.o.
 * License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).
 */

import { registry } from "@web/core/registry";
import { FieldDynamicDropdown } from "@web_widget_dropdown_dynamic/js/field_dynamic_dropdown.esm";

/**
 * Patch FieldDynamicDropdown to forward `required` into props so the
 * web.SelectionField template hides the empty option when required=true.
 */
FieldDynamicDropdown.props = {
    ...FieldDynamicDropdown.props,
    required: { type: Boolean, optional: true },
};

const fieldsRegistry = registry.category("fields");
const original = fieldsRegistry.get("dynamic_dropdown");
fieldsRegistry.add("dynamic_dropdown", {
    ...original,
    extractProps(fieldInfo, dynamicInfo) {
        return {
            ...original.extractProps(fieldInfo, dynamicInfo),
            required: dynamicInfo.required,
        };
    },
}, { force: true });
