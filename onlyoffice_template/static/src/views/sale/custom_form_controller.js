/** @odoo-module **/
import { FormController } from "@web/views/form/form_controller";
import { TemplateDialog } from "./template_dialog";

export class CustomFormController extends FormController {
    openTemplateDialog() {
        this.env.services.dialog.add(TemplateDialog, {
            formControllerProps: this.props
        });
    }
}

CustomFormController.template = "onlyoffice_template.CustomFormController";
