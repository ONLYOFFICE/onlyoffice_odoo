---
name: odoo-code-style
description:
  Naming conventions, comment/docstring style, and logging patterns actually used in the ONLYOFFICE Odoo modules
  (onlyoffice_odoo, onlyoffice_odoo_documents, onlyoffice_odoo_templates). Use whenever generating new Python or JS code
  so it matches the surrounding style.
---

# Code Style

This skill documents the naming and comment conventions **observed in this repo's existing code** (`onlyoffice_odoo/`,
`onlyoffice_odoo_documents/`, `onlyoffice_odoo_templates/`), so new code blends in. It does not replace lint config
(`.ruff.toml`, `.pylintrc`, `eslint.config.cjs`, `prettier.config.cjs`) — follow that first for formatting (line length
120, no semicolons in JS, 2-space JS indent, isort section order, etc.).

## Naming

- **Python**: `snake_case` for functions, variables, and module files everywhere (`get_file_ext`,
  `doc_server_public_url`, `config_utils.py`).
- **Python classes**: `PascalCase`. The brand is written **`OnlyOffice`** (capital O twice) in new class names — e.g.
  `OnlyOfficeConnector`, `OnlyOfficeDocumentsAccess`. Do not add underscores inside a class name (see "Known issues"
  below).
- **JS**: `camelCase` for variables/functions, `PascalCase` for components/classes (`OnlyofficePreview`,
  `DocumentsAction`).
- **Booleans** are prefixed `can_` / `is_` / `has_` (`can_view`, `can_edit`, `is_mobile`, `is_jwt_enabled`,
  `has_group`).
- **Config accessors** come in `get_*`/`set_*` pairs in `config_utils.py` (`get_jwt_secret` / `set_jwt_secret`,
  `get_doc_server_public_url` / `set_doc_server_public_url`). Follow this pairing for new settings.
- **Odoo API hooks** keep Odoo's own underscore convention (`_onchange_doc_server_public_url`, `_compute_*`,
  `_sql_constraints`). Plain helper methods on controllers (`get_attachment`, `prepare_editor_values`, `filter_xss`) are
  **not** underscore-prefixed in this repo even though they aren't routes — match whichever convention the surrounding
  class already uses (some controllers do prefix internal helpers, e.g. `_check_document_access`; check the class before
  adding a new helper).

## Comments and docstrings

- **No docstrings in controllers, models, or utils.** Names carry the meaning (`get_file_type`, `filter_xss`). Add a
  comment only when the _why_ isn't obvious from the code — a workaround, a magic number, a version-specific quirk (see
  `_resolve_env` in `onlyoffice_odoo/controllers/main.py` for the style: short, explains reasoning, not what the code
  literally does).
- **Tests are the exception**: every `test_*` method gets a short one-line docstring in plain English stating what
  behavior is being checked (see `onlyoffice_odoo/tests/test_validation_utils.py`), e.g.:
  ```python
  def test_valid_url_ip_with_port(self):
      """DocServer deployed on a bare IP address with port is a valid URL (common in LAN setups)."""
  ```
- Keep any comment short and factual. No commented-out code, no restating the obvious.
- Every new `.py`/`.js` file starts with the repo's copyright header:
  ```python
  # Copyright (C) 2026 Ascensio System SIA
  # License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).
  ```
  ```javascript
  /** @odoo-module **/
  // Copyright (C) 2026 Ascensio System SIA
  ```

## Logging pattern (controllers)

Route handlers log entry, then success or failure, prefixed with the HTTP method and route pattern — see
`onlyoffice_odoo/controllers/main.py`:

```python
_logger.info("POST /onlyoffice/editor/get_config - document: %s, attachment: %s", document_id, attachment_id)
...
_logger.warning("POST /onlyoffice/editor/get_config - attachment not found: %s", attachment_id)
...
_logger.info("POST /onlyoffice/editor/get_config - success: %s", attachment_id)
```

- Use `%s`-style lazy formatting for `_logger` calls, not f-strings — keep the format string and args separate.
- f-strings and `_()` are for user-facing/exception messages, not log calls.
- `_logger.error` for failures that abort the request; `_logger.warning` for expected rejections (missing record, no
  access); `_logger.info` for normal flow; `_logger.debug` for internal lookups (`get_attachment`).

## Known issues (do not copy these patterns into new code)

The existing code is inconsistent in a couple of ways. New code should use the fixed convention below, not whatever a
neighboring line happens to do; these are tracked as cleanup, not house style:

- **Brand casing**: some classes use `Onlyoffice` (one capital), others `OnlyOffice`. Standard Odoo class-naming is
  CamelCase with no internal underscores — use `OnlyOffice` for new classes.
- **Underscores inside PascalCase class names**: e.g. `Onlyoffice_Inherited_Connector`, `OnlyofficeTemplate_Connector`,
  `OnlyofficeDocuments_Connector` in the documents/templates controllers. This is not standard Odoo/Python style (Odoo
  controller classes are plain CamelCase, e.g. `MainController`). New controller classes must not contain underscores —
  e.g. `OnlyOfficeInheritedConnector`, `OnlyOfficeTemplateConnector`.
