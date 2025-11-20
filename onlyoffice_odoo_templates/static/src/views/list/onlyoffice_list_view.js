/** @odoo-module **/
import { _t } from "@web/core/l10n/translation"
import { patch } from "@web/core/utils/patch"
import { ListController } from "@web/views/list/list_controller"
import { TemplateDialog } from "../dialog/onlyoffice_dialog"

patch(ListController.prototype, {
  setup() {
    super.setup(...arguments)
  },

  /**
   * @override
   **/
  // eslint-disable-next-line sort-keys
  getStaticActionMenuItems() {
    const menuItems = super.getStaticActionMenuItems()
    menuItems.printWithOnlyoffice = {
      callback: async () => {
        this.env.services.dialog.add(TemplateDialog, {
          resId: await this.model.root.getResIds(true),
          resModel: this.props.resModel,
        })
      },
      description: _t("Print with ONLYOFFICE"),
      icon: "fa fa-print",
      skipSave: true,
    }
    return menuItems
  },
})
