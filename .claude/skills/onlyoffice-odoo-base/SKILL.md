---
name: onlyoffice-odoo-base
description:
  The onlyoffice_odoo base connector module — editor open/save flow, JWT layers, settings and demo mode, file formats,
  chatter button, preview, form gallery proxy. Use for any change inside onlyoffice_odoo, and as background when working
  in onlyoffice_odoo_documents or onlyoffice_odoo_templates (both depend on it).
---

# onlyoffice_odoo (base connector)

Opens office files stored in `ir.attachment` in the ONLYOFFICE editor. Provides settings, JWT, the save callback, the
read-only preview, the chatter "Open in ONLYOFFICE" button, and a proxy to the public form-template gallery. No
dependency on Enterprise — `depends: base, mail`; Python dependency `pyjwt`.

`onlyoffice_odoo_documents` and `onlyoffice_odoo_templates` depend on this module and import its controllers/utils
directly (see `onlyoffice-odoo-documents` / `onlyoffice-odoo-templates`).

## Data flow (editor round trip)

1. The user clicks "Open in ONLYOFFICE" (chatter attachment card) or a Documents/Templates button. Depending on the
   "Open file in the same tab" setting the client either runs the OWL client action `onlyoffice_editor` (which POSTs
   `/onlyoffice/editor/get_config`) or opens `/onlyoffice/editor/<attachment_id>` in a new tab.
2. `prepare_editor_values()` builds the editor config: document `key` = `str(id) + checksum`, document URL
   `<odoo_url>onlyoffice/file/content/<id>?oo_security_token=…[&access_token=…]&shardkey=<key>`, `callbackUrl` only when
   the user can write, and `token` (JWT of the whole config) when a Document Server secret is set.
3. The Document Server downloads the file from `/onlyoffice/file/content/<id>` (public route, guarded by
   `oo_security_token` + optional DS JWT header) and users edit in the browser.
4. When editing ends, the Document Server POSTs to `/onlyoffice/editor/callback/<id>`; on status 2/3 Odoo downloads
   `body["url"]` through `onlyoffice_urlopen` and writes it back (`attachment.write({"raw": …})`, or the Documents
   versioning branch when `res_model == "documents.document"`).
5. A stale `key` makes the Document Server serve a cached copy; the key changes because `checksum` changes on write.

## Code map

### `controllers/main.py`

Module-level helpers (import these from other modules):

- `onlyoffice_request(url, method, opts=None, env=None)` — the only correct way to send HTTP requests to the Document
  Server. Logs the request, replaces the public URL by the inner one, honours "disable certificate verification",
  default timeout 120 s (`opts["timeout"]` overrides), raises `requests.exceptions.RequestException` with context on any
  failure. `method` is `"post"` or anything else (= GET).
- `onlyoffice_urlopen(url, timeout=120, context=None, env=None)` — low-level `urllib` variant used by the save callback.
- `_resolve_env(env)` — both helpers accept `env=` so they work outside an HTTP request (report rendering, cron, shell);
  without it they use `request.env`.

`OnlyofficeConnector(http.Controller)` — routes:

