/** @odoo-module **/
/**
 * Copyright (C) 2026 Data Dance s.r.o., Ascensio System SIA
 * License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).
 */

import { Component, useState, onMounted } from "@odoo/owl"
import { registry } from "@web/core/registry"
import { useService } from "@web/core/utils/hooks"

/**
 * Client action that embeds the ONLYOFFICE DMS editor in an iframe
 * inside the Odoo shell so the top bar, menu and breadcrumbs remain visible.
 *
 * Registered as tag: "onlyoffice_dms.editor"
 *
 * Expected action context:
 *   - file_id  {Number}  — dms.file record id
 *   - mode     {String}  — "edit" (default) or "view"
 */
export class OnlyofficeDmsEditorAction extends Component {
  static template = "onlyoffice_odoo_dms.EditorAction"

  static props = {
    "*": true,
    action: Object,
  }

  setup() {
    this.actionService = useService("action")
    const ctx = this.props.action.context || {}
    const fileId = ctx.file_id
    const mode = ctx.mode || "edit"
    let url = `/onlyoffice/dms/editor/${fileId}`
    if (mode === "view") {
      url += "?mode=view"
    }
    this.editorUrl = url
    this._mode = mode

    // Env.config.breadcrumbs triggers URL computation in the action service,
    // which is not ready during the initial render — capture it after mount.
    this.bcState = useState({ items: [] })
    onMounted(() => {
      const all = this.env.config.breadcrumbs || []
      const label = this._mode === "view" ? "Preview in ONLYOFFICE" : "Edit in ONLYOFFICE"
      // Replace the last entry (the editor action itself) with a descriptive label
      if (all.length) {
        this.bcState.items = [
          ...all.slice(0, -1),
          {
            jsId: all[all.length - 1].jsId,
            name: label,
          },
        ]
      } else {
        this.bcState.items = []
      }
    })

    // Arrow function so `this` is always the component when called from template
    this.navigateTo = (jsId) => this.actionService.restore(jsId)
  }

  get parentBreadcrumbs() {
    return this.bcState.items.slice(0, -1)
  }

  get currentBreadcrumb() {
    const items = this.bcState.items
    return items.length ? items[items.length - 1].name : ""
  }
}

registry.category("actions").add("onlyoffice_dms.editor", OnlyofficeDmsEditorAction)
