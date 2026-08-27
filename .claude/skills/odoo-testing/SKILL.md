---
name: odoo-testing
description:
  Writing and maintaining tests for the ONLYOFFICE Odoo modules - TransactionCase, HttpCase, tags, mocking Document
  Server calls, and the optional live Document Server test setup. Use when adding tests, fixing broken tests, or
  verifying a bug fix.
---

# Testing

## Existing tests

`onlyoffice_odoo/tests/` covers utils (config, jwt, file, url, validation), models, and HTTP controllers. Use these
files as style references.

## Test class choice

| Class             | Use for                                                                     |
| ----------------- | --------------------------------------------------------------------------- |
| `TransactionCase` | ORM logic, utils, models — one rollback per test                            |
| `HttpCase`        | Real HTTP calls to controller routes (`self.url_open`, `self.authenticate`) |

Standard tagging in this repo:

```python
from odoo.tests import tagged
from odoo.tests.common import HttpCase

@tagged("post_install", "-at_install")
class TestSomething(HttpCase):
    ...
```

## Controller test rules

- Create a dedicated test user with a known password; do not rely on `admin` (see `test_controllers.py::setUp`).
- Version note: on Odoo 19, `groups_id` passed to `res.users.create()` is ignored — create the user first, then add
  groups via `group.write({"users": [(4, user.id)]})`. On 17/18 the `groups_id` key in create vals still works.
- Disable JWT in setup unless the test targets JWT itself: `config_utils.set_jwt_secret(self.env, "")`.
- Public routes: test both the happy path (valid `oo_security_token`) and rejection without a token.
- JSON routes: post with
  `self.url_open(url, data=json.dumps({"jsonrpc": "2.0", "params": {...}}), headers={"Content-Type": "application/json"})`.

## Mocking the Document Server

Unit tests must not hit a real Document Server. Patch the request helper:

```python
from unittest.mock import patch

with patch("odoo.addons.onlyoffice_odoo.controllers.main.onlyoffice_request") as m:
    m.return_value.status_code = 200
    m.return_value.content = b"%PDF-..."
    m.return_value.json.return_value = {"urls": {"file.pdf": "http://ds/cache/file.pdf"}}
    # run the code under test
```

Note: Odoo's test framework blocks non-localhost HTTP for classes tagged `standard` (which is added automatically). Mock
instead of fighting this.

## Live Document Server tests (optional, not currently in this repo)

There is no live-Document-Server test file or CI job in this repo today — `.github/workflows/test.yml` only spins up
postgres and runs the standard suite for `onlyoffice_odoo` (the other two modules are excluded there). If a test
genuinely needs a real Document Server:

- Gate it behind an explicit opt-in (e.g. an env var you introduce and document), so it is skipped by default and in CI.
- Tag it with `-standard` so Odoo's external-request block does not apply; add a distinct extra tag so it can be
  selected on its own.
- Pass `env=self.env` explicitly to `onlyoffice_request(...)` because there is no HTTP request context inside tests.
- Document the new env var and CI wiring in the same PR, and update this skill once the pattern actually exists in the
  repo.

## JWT test helper

```python
from odoo.addons.onlyoffice_odoo.utils import jwt_utils, config_utils

token = jwt_utils.encode_payload(self.env, {"id": self.env.user.id},
                                 config_utils.get_internal_jwt_secret(self.env))
```

## Checklist for a bug fix

- [ ] A test reproduces the bug and fails before the fix
- [ ] Test lives in the module that owns the fixed code
- [ ] No live network calls in standard tests
- [ ] Existing tests still pass (`--test-tags` for the touched module)
- [ ] Consider whether the same test is needed on the other Odoo-version code lines
