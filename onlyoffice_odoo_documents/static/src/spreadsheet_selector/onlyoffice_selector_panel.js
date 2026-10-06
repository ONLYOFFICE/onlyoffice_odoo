/** @odoo-module */
// Copyright (C) 2026 Ascensio System SIA

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
    // The search filter of the parent panel is kept in this.domain
    const { limit, offset } = this.state.pagerProps
    const [records, total] = await this.keepLast.add(
      Promise.all([
        this.orm.call("documents.document", "get_onlyoffice_spreadsheets_to_display", [this.domain], {
          limit,
          offset,
        }),
        this.orm.call("documents.document", "get_onlyoffice_spreadsheets_count", [this.domain]),
      ]),
    )
    this.state.spreadsheets = records
    this.state.pagerProps.total = total
    if (this.state.spreadsheets.length) {
      this._selectItem(this.state.spreadsheets[0].id)
    }
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

/**
 * Odoo 19 builds the dialog's Notebook pages dynamically in JS
 * (`setup()` populates `this.noteBookPages` from the
 * `spreadsheet.mixin.get_selector_spreadsheet_models` RPC) instead of the old
 * QWeb slot-based Notebook. ONLYOFFICE XLSX documents are plain
 * `documents.document` records, not `spreadsheet.mixin` records, so they
 * can't be listed through that RPC. Instead, intercept the assignment of
 * `this.noteBookPages` with a property setter installed before `super.setup()`
 * runs, appending our own tab regardless of when the async assignment
 * happens (it cannot race, unlike a second `onWillStart` hook would).
 */
patch(SpreadsheetSelectorDialog.prototype, {
  setup() {
    let pages = []
    Object.defineProperty(this, "noteBookPages", {
      configurable: true,
      get: () => pages,
      set: (value) => {
        pages = [
          ...value,
          {
            Component: OnlyofficeSelectorPanel,
            id: "onlyoffice",
            props: {
              model: "documents.document",
              onSpreadsheetDblClicked: this._onInsert.bind(this),
              onSpreadsheetSelected: this.onSpreadsheetSelected.bind(this),
            },
            title: "ONLYOFFICE",
          },
        ]
      },
    })
    super.setup()
  },
})
