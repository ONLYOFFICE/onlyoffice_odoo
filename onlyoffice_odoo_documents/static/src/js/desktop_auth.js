/** @odoo-module **/

import { registry } from "@web/core/registry"
import { user } from "@web/core/user"

const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")

if (isDesktopEditor && window.AscDesktopEditor) {
  const desktopAuthService = {
    start(env) {
      if (user.userId) {
        const params = {
          displayName: user.name || "User",
          domain: window.location.origin,
          email: user.login || "",
          provider: "odoo",
          userId: String(user.userId),
        }

        window.AscDesktopEditor.execCommand("portal:login", JSON.stringify(params))
      }
    },
  }

  registry.category("services").add("desktop_auth", desktopAuthService)
}
