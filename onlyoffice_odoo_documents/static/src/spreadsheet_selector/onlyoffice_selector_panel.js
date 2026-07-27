/** @odoo-module */

import { SpreadsheetSelectorDialog } from "@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/spreadsheet_selector_dialog" // eslint-disable-line @stylistic/max-len
import { SpreadsheetSelectorPanel } from "@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/spreadsheet_selector_panel" // eslint-disable-line @stylistic/max-len
import { _t } from "@web/core/l10n/translation"
import { patch } from "@web/core/utils/patch"

export class OnlyofficeSelectorPanel extends SpreadsheetSelectorPanel {
  constructor() {
    super(...arguments)
    this.notificationMessage = _t("List inserted in ONLYOFFICE spreadsheet")
  }

  /**
   * @override
   */
  async _fetchSpreadsheets() {
    const domain = []
    if (this.currentSearch !== "") {
      domain.push(["name", "ilike", this.currentSearch])
    }
    const { limit, offset } = this.state.pagerProps
    this.state.spreadsheets = await this.keepLast.add(
      this.orm.call("documents.document", "get_onlyoffice_spreadsheets_to_display", [domain], {
        limit,
        offset,
      }),
    )
    if (this.state.spreadsheets.length) {
      this._selectItem(this.state.spreadsheets[0].id)
    }
  }

  /**
   * @override
   */
  async _fetchPagerTotal() {
    return this.orm.call("documents.document", "get_onlyoffice_spreadsheets_count", [[]])
  }

  /**
   * Opens the selected XLSX in OnlyOffice editor.
   * The list/pivot insertion is done server-side before opening.
   * @override
   */
  _getOpenSpreadsheetAction() {
    return {
      params: {
        document_id: this.state.selectedSpreadsheetId,
        onlyoffice_insert: true,
      },
      tag: "onlyoffice_editor",
      type: "ir.actions.client",
    }
  }

  /**
   * @override
   */
  async _getCreateAndOpenSpreadsheetAction() {
    return this._getOpenSpreadsheetAction()
  }
}

patch(SpreadsheetSelectorDialog, {
  components: {
    ...SpreadsheetSelectorDialog.components,
    OnlyofficeSelectorPanel,
  },
})
