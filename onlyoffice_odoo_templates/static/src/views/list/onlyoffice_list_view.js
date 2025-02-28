/** @odoo-module **/
import { patch } from "@web/core/utils/patch"
import { ListController } from "@web/views/list/list_controller"
import { TemplateDialog } from "../dialog/onlyoffice_dialog"

patch(ListController.prototype, "ListController.ActionButton", {
  /**
   * @override
   **/
  getActionMenuItems() {
    const menuItems = this._super()
    menuItems.other.push({
      callback: async () => {
        this.env.services.dialog.add(TemplateDialog, {
          resId: await this.model.root.getResIds(true),
          resModel: this.props.resModel,
        })
      },
      description: this.env._t("Print with ONLYOFFICE"),
      skipSave: true,
    })
    return menuItems
  },
})
