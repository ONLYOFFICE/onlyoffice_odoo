/** @odoo-module **/

import { registry } from "@web/core/registry"
import { session } from "@web/session"

const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")

if (isDesktopEditor && window.AscDesktopEditor) {
  const desktopAuthService = {
    sendLoginCommand() {
      const params = {
        displayName: session.partner_display_name || session.name || "User",
        domain: window.location.origin,
        email: session.username || "",
        provider: "odoo",
        userId: String(session.uid),
      }

      window.AscDesktopEditor.execCommand("portal:login", JSON.stringify(params))
    },

    start() {
      if (session.uid && session.uid !== false) {
        this.sendLoginCommand()
      }
    },
  }

  registry.category("services").add("desktop_auth", desktopAuthService)
}
