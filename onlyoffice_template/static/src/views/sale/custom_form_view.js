/** @odoo-module **/
import { formView } from '@web/views/form/form_view';
import { CustomFormController } from "./custom_form_controller";
import { registry } from "@web/core/registry";

export const customInfoView = {
   ...formView,
   Controller: CustomFormController,
};
registry.category("views").add("onlyoffice_info_view", customInfoView);
