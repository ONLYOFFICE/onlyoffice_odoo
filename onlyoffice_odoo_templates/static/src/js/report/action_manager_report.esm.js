/** @odoo-module **/

import { download } from "@web/core/network/download"
import { registry } from "@web/core/registry"
import { user } from "@web/core/user"

registry.category("ir.actions.report handlers").add("onlyoffice-pdf_handler", async function (action, options, env) {
  if (action.report_type === "onlyoffice-pdf") {
    const type = action.report_type
    let url = `/report/${type}/${action.report_name}`
    const actionContext = action.context || {}
    if (action.data && JSON.stringify(action.data) !== "{}") {
      // Build a query string with `action.data` (it's the place where reports
      // using a wizard to customize the output traditionally put their options)
      const action_options = encodeURIComponent(JSON.stringify(action.data))
      const context = encodeURIComponent(JSON.stringify(actionContext))
      url += `?options=${action_options}&context=${context}`
    } else {
      if (actionContext.active_ids) {
        url += `/${actionContext.active_ids.join(",")}`
      }
      if (type === "onlyoffice-pdf") {
        const context = encodeURIComponent(JSON.stringify(user.context))
        url += `?context=${context}`
      }
    }
    env.services.ui.block()
    try {
      await download({
        url: "/report/download",
        data: {
          data: JSON.stringify([url, action.report_type]),
          context: JSON.stringify(user.context),
        },
      })
    } finally {
      env.services.ui.unblock()
    }
    // In Odoo 20, the action plugin handles `close_on_report_download`/`onClose`
    // itself once a handler returns a truthy result:
    // addons/web/static/src/webclient/actions/action_plugin.js (_executeReportAction)
    return Promise.resolve(true)
  }
  return Promise.resolve(false)
})
