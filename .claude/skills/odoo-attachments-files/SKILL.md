---
name: odoo-attachments-files
description:
  Working with ir.attachment, binary fields, base64 data, file streaming, mimetypes, access tokens, supported formats,
  blank templates, XLSX parsing and document versioning in the ONLYOFFICE Odoo modules. Use when reading, writing,
  versioning, converting, or serving files.
---

# Attachments and Files

## ir.attachment essentials

| Field                  | Meaning                                                |
| ---------------------- | ------------------------------------------------------ |
| `datas`                | 17-19: base64 string of the content. **Removed in 20** |
| `raw`                  | raw content (preferred for writes, no base64 step)     |
| `name`                 | filename with extension                                |
| `mimetype`             | set it explicitly when writing new content             |
| `checksum`             | changes with content; part of the editor document key  |
| `res_model` / `res_id` | owner record                                           |
| `access_token`         | share token, checked by `validate_access` (core API)   |

Write patterns:

```python
attachment.write({"raw": file_bytes, "mimetype": guess_type(url)[0]})   # bytes
attachment.write({"datas": base64.b64encode(file_bytes)})               # base64
```

Do not mix them up: `raw` = bytes, `datas` = base64. A wrong choice corrupts the file silently. Set `mimetype`
explicitly for generated XLSX (`XLSX_MIMETYPE` from `onlyoffice_odoo_documents/controllers/spreadsheet_docbuilder.py`) —
Odoo may sniff a rebuilt workbook as `application/zip`.

Documents app: writing `documents.document.write({"datas": ..., "mimetype": ...})` (20: `{"raw": ...}`) creates a
**new** attachment behind the document; the previous one stays attached to the document (this is what the version
history relies on).

### Odoo 20: binary values

- `datas` no longer exists on `ir.attachment` nor on `documents.document`. Writing it to `ir.attachment` is **silently
  ignored** (only a `warnings.warn`), so a save looks successful and loses the content. Always write `raw`.
- A binary field value is a `BinaryValue` (`odoo.tools.binary`), not base64 `bytes`: use `.content` for the bytes,
  `.to_base64()` for a base64 string, `.size`, `.filename`. `json.loads(attachment.raw)` fails — use
  `json.loads(attachment.raw.content)`.
- Writing a binary field accepts a `BinaryValue` (`BinaryBytes(data)`), a base64 `str` (what the web client sends) or a
  `{"filename", "content"}` dict. Raw `bytes` are accepted only by `raw`; any other binary field raises `TypeError`.
  Normalize unknown input with `record._fields[name].convert_to_cache(value, record).content`.
- `read()` returns a binary field as `{"content": <base64>, "size": ..., "filename"?: ...}`; `search_read`-based RPC
  results (e.g. thumbnails sent to JS) have that shape too. Never put a `BinaryValue` in a JSON response.

## Serving file content

Stream instead of loading into memory (base module `get_file_content`):

```python
stream = request.env["ir.binary"]._get_stream_from(attachment, "raw", None, "name", None)  # 17-19: "datas"
return stream.get_response(as_attachment=True, max_age=None)
```

For small generated content use `request.make_response(content, headers)` with `Content-Type`, `Content-Length`,
`Content-Disposition`, and `X-Content-Type-Options: nosniff` for downloads (templates fill route, docbuilder files).
Docbuilder scripts are served as `text/plain` with an attachment disposition.

## Access checks (this repo's contract)

Before returning any file:

1. `attachment.validate_access(access_token)` — share-token check.
2. ORM access check for `"read"` (or `"write"` for saves). The API name is version-specific:
   - 17: `attachment.check_access_rights(op)` / `check_access_rule(op)`
   - 18/19/20: `attachment.has_access(op)` / `attachment.check_access(op)` (`check_access_rights` is removed in 20; for
     a model-level check use `attachment.browse().has_access(op)`)
3. For `documents.document` owners: lock check (`is_locked` and `lock_uid != user`) + the same version's rule check for
   `"read"` (`OnlyofficeConnector._check_document_access`).
4. On public routes: resolve the user from `oo_security_token` first and use `with_user(user)` for all of the above.

## Supported formats

Formats are data, not code: `onlyoffice_odoo/static/assets/document_formats/onlyoffice-docs-formats.json` (vendored
submodule; do not hand-edit — update the submodule). Each entry has `name` (extension), `type`
(`word`/`cell`/`slide`/`pdf`/`diagram`), `actions` (`view`, `edit`, `fill`, ...), `convert` (target extensions) and
`mime`.

