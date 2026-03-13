/** @odoo-module **/

import { registry } from "@web/core/registry"

const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")

if (isDesktopEditor) {
  const addBodyClass = () => {
    if (document.body) {
      document.body.classList.add("desktop-editor-mode")
    }
  }

  addBodyClass()

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addBodyClass)
  }

  const DOCUMENTS_URL = "/web#action=documents.document_action&menu_id=documents.menu_root"

  const shouldRedirect = () => {
    const currentPath = window.location.pathname + window.location.hash + window.location.search

    if (/\/onlyoffice\/editor\//.test(currentPath)) {
      return false
    }

    if (currentPath.includes("/web/login") || currentPath.includes("/web/session")) {
      return false
    }

    if (currentPath.includes("action=documents.document_action") || currentPath.includes("/odoo/documents")) {
      return false
    }

    return true
  }

  const performRedirect = () => {
    if (shouldRedirect()) {
      window.location.replace(`${window.location.origin}${DOCUMENTS_URL}`)
    }
  }

  performRedirect()

  const desktopRestrictionService = {
    start() {
      performRedirect()

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
