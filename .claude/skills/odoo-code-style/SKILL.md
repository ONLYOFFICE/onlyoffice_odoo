---
name: odoo-code-style
description:
  Naming conventions, comment/docstring style, logging patterns, file headers and docbuilder-script conventions actually
  used in the ONLYOFFICE Odoo modules (onlyoffice_odoo, onlyoffice_odoo_documents, onlyoffice_odoo_templates). Use
  whenever generating new Python, JS or .docbuilder code so it matches the surrounding style.
---

# Code Style

This skill documents the conventions **observed in this repo's existing code**, so new code blends in. It does not
replace lint config (`.ruff.toml`, `.pylintrc`, `eslint.config.cjs`, `prettier.config.cjs`) — follow that first for
formatting: line length 120, ruff with `B`, `C90` (max complexity 16), `E501`, `I` (isort sections `odoo` and
`odoo.addons` between third-party and first-party), `UP`; JS without semicolons, 2-space indent, trailing commas,
`proseWrap: always` for Markdown. Run `pre-commit run -a` before finishing.

## Naming

- **Python**: `snake_case` for functions, variables, and module files everywhere (`get_file_ext`,
  `doc_server_public_url`, `config_utils.py`).
- **Python classes**: `PascalCase`. The brand is written **`OnlyOffice`** (capital O twice) in new class names — e.g.
  `OnlyOfficeConnector`, `OnlyOfficeDocumentsAccess`. Do not add underscores inside a class name (see "Known
  inconsistencies" below).
- **Models**: `onlyoffice.odoo.<something>` (`onlyoffice.odoo.templates`, `onlyoffice.odoo.documents.access.user`);
  extensions of core models keep the core name with `_inherit`. Custom fields added to core models are prefixed `oo_` or
  `onlyoffice_` (`oo_attachment_version`, `onlyoffice_spreadsheet_metadata`, `onlyoffice_template_id`).
- **Config parameters**: `onlyoffice_connector.<snake_case>` in a `config_constants.py`, accessed only through
  `get_*`/`set_*` pairs in `config_utils.py` (`get_jwt_secret` / `set_jwt_secret`). Follow this pairing for new
  settings, also in `onlyoffice_odoo_templates/utils`.
- **Routes**: `/onlyoffice/<area>/<action>` (`/onlyoffice/editor/...`, `/onlyoffice/documents/...`,
  `/onlyoffice/template/...`); callback routes under `.../callback/...`.
- **JS**: `camelCase` for variables/functions, `PascalCase` for components/classes (`OnlyofficePreview`,
  `DocumentsAction`); template names `<module>.<ComponentName>`; CSS classes `o-onlyoffice-*` / `o_onlyoffice_*`
  following the surrounding Odoo file; client action tags `onlyoffice_editor`, `onlyoffice_template_editor`; bus events
  `onlyoffice-template-<verb>-<noun>`.
- **Booleans** are prefixed `can_` / `is_` / `has_` (`can_view`, `can_edit`, `is_mobile`, `is_jwt_enabled`, `has_group`,
  `hasLicense`).
- **Odoo API hooks** keep Odoo's own underscore convention (`_onchange_doc_server_public_url`, `_compute_*`,
  `_sql_constraints`). Plain helper methods on controllers (`get_attachment`, `prepare_editor_values`, `filter_xss`) are
  **not** underscore-prefixed in the base module even though they aren't routes; newer code prefixes internal helpers
  (`_check_document_access`, `_get_cached_keys`, `_validate_document_for_convert`, `_store_docbuilder_data`). Match the
  class you are editing; for new classes, prefix non-route helpers with `_`.

## Comments and docstrings

The repo uses two styles side by side; keep each file consistent with itself:

- **Base connector style** (`onlyoffice_odoo/controllers/main.py`, `utils/config_utils.py`, `jwt_utils.py`,
  `file_utils.py`, `models/`): no docstrings — names carry the meaning. A comment only where the _why_ isn't obvious (a
  workaround, a magic number, a version quirk), e.g. `_resolve_env` or the `env.cr.commit()` explanation in
  `get_internal_jwt_secret`: short, explains reasoning, not what the code literally does.
- **Newer code style** (`utils/conversion_utils.py`, `onlyoffice_odoo_documents/controllers/*.py`,
  `models/documents.py`, `onlyoffice_odoo_templates/models/*.py`, `utils/keys_utils.py`): a short docstring on
  functions/methods whose purpose or contract is not obvious — one imperative sentence
  (`"""Return the effective res.lang code for the current request/user."""`), optionally a second paragraph with the
  _why_, and `Args:` only for route handlers with several structured parameters. Trivial getters, `create`/`write`
  overrides that only delegate, and route methods whose name equals the route do not need one. Class docstrings are used
  for the two spreadsheet service classes.
- Inline comments in both styles are short, factual, in simple English. No commented-out code, no restating the obvious,
  no TODO without an owner/context.
