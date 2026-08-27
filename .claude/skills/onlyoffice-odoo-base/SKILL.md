---
name: onlyoffice-odoo-base
description:
  The onlyoffice_odoo base connector module — editor open/save flow, JWT layers, config storage, file utils, attachment
  integration. Use for any change inside onlyoffice_odoo, and as background when working in onlyoffice_odoo_documents or
  onlyoffice_odoo_templates (both depend on it).
---

# onlyoffice_odoo (base connector)

Opens office files from `ir.attachment` in the ONLYOFFICE editor. Provides settings, JWT, the save callback, and the
read-only preview. No dependency on Enterprise — `depends: base, mail`.

`onlyoffice_odoo_documents` and `onlyoffice_odoo_templates` both depend on this module and reuse its controllers/utils
directly (see `onlyoffice-odoo-documents` / `onlyoffice-odoo-templates`).

## Data flow

1. The user opens a file. A controller builds an editor config (document URL, permissions, callback URL) and renders the
   `onlyoffice_odoo.onlyoffice_editor` QWeb page which loads `api.js` from the Document Server.
2. The Document Server downloads the file from Odoo (`/onlyoffice/file/content/<id>`), users edit it in the browser.
3. When editing ends, the Document Server POSTs to `/onlyoffice/editor/callback/<id>` with status 2 or 3. Odoo downloads
   the result and writes it back to the attachment.
4. Two JWT layers protect this: the Document Server secret (config) and an internal secret used for `oo_security_token`
   (identifies the Odoo user on public routes).

## Code map

- `controllers/main.py`
  - `onlyoffice_request(url, method, opts, env=None)` — the only correct way to send HTTP requests to the Document
    Server. Respects the "disable certificate verify" setting. `onlyoffice_urlopen` is the low-level variant used by the
    save callback.
  - `OnlyofficeConnector` — routes:
    - `POST /onlyoffice/editor/get_config` (json) — editor config for OWL views
    - `GET /onlyoffice/editor/<attachment_id>` — full editor page
    - `GET /onlyoffice/file/content/<attachment_id>` (public) — file download for the Document Server, guarded by
      `oo_security_token` + JWT
    - `POST /onlyoffice/editor/callback/<attachment_id>` (public) — save callback; status 2/3 means "download the result
      and store it"
    - `GET /onlyoffice/preview` — embedded read-only viewer
  - `prepare_editor_values()` — builds the config: document key (`id + checksum`), URLs, permissions, JWT token.
  - `OnlyOfficeOFormsDocumentsController` — proxy routes to the public oforms/cmsoforms APIs (form template gallery),
    unrelated to the editor flow.
- `utils/config_utils.py` + `utils/config_constants.py` — all settings are `ir.config_parameter` records under
  `onlyoffice_connector.*`: public URL, inner URL, Odoo URL override, JWT secret/header, demo mode, internal secret.
- `utils/jwt_utils.py` — HS256 encode/decode with 24h expiry. Two secrets: the Document Server secret (external) and the
  internal secret used for `oo_security_token` (carries the Odoo user id to public routes).
- `utils/file_utils.py` — file extension lists (view/edit), mimetypes, new-file templates by language.
- `utils/url_utils.py` — swaps the public Document Server URL for the inner one for server-to-server calls (Docker
  networks).
- `utils/validation_utils.py` — settings-form validation (URL shape, mixed content, live doc-server
  healthcheck/convert/command checks).
- `models/` — `res.config.settings` extension (settings form fields/save) and `ir.attachment` extension
  (`oo_attachment_version`, `validate_access`).

## Rules specific to this module

- Never call `requests` directly for Document Server traffic — use `onlyoffice_request` so certificate settings and URL
  replacement work.
- Public routes must validate `oo_security_token` (internal JWT) and, when JWT is enabled, the Document Server token
  too. Never trust a bare attachment id.
- Build callback/content URLs from `config_utils.get_base_or_odoo_url(env)`, never from `request.httprequest.host`.
- Keep `env.cr.commit()` out of new code unless there is a documented reason (existing spots have comments explaining
  why).

For route/JWT patterns in depth see `odoo-controllers-jwt`; for attachment read/write/versioning see
`odoo-attachments-files`; for repo-wide rules (version detection, external sources, manifest version) see
`onlyoffice-odoo-core`.
