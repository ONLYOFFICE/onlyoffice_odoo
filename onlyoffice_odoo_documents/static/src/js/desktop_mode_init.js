/** @odoo-module **/

import { cookie } from "@web/core/browser/cookie"
import { registry } from "@web/core/registry"
import { user } from "@web/core/user"

const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")

if (isDesktopEditor) {
  const getDesktopTheme = () => {
    if (window?.RendererProcessVariable?.theme) {
      const type = window.RendererProcessVariable.theme.type
      if (type === "dark" || type === "light") {
        return type
      }
    }
    return null
  }

  const addBodyClass = () => {
    if (document.body) {
      document.body.classList.add("desktop-editor-mode")
    }
  }

  addBodyClass()

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addBodyClass)
  }

  const DOCUMENTS_URL = "/odoo/action-documents.document_action"

  const shouldRedirect = () => {
    const currentPath = window.location.pathname + window.location.hash + window.location.search

    if (/\/onlyoffice\/editor\//.test(currentPath)) {
      return false
    }

    if (currentPath.includes("/web/login") || currentPath.includes("/web/session")) {
      return false
    }

    if (currentPath.includes("action-documents.document_action") || currentPath.includes("/odoo/documents")) {
      return false
    }

    return true
  }

  const performRedirect = () => {
    if (shouldRedirect()) {
      window.location.replace(`${window.location.origin}${DOCUMENTS_URL}`)
    }
  }

  const syncDesktopTheme = async () => {
    const desktopTheme = getDesktopTheme()
    if (!desktopTheme) {
      return
    }
    const currentSetting = user.settings.color_scheme
    if (currentSetting !== desktopTheme) {
      await user.setUserSettings("color_scheme", desktopTheme)
      cookie.set("color_scheme", desktopTheme)
      window.location.reload()
    }
  }

  const desktopRestrictionService = {
    start(env) {
      env.bus.addEventListener("WEB_CLIENT_READY", () => {
        syncDesktopTheme()
        performRedirect()
      })

      window.addEventListener("hashchange", performRedirect)
      window.addEventListener("popstate", performRedirect)

      document.addEventListener(
        "click",
        (e) => {
          const appIcon = e.target.closest(".o_app")
          if (appIcon) {
            e.preventDefault()
            e.stopPropagation()
            e.stopImmediatePropagation()
            performRedirect()
            return false
          }
        },
        true,
      )
    },
  }

  registry.category("services").add("desktop_restriction", desktopRestrictionService)
}
