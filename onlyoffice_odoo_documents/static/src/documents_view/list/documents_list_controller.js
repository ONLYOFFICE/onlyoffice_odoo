/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DocumentsListController } from "@documents/views/list/documents_list_controller";
import { OnlyofficeDocumentsControllerMixin } from "../onlyoffice_odoo_documents_controller_mixin";

patch(DocumentsListController.prototype, "onlyoffice_odoo_documents_kanban_controller", OnlyofficeDocumentsControllerMixin);