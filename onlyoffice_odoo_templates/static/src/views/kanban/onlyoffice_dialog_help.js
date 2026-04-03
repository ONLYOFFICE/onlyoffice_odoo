/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { Dialog } from "@web/core/dialog/dialog"
import { _t } from "@web/core/l10n/translation"

const { Component } = owl

export class HelpDialog extends Component {
  setup() {
    this.title = _t("Help")
    console.log(this)
  }
}

HelpDialog.template = "onlyoffice_odoo_templates.HelpDialog"
HelpDialog.components = { Dialog }
