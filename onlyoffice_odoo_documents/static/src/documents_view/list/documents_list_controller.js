/** @odoo-module **/

import { DocumentsListController } from "@documents/views/list/documents_list_controller"
import { patch } from "@web/core/utils/patch"
import { OnlyofficeDocumentsControllerMixin } from "../onlyoffice_odoo_documents_controller_mixin"

patch(DocumentsListController.prototype, OnlyofficeDocumentsControllerMixin())
