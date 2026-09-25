// Copyright (C) 2026 Ascensio System SIA
import path from "node:path"

export const ODOO_URL = process.env.E2E_ODOO_URL ?? "http://localhost:8069"

/** Connector settings: Docs as seen from the browser and from Odoo, Odoo as seen from Docs. */
export const DOC_SERVER = {
  publicUrl: process.env.E2E_DS_PUBLIC_URL ?? "http://localhost:8080/",
  innerUrl: process.env.E2E_DS_INNER_URL ?? "http://documentserver/",
  odooUrl: process.env.E2E_ODOO_INNER_URL ?? "http://web:8069/",
  jwtSecret: "e2e-secret-0123456789abcdef0123456789",
}

/**
 * The file must be saved 5 s after leaving the editor. Docs assembles it `savetimeoutdelay` (5 s) after the last
 * user leaves: 6-7 s normally, over 20 s in CI and up to a minute locally under load. The real latency is reported
 * as the `save-latency` annotation; 0 makes the check strict.
 */
export const SAVE_GRACE_MS = Number(process.env.E2E_SAVE_GRACE_MS ?? 55_000)

/** Blank office file shipped with the module, used as an upload fixture. */
export const template = (format: string) =>
  path.resolve(__dirname, `../../onlyoffice_odoo/static/assets/document_templates/en-US/new.${format}`)

/** `ir.config_parameter` keys, see `utils/config_constants.py` of onlyoffice_odoo and onlyoffice_odoo_templates. */
export const PARAM = {
  publicUrl: "onlyoffice_connector.doc_server_public_url",
  sameTab: "onlyoffice_connector.same_tab",
  disableFormFields: "onlyoffice_connector.editable_form_fields",
}