- **Tests**: every `test_*` method in the base module gets a one-line docstring in plain English stating the behavior
  being checked (see `onlyoffice_odoo/tests/test_validation_utils.py`); test classes may carry a docstring listing the
  routes or the contract under test (`test_controllers.py`, `test_field_keys_cache.py`). The templates test file uses a
  leading comment instead of a docstring — for new tests prefer the docstring form:
  ```python
  def test_valid_url_ip_with_port(self):
      """DocServer deployed on a bare IP address with port is a valid URL (common in LAN setups)."""
  ```
- Every new `.py`/`.js`/`.xml` file starts with the repo's copyright header (`.docbuilder` files have none):
  ```python
  # Copyright (C) 2026 Ascensio System SIA
  # License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).
  ```
  ```javascript
  /** @odoo-module **/
  // Copyright (C) 2026 Ascensio System SIA
  ```
  ```xml
  <!-- Copyright (C) 2026 Ascensio System SIA -->
  ```
  Files co-authored with Data Dance s.r.o. keep both copyright lines. Do not change existing years or authors.
- Pylint pragmas are used sparingly and inline: `# pylint: disable=invalid-commit` on every intentional
  `env.cr.commit()`, `# noqa: E501` on unavoidable long URLs/strings, `# noqa: C901` on the few long controller methods.

## Logging pattern

- Python: module logger `_logger = logging.getLogger(__name__)` (the templates module uses `logger`; do not introduce a
  third name — match the file).
- Route handlers log entry, then success or failure, prefixed with the HTTP method and route pattern — see
  `onlyoffice_odoo/controllers/main.py`:

  ```python
  _logger.info("POST /onlyoffice/editor/get_config - document: %s, attachment: %s", document_id, attachment_id)
  ...
  _logger.warning("POST /onlyoffice/editor/get_config - attachment not found: %s", attachment_id)
  ...
  _logger.info("POST /onlyoffice/editor/get_config - success: %s", attachment_id)
  ```

  Helper methods use their own name as prefix (`"prepare_editor_values - attachment: %s"`,
  `"fill_template - docbuilder error: %s"`, `"evaluate_formulas_batch: token doc_id=%s != request doc_id=%s"`).

- Use `%s`-style lazy formatting for `_logger` calls, not f-strings — keep the format string and args separate.
  f-strings and `_()` are for user-facing/exception messages, not log calls.
- Levels: `_logger.error` for failures that abort the request (`_logger.exception` when the traceback matters);
  `_logger.warning` for expected rejections (missing record, no access, invalid token) and for per-formula errors in a
  batch; `_logger.info` for normal flow and external requests (`"External request: %s %s"`); `_logger.debug` for
  internal lookups and cache misses.
- Never log secrets or tokens (log URLs without the `oo_security_token` when possible, ids and status codes).
- JS: `console.error("<context>:", error)` in catch blocks that also notify the user; no `console.log` left in committed
  component code (the raw-loaded custom-functions script is the exception and keeps its own prefixed diagnostics).

## `.docbuilder` scripts

- Plain JS executed by the Document Server docbuilder: no modules/imports, `var` declarations, `Api.*` / `builder.*` /
  `GlobalVariable` globals. Files live in `controllers/` and are read with `odoo.tools.file_open`.
- Python composes the final script: `builder.OpenFile("<url>")` prefix + template body + `builder.SaveFile(...)` /
  `builder.CloseFile()` suffix. Insert data only as `json.dumps(...)` literals (`var fields = {...};`) or through
  clearly delimited placeholders replaced by JSON text; never interpolate raw user strings.
- Shared helper functions that several scripts need are kept in one Python constant and substituted as text
  (`_SHARED_DOCBUILDER_HELPERS` in `spreadsheet_docbuilder.py`).

## Known inconsistencies (do not copy these patterns into new code)

The existing code is inconsistent in a few ways. New code should use the fixed convention below, not whatever a
neighboring line happens to do; these are tracked as cleanup, not house style:

- **Brand casing**: some classes use `Onlyoffice` (one capital), others `OnlyOffice`. Use `OnlyOffice` for new classes.
- **Underscores inside PascalCase class names**: `Onlyoffice_Inherited_Connector`, `OnlyofficeTemplate_Connector`,
  `OnlyofficeDocuments_Connector`, `OnlyofficeDocuments_Inherited_Connector`. Odoo controller classes are plain
  CamelCase (`MainController`) — new controller classes must not contain underscores, e.g.
  `OnlyOfficeTemplateConnector`.
- **Logger name**: `_logger` (base, documents) vs `logger` (templates).
- **f-strings in log calls** exist in a few places of the documents controller; use `%s` formatting in new code.
- **OWL imports**: `const { Component } = owl` vs `import { Component } from "@odoo/owl"` — new code imports from
  `@odoo/owl` (see `odoo-owl-assets`).
- **License URL in headers**: a few templates files carry a variant URL; new files use the header shown above.
