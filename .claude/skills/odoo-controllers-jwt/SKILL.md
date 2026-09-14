---
name: odoo-controllers-jwt
description:
  Patterns for Odoo HTTP controllers, route auth types, JSON vs HTTP routes, CSRF/CORS, the token types used in the
  ONLYOFFICE modules, and outgoing requests to the ONLYOFFICE Document Server (editor callback, converter, docbuilder).
  Use when adding or changing routes, callbacks, tokens, or server-to-server communication.
---

# Controllers, Routes and JWT

## Route basics (valid for 17/18/19)

```python
from odoo import http
from odoo.http import request

class MyController(http.Controller):
    # JSON route: body and result are JSON, called from JS via rpc/orm
    @http.route("/my/endpoint", auth="user", methods=["POST"], type="json", csrf=False)
    def my_json(self, some_id=None):
        return {"ok": True}

    # HTTP route: returns a Response (file, page, redirect)
    @http.route("/my/file/<int:rec_id>", auth="public", type="http")
    def my_file(self, rec_id, token=None):
        return request.make_response(data, headers=[...])
```

Rules of thumb:

- `auth="user"` — logged-in users only. Use for UI-facing endpoints.
- `auth="public"` — anyone, including the Document Server. Every public route in this repo MUST verify a token before
  touching data.
- `type="json"` for JS clients; `type="http"` for files/pages and for endpoints the Document Server calls (editor
  callback, docbuilder/converter downloads — it does not speak JSON-RPC). The one exception is `evaluate_formulas_batch`
  (documents module), a `type="json"` route called by the editor sandbox with a hand-built JSON-RPC body, `cors="*"` and
  `methods=["POST", "OPTIONS"]`.
- `csrf=False` only on routes called by external services (callbacks) or from outside the Odoo web client.
- `website=True` on editor pages so the frontend layout/session helpers work for public users.
- Return `request.not_found()` for missing records; raise `Forbidden` / `AccessError` for auth problems. Do not leak
  internals in error messages.
- Several routes in this repo return `json.dumps(result)` (a JSON string) from a `type="json"` route and the JS does
  `JSON.parse` — keep the existing contract of a route when you change it.

## Token types used in this repo

| Token                                   | Secret                                 | Payload                               | Where                                                                                                                                                        |
| --------------------------------------- | -------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Document Server JWT (outgoing)          | `config_utils.get_jwt_secret`          | the editor config / request body      | `root_config["token"]`, converter and docbuilder bodies (`token`), plus header `<jwt_header>: Bearer <jwt of {"payload": body}>`                             |
| Document Server JWT (incoming)          | same                                   | callback body                         | editor callbacks: body `token` or the configured header; decode with `jwt_utils.decode_token` and use the decoded body (`payload` key) not the raw one       |
| Internal user token `oo_security_token` | `config_utils.get_internal_jwt_secret` | `{"id": user_id}`                     | query string of every URL the Document Server downloads or posts to (`file/content`, `editor/callback`, `template/download`, docbuilder callbacks)           |
| Internal formula token `jwt_token`      | internal secret                        | `{"uid": user_id, "document_id": id}` | `evaluate_formulas_batch`; the route checks that `document_id` in the token matches the request                                                              |
| Docbuilder cache key                    | none (random `uuid4().hex`)            | —                                     | `/onlyoffice/documents/docbuilder_callback/<token>` and `docbuilder_file/<token>`: a lookup key for an `ir.attachment` cache row, despite the parameter name |

All JWTs are HS256 with a 24 h expiry (`jwt_utils.encode_payload` adds `iat`/`exp`). `is_jwt_enabled(env)` is simply "a
Document Server secret is configured"; internal tokens are always used.

Resolve internal tokens with `OnlyofficeConnector.get_user_from_token(token)` (raises `Forbidden` when missing) and run
all ORM access with `.with_user(user)` — never with sudo-by-default. The templates controller keeps its own copy of
`get_user_from_token`; keep both in sync.

## Calling the Document Server

Always go through helpers from `onlyoffice_odoo.controllers.main`:

```python
from odoo.addons.onlyoffice_odoo.controllers.main import onlyoffice_request, onlyoffice_urlopen

response = onlyoffice_request(url=url, method="post", opts={"json": payload, "headers": headers}, env=env)
```

- `onlyoffice_request` replaces the public URL with the inner one, honours "disable certificate verification", logs the
  call, uses timeout 120 s (`opts["timeout"]`), calls `raise_for_status()` and re-raises as
  `requests.exceptions.RequestException` with context.
- Pass `env=self.env` when there is no HTTP request context (report rendering, cron, shell, tests).
- Build callback URLs from `config_utils.get_base_or_odoo_url(env)`, never from `request.httprequest.host`.
- Use `url_utils.replace_public_url_to_internal(env, url)` on any URL you got back from the Document Server before
  downloading from it (the helpers already do this for the URL you pass them).
