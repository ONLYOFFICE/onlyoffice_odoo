/** @odoo-module **/
import { _t } from "@web/core/l10n/translation"
import { patch } from "@web/core/utils/patch"
import { FormController } from "@web/views/form/form_controller"
import { TemplateDialog } from "../dialog/onlyoffice_dialog"

patch(FormController.prototype, {
  setup() {
    super.setup(...arguments)
  },

  // eslint-disable-next-line sort-keys
  getStaticActionMenuItems() {
    const { activeActions } = this.archInfo
    const menuItems = super.getStaticActionMenuItems(...arguments)
    menuItems.printWithOnlyoffice = {
      callback: () => {
        this.env.services.dialog.add(TemplateDialog, {
          resId: this.model.root.resId,
          resModel: this.props.resModel,
        })
      },
      description: _t("Print with ONLYOFFICE"),
      icon: "fa fa-print",
      isAvailable: () => activeActions.type === "view",
      sequence: 60,
      skipSave: true,
    }
    return menuItems
  },
})
