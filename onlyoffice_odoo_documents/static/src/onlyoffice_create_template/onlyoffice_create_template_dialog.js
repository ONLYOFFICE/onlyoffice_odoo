/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";

import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { getDefaultConfig } from "@web/views/view";
import { rpc } from "@web/core/network/rpc";

import { _t } from "@web/core/l10n/translation";

const { Component, useState, useSubEnv } = owl;

export class CreateDialog extends Component {
    setup() {
        this.orm = useService("orm");
        this.rpc = rpc;
        this.viewService = useService("view");
        this.notificationService = useService("notification");
        this.actionService = useService("action");

        this.data = this.env.dialogData;
        useHotkey("escape", () => this.data.close());

        this.dialogTitle = _t("Create with ONLYOFFICE");
        this.state = useState({
            isOpen: true,
            selectedFormat: "docx",
            title: _t("New Document"),
            isCreating: false,
        });
        useSubEnv({
            config: {
                ...getDefaultConfig(),
            },
        });
        this.keepLast = new KeepLast();
    }

    async _createFile() {
        if (this._buttonDisabled()) return;
        this.state.isCreating = true;
        const selectedFormat = this.state.selectedFormat;
        const title = this.state.title;

        const json = await this.rpc(`/onlyoffice/documents/file/create`, {
            folder_id: this.props.folderId,
            title: title,
            format: selectedFormat
        });

        const result = JSON.parse(json);

        this.props.model.load();
        this.props.model.notify();
        
        if (result.error) {
            this.notificationService.add(result.error, {
                type: "error",
                sticky: false,
            }); 
        } else {
            this.notificationService.add(_t("New document created in Documents"), {
                type: "info",
                sticky: false,
            });

            window.open(`/onlyoffice/editor/${result.file_id}`, '_blank');
        }

        this.data.close();
    }

    _selectedFormat(format) {
        this.state.selectedFormat = format;
    }

    _isSelected(format) {
        return this.state.selectedFormat === format;
    }

    _hasSelection() {
        return !!this.state.selectedFormat !== null;
    }

    _buttonDisabled() {
        return this.state.isCreating || !this._hasSelection() || !this.state.title;
    }
}
CreateDialog.components = { Dialog };
CreateDialog.template = "onlyoffice_odoo_documents.CreateDialog";
