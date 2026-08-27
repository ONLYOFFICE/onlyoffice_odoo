---
name: odoo-attachments-files
description:
  Working with ir.attachment, binary fields, base64 data, file streaming, mimetypes, access tokens, and file format
  checks in the ONLYOFFICE Odoo modules. Use when reading, writing, versioning, or serving files.
---

# Attachments and Files

## ir.attachment essentials

| Field                  | Meaning                                               |
| ---------------------- | ----------------------------------------------------- |
| `datas`                | base64 string of the content (ORM level)              |
| `raw`                  | raw bytes (preferred for writes, no base64 step)      |
| `name`                 | filename with extension                               |
| `mimetype`             | set it explicitly when writing new content            |
| `checksum`             | changes with content; part of the editor document key |
| `res_model` / `res_id` | owner record                                          |
| `access_token`         | share token, checked by `validate_access`             |

Write patterns:

```python
attachment.write({"raw": file_bytes, "mimetype": guess_type(url)[0]})   # bytes
attachment.write({"datas": base64.b64encode(file_bytes)})               # base64
```

Do not mix them up: `raw` = bytes, `datas` = base64. A wrong choice corrupts the file silently.

## Serving file content

Stream instead of loading into memory:

```python
stream = request.env["ir.binary"]._get_stream_from(attachment, "datas", None, "name", None)
return stream.get_response(as_attachment=True, max_age=None)
```

For small generated content use `request.make_response(content, headers)` with `Content-Type`, `Content-Length`,
`Content-Disposition`, and `X-Content-Type-Options: nosniff` for downloads.

## Access checks (this repo's contract)

Before returning any file:

1. `attachment.validate_access(access_token)` — share-token check.
2. ORM access check for `"read"` (or `"write"` for saves). The API name is version-specific:
   - 17: `attachment.check_access_rights(op)` / `check_access_rule(op)`
   - 18/19: `attachment.has_access(op)` / `attachment.check_access(op)`
3. For `documents.document` owners: lock check + the same version's rule check for `"read"`.
4. On public routes: resolve the user from `oo_security_token` first and use `with_user(user)` for all of the above.

## File format logic

`onlyoffice_odoo/utils/file_utils.py` owns:

- `can_view(name)` / `can_edit(name)` — allowed extension lists
- `get_file_ext(name)` / `get_file_type(name)` — word / cell / slide / pdf
- `get_mime_by_ext(ext)` — mimetype table
- `get_default_file_template(lang, ext)` — blank docx/xlsx/pptx per language from `static/src/assets/new/...`

Add new formats there, never inline in controllers.

## Versioning (documents module)

Saving a `documents.document` through the editor callback:

1. Write new content to the document (creates a fresh attachment).
2. Increment `oo_attachment_version` on the active attachment.
3. Rename the previous attachment to `"name (N).ext"` — it becomes a read-only history version (editor opens it in view
   mode).

Keep this flow intact when touching the callback; version history in the UI depends on it.

## Pitfalls

- Filenames go through `filter_xss` before entering editor configs.
- Sanitize generated filenames: `re.sub(r"[<>:'/\\|?*\x00-\x1f]", " ", name)`.
- The editor document `key` must change when content changes (`id + checksum`); a stale key makes the Document Server
  serve a cached copy.
- Binary field values read via ORM come back as base64 `bytes`; decode before processing with pdf/zip tools.
