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
   * The search filter of the parent panel is kept in this.domain. The selection is left to the parent: "Blank
   * spreadsheet" when the panel opens, the user's choice when paging or searching.
   * @override
   */
  async _fetchSpreadsheets() {
    const { limit, offset } = this.state.pagerProps
    this.state.spreadsheets = await this.keepLast.add(
      this.orm.call("documents.document", "get_onlyoffice_spreadsheets_to_display", [this.domain], {
        limit,
        offset,
      }),
    )
  }

  /**
   * @override
   */
  async _fetchPagerTotal() {
    return this.orm.call("documents.document", "get_onlyoffice_spreadsheets_count", [this.domain])
  }

  /**
   * As the parent, and tells the dialog the choice is made on the ONLYOFFICE tab: the dialog then knows it without
   * asking for the action, which for "Blank spreadsheet" of the other tabs creates a spreadsheet.
   * @override
   */
  _selectItem(id) {
    this.state.selectedSpreadsheetId = id
    const spreadsheet = id && this.state.spreadsheets.find((s) => s.id === id)
    this.props.onSpreadsheetSelected({
      getOpenSpreadsheetAction: this._getOpenSpreadsheetAction.bind(this),
      isOnlyoffice: true,
      notificationMessage: spreadsheet ? _t("New sheet inserted in '%s'", spreadsheet.name) : this.notificationMessage,
      spreadsheet,
    })
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
