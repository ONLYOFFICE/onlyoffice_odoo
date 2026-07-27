/** @odoo-module */

import { SpreadsheetSelectorDialog } from "@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/spreadsheet_selector_dialog" // eslint-disable-line @stylistic/max-len
import { _t } from "@web/core/l10n/translation"
import { patch } from "@web/core/utils/patch"

/**
 * Patch the SpreadsheetSelectorDialog to intercept confirmation
 * when the ONLYOFFICE tab is active.
 *
 * The dialog is opened from several places with different data shapes:
 * - "Insert list in spreadsheet"  -> preProcessingAsyncAction = "insertList"
 * - "Insert pivot in spreadsheet" -> preProcessingAsyncAction = "insertPivot"
 * - "Insert chart in spreadsheet" -> preProcessingAsyncAction = "insertChart"
 * - "Link menu in spreadsheet"    -> preProcessingAction = "insertLink"
 *
 * List and pivot insertion is done server-side: the XLSX file is rebuilt
 * with ODOO_* formulas before opening it in the ONLYOFFICE editor.
 * Link and chart insertion is not supported for ONLYOFFICE spreadsheets.
 */
patch(SpreadsheetSelectorDialog.prototype, {
  async _confirm() {
    const action = await this.actionState.getOpenSpreadsheetAction()

    // Only intercept confirmations coming from the ONLYOFFICE tab
    // (flagged by OnlyofficeSelectorPanel)
    if (!(action && action.params && action.params.onlyoffice_insert)) {
      return super._confirm()
    }

    if (this.state.confirmationIsPending) {
      return
    }
    this.state.confirmationIsPending = true

    try {
      const inserted = await this._onlyofficeInsert(action.params.document_id)
      if (!inserted) {
        this.state.confirmationIsPending = false
        return
      }

      // Open the target document in the ONLYOFFICE editor
      this.actionService.doAction({
        params: { document_id: action.params.document_id },
        tag: "onlyoffice_editor",
        target: "current",
        type: "ir.actions.client",
      })
      this.props.close()
    } catch (error) {
      console.error("ONLYOFFICE insert failed:", error)
      this.notification.add(_t("Failed to insert data into the ONLYOFFICE spreadsheet"), { type: "danger" })
      this.state.confirmationIsPending = false
    }
  },

  /**
   * Insert the pending data (list or pivot) into the selected XLSX document.
   * @param {Number} documentId target documents.document id // eslint-disable-line jsdoc/check-types
   * @returns {Promise<boolean>} true when the insertion succeeded
   */
  async _onlyofficeInsert(documentId) {
    const options = this.props.actionOptions || {}
    const asyncData = options.preProcessingAsyncActionData

    if (options.preProcessingAsyncAction === "insertList" && asyncData && asyncData.list) {
      const name = this.state.name ? this.state.name.toString() : _t("List")
      const threshold = this.state.threshold ? parseInt(this.state.threshold, 10) : 10
      const result = await this.env.services.rpc("/onlyoffice/documents/insert_list_in_xlsx", {
        document_id: documentId,
        list_data: asyncData.list,
        name,
        threshold,
      })
      if (result.error) {
        this.notification.add(_t("Failed to insert list: ") + result.error, { type: "danger" })
        return false
      }
      this.notification.add(_t("List inserted into ONLYOFFICE spreadsheet"), { type: "info" })
      return true
    }

    if (options.preProcessingAsyncAction === "insertPivot" && asyncData && asyncData.metaData) {
      const metaData = asyncData.metaData
      const searchParams = asyncData.searchParams || {}
      const name = this.state.name ? this.state.name.toString() : _t("Pivot")
      const result = await this.env.services.rpc("/onlyoffice/documents/insert_pivot_in_xlsx", {
        document_id: documentId,
        name,
        pivot_data: {
          colGroupBys: metaData.fullColGroupBys || [],
          context: searchParams.context || {},
          domain: searchParams.domain || "[]",
          measures: metaData.activeMeasures || [],
          model: metaData.resModel,
          rowGroupBys: metaData.fullRowGroupBys || [],
        },
      })
      if (result.error) {
        this.notification.add(_t("Failed to insert pivot: ") + result.error, { type: "danger" })
        return false
      }
      this.notification.add(_t("Pivot inserted into ONLYOFFICE spreadsheet"), { type: "info" })
      return true
    }

    // InsertLink / insertChart are not supported for ONLYOFFICE spreadsheets
    this.notification.add(_t("This insert type is not supported for ONLYOFFICE spreadsheets"), { type: "warning" })
    return false
  },
})
