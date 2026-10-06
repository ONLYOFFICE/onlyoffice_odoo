/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { Dialog } from "@web/core/dialog/dialog"
import { _t } from "@web/core/l10n/translation"

const { Component, useProps } = owl

export class HelpDialog extends Component {
  props = useProps()

  setup() {
    this.title = _t("Help")
    console.log(this)
  }
}

HelpDialog.template = "onlyoffice_odoo_templates.HelpDialog"
HelpDialog.components = { Dialog }