- Python: `format_utils.get_supported_formats()` → list of `Format`; `file_utils` wraps it: `get_file_ext(name)`,
  `get_file_type(name)`, `can_view(name)`, `can_edit(name)`, `can_fill_form(name)`, `get_mime_by_ext(ext)`
  (docx/xlsx/pptx/pdf only), `get_file_title_without_ext(name)`.
- JS: the same JSON is fetched at runtime
  (`/onlyoffice_odoo/static/assets/document_formats/onlyoffice-docs-formats.json`) by the chatter patch, the Documents
  inspector patch and the convert dialog (`convert` list = allowed targets).
- The documents `file/convert` route only accepts a target that is in the source format's `convert` list.

Never inline extension lists in controllers or components.

## Blank templates

`file_utils.get_default_file_template(lang, ext)` returns the bytes of
`onlyoffice_odoo/static/assets/document_templates/<locale>/new.<ext>` for `docx`, `xlsx`, `pptx` and `pdf` (blank PDF
form). Locale resolution: exact code (`pt-BR`, `zh-CN`), then language prefix (`pt`), then `default`. Used by
`file/create` (documents) and by template creation without a file (templates). New languages: add a folder with all four
files and a mapping entry in `locale_path`.

## Reading uploaded XLSX (documents module)

XLSX files are zip archives; the documents module reads parts of them (`xl/workbook.xml`, `xl/_rels/workbook.xml.rels`,
sheet XML, `xl/sharedStrings.xml`) with `zipfile.ZipFile` + `xml.etree.ElementTree` — for the hidden `_OdooMetadata`
sheet (`models/documents.py::_extract_odoo_metadata_from_xlsx`) and for existing sheet names
(`spreadsheet_docbuilder.py::_unique_sheet_name`). Wrap such parsing in `try/except` and treat a failure as "no
metadata", as the existing code does; do not let a malformed upload break the editor open.

## Temporary storage between requests (docbuilder cache)

The documents docbuilder flow stores payloads and source XLSX bytes as `ir.attachment` records named
`onlyoffice_docbuilder_cache_<uuid>` (created with `sudo()`, committed immediately, TTL 1 h, stale rows purged on the
next store). Reuse this helper (`_store_docbuilder_data` / `_load_docbuilder_data` / `_delete_docbuilder_data` in
`spreadsheet_docbuilder.py`) instead of module-level dicts — the Document Server's callback can hit another worker.

## Reacting to file changes (templates module)

`onlyoffice_odoo_templates/models/ir_attachment.py` overrides `create`/`write` and, when a content field (`datas`,
`raw`, `db_datas`, `store_fname`) changes on an attachment with `res_model == "onlyoffice.odoo.templates"`, schedules
`_refresh_template_field_keys` via `env.cr.postcommit`. Pass context `skip_field_keys_refresh=True` for bulk imports
(demo templates). Follow this pattern for any "recompute something when the file changes" need. On Odoo 20 the
transaction is reset after the commit, so a postcommit hook must open its own cursor
(`with self.env.registry.cursor() as cr: env = self.env(cr=cr)`); tests run the queue inside `registry_test_mode()`.

## Versioning (documents module)

Saving a `documents.document` through the editor callback (`onlyoffice_odoo/controllers/main.py::editor_callback`):

1. `document.with_user(user).write({"name", "datas", "mimetype"})` (20: `"raw"` with the downloaded bytes) — Documents
   creates a fresh attachment.
2. Increment `oo_attachment_version` on the attachment that was edited (field defined in
   `onlyoffice_odoo_documents/models/ir_attachment.py`, default 1).
3. Rename the attachment that still carries the old version number to `"name (N).ext"` (sudo) — it becomes a read-only
   history version (`get_documents_permissions` forces view mode when the attachment is not the document's current one).

Keep this flow intact when touching the callback; version history in the UI depends on it. The share-link callback in
the documents module writes the document without the version bookkeeping — check both when changing behavior.

## Pitfalls

- Filenames go through `OnlyofficeConnector.filter_xss` before entering editor configs.
- Sanitize generated filenames: `re.sub(r"[<>:'/\\|?*\x00-\x1f]", " ", name)` (templates fill flow).
- The editor document `key` must change when content changes (`id + checksum`); a stale key makes the Document Server
  serve a cached copy. The preview uses a timestamp key because it is read-only.
- Binary field values read via ORM come back as base64 `bytes` (17-19) or a `BinaryValue` (20, use `.content`); get raw
  bytes before processing with pdf/zip tools (`pdf_utils.is_pdf_form` expects raw bytes).
- Docbuilder/converter results are downloaded from Document Server URLs — always through `onlyoffice_request` so the
  inner URL and certificate settings apply.
