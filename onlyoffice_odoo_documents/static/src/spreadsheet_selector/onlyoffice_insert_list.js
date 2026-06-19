/** @odoo-module */

import { SpreadsheetSelectorDialog } from "@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/spreadsheet_selector_dialog"
import { _t } from "@web/core/l10n/translation"
import { patch } from "@web/core/utils/patch"

/**
 * Patch the SpreadsheetSelectorDialog to intercept confirmation
 * when the ONLYOFFICE tab is active. Calls insert_list_in_xlsx on the server
 * to modify the XLSX before opening it.
 */
patch(SpreadsheetSelectorDialog.prototype, {
  async _confirm() {
    const action = await this.actionState.getOpenSpreadsheetAction()

    // Check if this is an ONLYOFFICE insertion (flagged by OnlyofficeSelectorPanel)
    if (action && action.params && action.params.onlyoffice_insert_list) {
      if (this.state.confirmationIsPending) {
        return
      }
      this.state.confirmationIsPending = true

      const threshold = this.state.threshold ? parseInt(this.state.threshold, 10) : 10
      const name = this.state.name ? this.state.name.toString() : "List"
      const listData = this.props.actionOptions.preProcessingAsyncActionData
        ? this.props.actionOptions.preProcessingAsyncActionData.list
        : null

      if (!listData) {
        this.state.confirmationIsPending = false
        return super._confirm()
      }

      try {
        const result = await this.env.services.rpc("/onlyoffice/documents/insert_list_in_xlsx", {
          document_id: action.params.document_id,
          list_data: listData,
          threshold,
          name,
        })

        if (result.error) {
          this.notification.add(_t("Failed to insert list: ") + result.error, { type: "danger" })
          this.state.confirmationIsPending = false
          return
        }

        this.notification.add(_t("List inserted into ONLYOFFICE spreadsheet"), { type: "info" })

        // Open the document in OnlyOffice editor
        this.actionService.doAction({
          type: "ir.actions.client",
          tag: "onlyoffice_editor",
          target: "current",
          params: { document_id: action.params.document_id },
        })
        this.props.close()
      } catch (error) {
        console.error("Failed to insert list:", error)
        this.notification.add(_t("Failed to insert list"), { type: "danger" })
        this.state.confirmationIsPending = false
      }
      return
    }

    // Default behavior for Spreadsheets/Dashboards tabs
    return super._confirm()
  },
})