| Route                                                  | auth / type                | Notes                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------------ | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /onlyoffice/editor/get_config`                   | user, json, csrf=False     | Params `document_id` or `attachment_id`, `access_token`. Returns the dict from `prepare_editor_values`. Resolves `documents.document` when given a document id or when the attachment belongs to one (soft coupling: no `depends` on `documents`, the model is only browsed in that branch). Read access + `file_utils.can_view` required; `can_write` = write access + `can_edit`. |
| `GET /onlyoffice/file/content/test.txt`                | public                     | Static `test` file; used by settings validation to test the converter.                                                                                                                                                                                                                                                                                                              |
| `GET /onlyoffice/file/content/<int:attachment_id>`     | public                     | File download for the Document Server. `oo_security_token` → user (`get_user_from_token`), `validate_access(access_token)`, `check_access_rights("read")`, DS JWT header check when JWT is enabled, then `ir.binary._get_stream_from(attachment, "datas", …)`.                                                                                                                      |
| `GET /onlyoffice/editor/<int:attachment_id>`           | public, http, website=True | Full-page editor (`onlyoffice_odoo.onlyoffice_editor`). Public so `access_token` links work; access is still checked through `validate_access` + `check_access_rights`.                                                                                                                                                                                                             |
| `POST /onlyoffice/editor/callback/<int:attachment_id>` | public, http, csrf=False   | Save callback. Resolves the user from `oo_security_token`, checks write access, decodes the DS JWT (body `token` or header), reads `status`. Always answers JSON `{"error": 0}` (200) or `{"error": 1, "message": …}` (500).                                                                                                                                                        |
| `GET /onlyoffice/preview?url=&title=`                  | user, http, website=True   | Embedded read-only viewer (`type: embedded`, `mode: view`, key = timestamp). Relative `url`s under `/onlyoffice/file/content/` get an `oo_security_token` appended; other relative URLs are prefixed with the Odoo URL.                                                                                                                                                             |

Helper methods on the same class (used by documents/templates too):
`prepare_editor_values(attachment, access_token, can_write)`,
`get_documents_permissions(attachment, can_write, root_config)` (role → editor permissions; history versions are forced
to view mode; see `onlyoffice-odoo-documents`), `get_attachment(attachment_id, user=None)`,
`get_user_from_token(token)`, `filter_xss(text)` (whitelist: letters, digits, `space _ - , . : @ +`),
`_check_document_access(document)` (lock + `check_access_rule("read")`).

`OnlyOfficeOFormsDocumentsController(http.Controller)` — JSON proxies for the form-template gallery
(`/onlyoffice/oforms/locales`, `/onlyoffice/oforms/category-types`, `/onlyoffice/oforms/subcategories`,
`/onlyoffice/oforms`, all `auth="user"`). They call `oforms.onlyoffice.com` / `cmsoforms.onlyoffice.com` with plain
`requests` (timeout 20 s) — this is not Document Server traffic, so `onlyoffice_request` is not used here. Consumed by
the `FormGallery` component.

### `models/`

- `res_config_settings.py` — `res.config.settings` extension with one field per setting (same names as the config keys).
  `set_values` compares with stored values and, when something changed and demo mode is off before and after, runs
  `validation_utils.settings_validation` before `save_config_values`.
- `onlyoffice_odoo.py` — model `onlyoffice.odoo` (no fields): `get_demo()` → JSON `{"mode", "date"}` and
  `get_same_tab()` → JSON `{"same_tab"}`. Called from JS via `orm.call` before opening the editor; ACL: read for
  `base.group_user`.

There is no `ir.attachment` extension in this module. `oo_attachment_version` is defined in `onlyoffice_odoo_documents`;
the base callback only touches it inside the `documents.document` branch.

### `utils/`

- `config_constants.py` — all settings are `ir.config_parameter` keys under `onlyoffice_connector.*` (one constant per
  setting, plus `doc_server_demo_date` and `internal_jwt_secret` which have no settings field).
- `config_utils.py` — `get_*`/`set_*` pairs; inner URL falls back to the public URL, Odoo URL to `web.base.url`, all
  URLs are normalised with a trailing slash. `get_internal_jwt_secret` generates the secret on first use and commits it
  immediately (commented). `set_demo(True)` overwrites URL/header/secret with the public demo server's values and
  records `doc_server_demo_date` (the 30-day limit is enforced client-side); `set_demo(False)` resets them.
- `jwt_utils.py` — `is_jwt_enabled(env)`, `encode_payload(env, payload, secret=None)` (adds `iat`/`exp`, 24 h, HS256),
  `decode_token(env, token, secret=None)`. `secret=None` means the Document Server secret.
- `url_utils.py` — `replace_public_url_to_internal(env, url)` for server-to-server calls (Docker networks).
- `format_utils.py` — `Format(name, type, actions, convert, mime)` and `get_supported_formats()` which parses
  `static/assets/document_formats/onlyoffice-docs-formats.json` (vendored submodule with its own LICENSE/CHANGELOG; do
  not edit by hand).
- `file_utils.py` — `get_file_ext`, `get_file_type` (word/cell/slide/pdf/diagram), `can_view`, `can_edit`,
  `can_fill_form`, `get_mime_by_ext` (docx/xlsx/pptx/pdf only), `get_file_title_without_ext`, and
  `get_default_file_template(lang, ext)` → bytes of `static/assets/document_templates/<locale>/new.<ext>`
  (`docx`/`xlsx`/`pptx`/`pdf`; locale lookup by full code, then language prefix, then `default`).
- `conversion_utils.py` — converter-service helpers shared with documents and templates: `build_conversion_body` (`key`,
  `url`, `filetype`, `outputtype`, optional `region`, extra options), `sign_conversion_request` (body `token`
  - `<jwt_header>: Bearer …`), `parse_conversion_response` (maps converter error codes −1…−8 to messages),
    `get_region(lang)`.
- `validation_utils.py` — settings validation: `valid_url` regex, mixed-content check (HTTPS Odoo requires HTTPS DS),
  `healthcheck`, CommandService `{"c": "version"}` (error 6 = authorization), and a txt→txt test conversion of
  `/onlyoffice/file/content/test.txt`. Uses the inner URL when it differs from the public one. Errors are raised as
  `ValidationError` (prefixed "Error connecting to demo server" in demo mode).

### `views/`

- `templates.xml` — QWeb `onlyoffice_odoo.onlyoffice_layout` (frontend assets, session info, csrf token, tz cookie) and
  `onlyoffice_odoo.onlyoffice_editor`: loads `docApiJS`, sets `uiTheme` from the `color_scheme` cookie, adds a `goback`
  link to `window.opener` when same-origin, and instantiates `DocsAPI.DocEditor("doceditor", config)`; shows an error
  block when `DocsAPI` is missing. The template also exposes optional values `document_id`, `jwt_token`,
  `filter_values_json`, `has_odoo_formulas` as `window.odoo*` globals and loads
  `static/src/js/odoo_custom_functions_init.js` as a raw script — these are filled by `onlyoffice_odoo_documents` for
  spreadsheets with `ODOO_*` formulas and are empty otherwise.
- `res_config_settings_views.xml` — settings app "ONLYOFFICE" (`groups="base.group_system"`). The last block has
  `id="o_onlyoffice_settings_common"` — other modules insert their settings blocks after this id.

### `static/src/` (frontend)

- `actions/documents_action.js|xml` — OWL client action `onlyoffice_editor` (registered with `{ force: true }`): reads
  `document_id`/`attachment_id` from action params, pushes them to the router, POSTs `/onlyoffice/editor/get_config` via
  `useService("rpc")`, loads `api.js` dynamically, applies the theme, and wires the `ODOO_*` formula init when the
  response has `has_odoo_formulas`.
- `models/attachment_card_onlyoffice.js` + `components/attachment_card_onlyoffice/*.xml` — `patch(AttachmentList)` from
  `@mail/core/common/attachment_list`: "Open in ONLYOFFICE" on chatter attachment cards (viewable/editable per the
  formats JSON); checks the demo period, then `same_tab` → `onlyoffice_editor` action, else new tab
  `/onlyoffice/editor/<id>?access_token=…`. This open logic is repeated in documents/templates — keep them consistent.
- `views/form_gallery/` — `FormGallery` dialog (props `onDownload(form)`, `showType`, `close`) and `views/preview/` —
  `OnlyofficePreview` dialog (iframe on `/onlyoffice/preview`). Both are reused by the documents and templates modules.
- `js/odoo_custom_functions_init.js` — defines `window.initializeOdooCustomFunctions()`: registers the `ODOO_*` custom
  spreadsheet functions through the editor Automation API (`docEditor.createConnector()`, `Api.AddCustomFunction`) and
  batches their evaluation into `POST /onlyoffice/documents/evaluate_formulas_batch` (a route of
  `onlyoffice_odoo_documents`). It is deliberately **not** in the asset bundle: the minifier strips the JSDoc comments
  that `AddCustomFunction` relies on, so it is loaded with a plain `<script>` tag / `loadScript`.
- `css/` — settings, preview and gallery styles.

Assets (`web.assets_backend`): `static/src/actions/*`, `static/src/components/*/*.xml`, `static/src/models/*.js`,
`static/src/views/**/*`, `static/src/css/*`.

## Rules specific to this module

Repo-wide rules (Document Server calls only through the helpers, token checks on public routes, URL building, no new
`cr.commit()`) are in `onlyoffice-odoo-core` and apply here first. In addition:

- Add new formats to the vendored JSON (submodule update), never as hard-coded lists; new blank templates go to
  `static/assets/document_templates/<locale>/`.
- New settings: add the constant, a `get_*`/`set_*` pair, the `res.config.settings` field, `get_values`/`set_values`
  wiring, and the settings view — and decide whether `settings_changed` should trigger validation.
- Anything shown to the Document Server (filename, title) goes through `filter_xss`.

For route/JWT/docbuilder patterns see `odoo-controllers-jwt`; for attachment read/write/versioning see
`odoo-attachments-files`; for the frontend see `odoo-owl-assets`; for repo-wide rules see `onlyoffice-odoo-core`.
