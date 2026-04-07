/** @odoo-module **/

import { DocumentsKanbanRecord } from "@documents/views/kanban/documents_kanban_record"
import { patch } from "@web/core/utils/patch"

const isDesktopEditor = navigator.userAgent.includes("AscDesktopEditor")

if (isDesktopEditor) {
  patch(DocumentsKanbanRecord.prototype, {
    onClickPreview(ev) {
      ev.preventDefault()
      ev.stopPropagation()
    },
  })

  document.addEventListener("DOMContentLoaded", () => {
    const observer = new MutationObserver(() => {
      const dropdown = document.querySelector(".o_documents_action_dropdown")
      if (dropdown) {
        const buttons = dropdown.querySelectorAll("button, a")
        buttons.forEach((btn) => {
          if (!btn.classList.contains("o_onlyoffice_open")) {
            btn.style.display = "none"
          }
        })
      }

      const popovers = document.querySelectorAll(".o_popover, .o_mail_activity")
      popovers.forEach((popover) => {
        const isInModal = popover.closest(".modal, .o_dialog, .o_technical_modal, .o-overlay-item")
        if (!isInModal) {
          popover.style.display = "none"
        }
      })

      const dropdownMenus = document.querySelectorAll(".dropdown-menu")
      dropdownMenus.forEach((menu) => {
        const isInModal = menu.closest(".modal, .o_dialog, .o_technical_modal, .o-overlay-item")
        const isActionMenu = menu.closest(".btn-group")
        const isAutocomplete = menu.classList.contains("o-autocomplete--dropdown-menu")
        if (!isInModal && !isActionMenu && !isAutocomplete) {
          menu.style.display = "none"
        }
      })

      const actionSections = document.querySelectorAll(".o_inspector_section_rules")
      actionSections.forEach((section) => {
        section.style.display = "none"
      })
    })

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    })

    document.addEventListener(
      "click",
      (e) => {
        if (e.target.closest(".modal, .o_dialog, .o_technical_modal, .o-overlay-item")) {
          return
        }

        const blockedSelectors = [
          ".o-mail-ActivityButton",
          ".o_field_many2one_avatar_user",
          ".o_activity_button",
          ".o_kanban_previewer",
          ".oe_kanban_previewer",
          ".o_document_preview_button",
          ".o_kanban_image_wrapper",
          ".o_documents_inspector_preview",
          ".o_document_preview",
          ".o_documents_single_preview",
          ".dropdown-item-studio",
        ].join(", ")
        const target = e.target.closest(blockedSelectors)
        if (target && !e.target.closest(".o_field_boolean_favorite")) {
          e.preventDefault()
          e.stopPropagation()
          e.stopImmediatePropagation()
          return false
        }
      },
      true,
    )

    document.addEventListener(
      "dblclick",
      (e) => {
        if (e.target.closest(".modal, .o_dialog, .o_technical_modal, .o-overlay-item")) {
          return
        }

        const previewArea = e.target.closest(".oe_kanban_previewer, .o_kanban_image_wrapper")
        if (previewArea) {
          e.preventDefault()
          e.stopPropagation()
          e.stopImmediatePropagation()
          return false
        }
      },
      true,
    )
  })
}
