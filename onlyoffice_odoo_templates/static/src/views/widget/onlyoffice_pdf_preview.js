/** @odoo-module **/

import { Component, onMounted, onWillUnmount } from "@odoo/owl"

export class OnlyofficePDFPreview extends Component {
  static template = "onlyoffice_odoo_templates.OnlyofficePDFPreview"

  static props = {
    close: Function,
    title: String,
    url: String,
  }

  setup() {
    const handleKeyDown = (ev) => {
      if (ev.key === "Escape") {
        ev.stopPropagation()
        ev.preventDefault()
        this.props.close()
      }
    }

    onMounted(() => {
      document.addEventListener("keydown", handleKeyDown, { capture: true })
    })

    onWillUnmount(() => {
      document.removeEventListener("keydown", handleKeyDown, { capture: true })
    })
  }

  onClickOutside(ev) {
    const isHeader = ev.target.closest(".o-onlyoffice-preview-header")
    const isBody = ev.target.closest(".o-onlyoffice-preview-body")

    if (!isHeader && !isBody) {
      this.props.close()
    }
  }
}