- Allowed exceptions to the rule: the oforms gallery API (`OnlyOfficeOFormsDocumentsController`), downloading a gallery
  form in `post_file_create`, and `validation_utils` (it must test the URLs the user just typed, before they are saved).
  Everything that talks to the Document Server uses the helpers.

### Editor save callback (reference)

`POST /onlyoffice/editor/callback/<attachment_id>` (base) and `POST /onlyoffice/documents/share/callback/...`
(documents):

- status 1 — editing in progress; 2 — must save; 3 — save error, force save; 4 — closed without changes; 6/7 —
  force-save variants.
- On 2/3: `url_utils.replace_public_url_to_internal(body["url"])`, download, write the file to the attachment/document,
  answer `{"error": 0}` (HTTP 200). Any exception → `{"error": 1, "message": …}` with HTTP 500. The Document Server
  retries on non-zero errors.
- Never answer 200 with `error: 0` when nothing was saved.

### Converter (`<docserver>converter?shardkey=<key>`)

Use `onlyoffice_odoo/utils/conversion_utils.py`:

```python
body = conversion_utils.build_conversion_body(source_url, "pdf", "pdf", extra_options={"pdf": {"form": True}}, region=None)
body, headers = conversion_utils.sign_conversion_request(env, body, jwt_secret, jwt_header)
response = onlyoffice_request(url=f"{docserver_inner}converter?shardkey={body['key']}", method="post",
                              opts={"data": json.dumps(body), "headers": headers}, env=env)
result = conversion_utils.parse_conversion_response(response)   # {"fileUrl": ...} or {"error": code, "message": ...}
```

- `source_url` must be reachable by the Document Server: an Odoo public route with `oo_security_token`
  (`/onlyoffice/file/content/<id>` or `/onlyoffice/template/download/<id>`).
- `extra_options={"async": False}` for synchronous conversion; `region` for locale-dependent formats.
- Users: settings validation (base), `file/convert` (documents), PDF → PDF-form (templates). Add new options here, not
  in callers.

### Docbuilder (`<docserver>docbuilder`)

Pattern used by templates (fill, get_keys) and documents (spreadsheet export/insert):

1. Odoo POSTs `{"async": False, "url": <public Odoo callback URL>}`. When a secret is set, add `token` to the body and
   the `Bearer` header (payload wrapper) — see `keys_utils.fetch_field_keys` for the compact version.
2. The Document Server GETs the callback URL and receives a `.docbuilder` script as `text/plain` (attachment
   `Content-Disposition`). The script starts with
   `builder.OpenFile("<public Odoo download URL with oo_security_token>")` and ends with `builder.SaveFile(...)` /
   `builder.CloseFile()`.
3. The response is `{"urls": {"<filename>": "<url>"}}` or `{"error": code}` (−1 unknown, −2 timeout, −3 generation
   error, −4 download error, −6 result database error, −8 invalid token — see `get_docbuilder_error`).
4. Odoo downloads each URL through `onlyoffice_request`.

Rules: the callback is a **second, independent HTTP request** — it may land on another worker, so pass everything it
needs in the URL (templates) or persist it (documents cache in `ir.attachment`, committed). Anything interpolated into
the script text is code: pass data as `json.dumps(...)` literals and sanitise file names.

## Inheriting controllers

Extend an existing controller class to change or add routes:

```python
from odoo.addons.onlyoffice_odoo.controllers.main import OnlyofficeConnector

class MyConnector(OnlyofficeConnector):
    @http.route("/onlyoffice/editor/get_config", auth="user", methods=["POST"], type="json", csrf=False)
    def get_config(self, document_id=None, attachment_id=None, access_token=None):
        config = super().get_config(document_id=document_id, attachment_id=attachment_id, access_token=access_token)
        config["extra"] = ...
        return config
```

`onlyoffice_odoo_documents` (`OnlyofficeDocuments_Inherited_Connector`) and `onlyoffice_odoo_templates`
(`Onlyoffice_Inherited_Connector`) both do this; they also add plain `http.Controller` classes for their own routes, and
documents subclasses the Enterprise `ShareRoute`. A bare `@http.route()` reuses the parent's route settings when
overriding an existing route.

## Checklist for a new/changed route

- [ ] Correct `auth` and `type`; `csrf=False` only when required; `cors` only for sandbox-called routes
- [ ] Public route validates `oo_security_token` (or the formula token) and, when enabled, the Document Server JWT
- [ ] ORM calls run as the resolved user (`with_user`), sudo only with a reason
- [ ] Attachment access checked: `validate_access` + the version's access API (17:
      `check_access_rights`/`check_access_rule`; 18/19: `has_access`/`check_access`)
- [ ] URLs given to the Document Server built from `get_base_or_odoo_url` and reachable from its network
- [ ] Errors logged (`_logger.warning` for expected rejections, `_logger.error` for aborts), safe responses returned
- [ ] Works when Odoo and Document Server are in Docker (inner URLs) and with JWT on and off
- [ ] Duplicated paths (share callback, report `fill_template`, templates `get_user_from_token`) updated together
