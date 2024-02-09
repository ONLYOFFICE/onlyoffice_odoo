/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DocumentsKanbanController } from "@documents/views/kanban/documents_kanban_controller";
import { OnlyofficeDocumentsControllerMixin } from "../onlyoffice_odoo_documents_controller_mixin";

patch(DocumentsKanbanController.prototype, OnlyofficeDocumentsControllerMixin());
