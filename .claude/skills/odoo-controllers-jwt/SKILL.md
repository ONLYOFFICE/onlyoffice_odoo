---
name: odoo-controllers-jwt
description:
  Patterns for Odoo HTTP controllers, route auth types, JSON vs HTTP routes, CSRF, JWT signing/validation, and outgoing
  requests to the ONLYOFFICE Document Server. Use when adding or changing routes, callbacks, tokens, or server-to-server
  communication.
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
- `type="json"` for JS clients; `type="http"` for files/pages and for endpoints the Document Server calls (it does not
  speak JSON-RPC).
- `csrf=False` only on routes called by external services (callbacks).
- Return `request.not_found()` for missing records; raise `Forbidden` / `AccessError` for auth problems. Do not leak
  internals in error messages.

## The two JWT layers in this repo

1. **Document Server JWT** (`jwt_utils` with the configured secret).
   - Outgoing: sign the editor config (`root_config["token"]`) and docbuilder payloads; also send the header
     `<jwt_header>: Bearer <jwt of {"payload": body}>`.
   - Incoming: callbacks and file downloads carry a token in the body or in the configured header. Decode with
     `jwt_utils.decode_token`; use the decoded body, not the raw one.
2. **Internal JWT** (`config_utils.get_internal_jwt_secret`).
   - `oo_security_token` in URLs identifies the Odoo user on public routes.
   - Resolve with `get_user_from_token(token)` and run all ORM access with `.with_user(user)` — never with
     sudo-by-default.

Both use HS256 with 24h expiry (`jwt_utils.encode_payload`).

## Calling the Document Server

Always go through helpers from `onlyoffice_odoo.controllers.main`:

```python
from odoo.addons.onlyoffice_odoo.controllers.main import onlyoffice_request

response = onlyoffice_request(url=url, method="post", opts={"json": payload, "headers": headers})
```

- Pass `env=self.env` when there is no HTTP request context (tests, cron).
- Convert public URLs to inner ones for server-to-server calls: `url_utils.replace_public_url_to_internal(env, url)`.
- Build callback URLs from `config_utils.get_base_or_odoo_url(env)`, never from `request.httprequest.host`.
- Set explicit timeouts for any new direct HTTP call; log the URL and status on failure with `_logger.warning/error`.

## Save callback contract (reference)

`POST /onlyoffice/editor/callback/<attachment_id>`:

- status 1 — editing in progress; 2 — must save; 3 — save error, force save; 4 — closed without changes; 6/7 —
  force-save variants.
- On 2/3: download `body["url"]` (converted to inner URL), write the file to the attachment, answer `{"error": 0}`. Any
  exception → `{"error": 1}` with HTTP 500. The Document Server retries on non-zero errors.

## Inheriting controllers

Extend an existing controller class to change or add routes:

```python
from odoo.addons.onlyoffice_odoo.controllers.main import OnlyofficeConnector

class MyConnector(OnlyofficeConnector):
    @http.route()  # keep parent route params
    def get_config(self, **kw):
        return super().get_config(**kw)
```

`onlyoffice_odoo_documents` and `onlyoffice_odoo_templates` both do this — follow their style. A bare `@http.route()`
reuses the parent's route settings.

## Checklist for a new/changed route

- [ ] Correct `auth` and `type`; `csrf=False` only when required
- [ ] Public route validates `oo_security_token` and/or Document Server JWT
- [ ] ORM calls run as the resolved user (`with_user`), sudo only with a reason
- [ ] Attachment access checked: `validate_access` + the version's access API (17:
      `check_access_rights`/`check_access_rule`; 18/19: `has_access`/`check_access`)
- [ ] Errors logged, safe responses returned
- [ ] Works when Odoo and Document Server are in Docker (inner URLs)
