/** @odoo-module **/

import { DocumentsKanbanController } from "@documents/views/kanban/documents_kanban_controller"
import { patch } from "@web/core/utils/patch"
import { OnlyofficeDocumentsControllerMixin } from "../onlyoffice_odoo_documents_controller_mixin"

patch(DocumentsKanbanController.prototype, OnlyofficeDocumentsControllerMixin())
