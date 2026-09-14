---
name: odoo-testing
description:
  Writing and maintaining tests for the ONLYOFFICE Odoo modules - what exists per module, CI setup and its limits,
  TransactionCase/HttpCase patterns, tags, mocking Document Server and docbuilder calls, and the optional live Document
  Server test setup. Use when adding tests, fixing broken tests, or verifying a bug fix.
---

# Testing

## State of the test suites

| Module                      | Tests                                                                                                                                                                                                                                                   | In CI                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| `onlyoffice_odoo`           | `tests/test_config_utils.py`, `test_jwt_utils.py`, `test_url_utils.py`, `test_file_utils.py`, `test_validation_utils.py`, `test_models.py` (`onlyoffice.odoo`, `res.config.settings`), `test_controllers.py` (`HttpCase`, all base routes). ~130 tests. | yes, coverage `fail_under=60` |
| `onlyoffice_odoo_documents` | none                                                                                                                                                                                                                                                    | excluded (needs Enterprise)   |
| `onlyoffice_odoo_templates` | `tests/test_field_keys_cache.py` (`TransactionCase`, no tags; patches `pdf_utils.is_pdf_form` and `OnlyOfficeTemplate._fetch_field_keys`)                                                                                                               | excluded                      |

Every new `test_*.py` must be imported from the module's `tests/__init__.py` or the runner will not see it.

CI (`.github/workflows/test.yml`): OCA container `py3.10-odoo17.0` + postgres, `INCLUDE=onlyoffice_odoo`,
`EXCLUDE=onlyoffice_odoo_documents,onlyoffice_odoo_templates`; it creates stub manifests for `documents` and
`documents_spreadsheet` so the addons path resolves, runs `oca_run_tests` and `coverage report --fail-under=60`
(`.coveragerc`: `source = onlyoffice_odoo`, tests and manifests omitted). Lint runs in `lint.yml` (pre-commit, ruff,
pylint-odoo). Tests for the documents and templates modules therefore run only locally — say so in the PR and describe
the manual check.

Local run (from `CONTRIBUTING.md`; confirm the database name with the user first):

```bash
docker exec <container> odoo -d <db> --test-enable --stop-after-init -i onlyoffice_odoo --log-level=test \
  --db_host=db --db_port=5432 --db_user=odoo --db_password=odoo
# narrower: --test-tags /onlyoffice_odoo_templates  or  --test-tags :TestOnlyofficeControllers
```

Use these files as style references: `test_controllers.py` for HTTP tests, `test_validation_utils.py` for util tests,
`test_field_keys_cache.py` for patching model internals.

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

- Create a dedicated test user with a known password; do not rely on `admin` (see `test_controllers.py::setUp`:
  `groups_id` with `base.group_user` + `base.group_system`).
- Version note: on Odoo 19, `groups_id` passed to `res.users.create()` is ignored — create the user first, then add
  groups via `group.write({"users": [(4, user.id)]})`. On 17/18 the `groups_id` key in create vals still works.
- Disable JWT in setup unless the test targets JWT itself: `config_utils.set_jwt_secret(self.env, "")`.
- Public routes: test both the happy path (valid `oo_security_token`) and rejection without a token. Callback routes
  answer JSON `{"error": 1}` with HTTP 500 on rejection — assert both.
- JSON routes: post with
  `self.url_open(url, data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {...}}), headers={"Content-Type": "application/json"})`;
  unauthenticated JSON-RPC answers HTTP 200 with an `error` key, not 401/403.
- Routes that return `json.dumps(result)` from a `type="json"` method: the JSON-RPC `result` is a string — parse it.
- Templates: group membership matters (`group_onlyoffice_odoo_templates_user` / `_admin`); give the test user the group
  you are testing.

## Mocking the Document Server

Unit tests must not hit a real Document Server. Patch the request helper where it is **used**:

```python
from unittest.mock import patch

with patch("odoo.addons.onlyoffice_odoo.controllers.main.onlyoffice_request") as m:
    m.return_value.status_code = 200
    m.return_value.content = b"%PDF-..."
    m.return_value.json.return_value = {"urls": {"file.pdf": "http://ds/cache/file.pdf"}}
    # run the code under test
```

Because the other modules import the helper by name, patch their module path instead:
`odoo.addons.onlyoffice_odoo_templates.controllers.controllers.onlyoffice_request`,
`odoo.addons.onlyoffice_odoo_templates.models.onlyoffice_odoo_templates.onlyoffice_request`,
`odoo.addons.onlyoffice_odoo_templates.utils.keys_utils.onlyoffice_request`,
`odoo.addons.onlyoffice_odoo_documents.controllers.controllers.onlyoffice_request`, and `onlyoffice_urlopen` in
`controllers.main` for the save callback.

Higher-level seams that avoid HTTP entirely:

- templates: `patch.object(OnlyOfficeTemplate, "_fetch_field_keys", return_value=[...])` and
  `patch("odoo.addons.onlyoffice_odoo_templates.utils.pdf_utils.is_pdf_form", return_value=True)` so `create()` does not
  call the converter;
- templates fill: `patch.object(OnlyofficeTemplate_Connector, "fill_template", return_value={"a.pdf": "http://ds/a"})`;
- documents convert: patch `conversion_utils.parse_conversion_response` or `onlyoffice_request` in the documents
  controller module;
- documents spreadsheet: patch `SpreadsheetDocBuilder._call_docbuilder`; the formula evaluator can be exercised directly
  with a hand-built snapshot dict (`evaluate_single_formula(snapshot, "=ODOO_LIST(1,1,\"name\")")`), it needs a
  `request` only for the `read_group` cache — run it inside an `HttpCase` request or patch `_safe_read_group`.
- the oforms gallery proxy uses plain `requests` — patch `requests.get` in `controllers.main` for those routes.

Note: Odoo's test framework blocks non-localhost HTTP for classes tagged `standard` (added automatically). Mock instead
of fighting this.

## Live Document Server tests (optional, not currently in this repo)

There is no live-Document-Server test file or CI job in this repo today. If a test genuinely needs a real Document
Server:

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
# formula token used by /onlyoffice/documents/evaluate_formulas_batch
formula_token = jwt_utils.encode_payload(self.env, {"uid": self.env.user.id, "document_id": doc.id},
                                         config_utils.get_internal_jwt_secret(self.env))
```

## Testing Enterprise-dependent code without Enterprise

CI has only stub manifests for `documents`/`documents_spreadsheet`, so tests for `onlyoffice_odoo_documents` cannot run
there. Options: keep pure-Python parts testable in isolation (`conversion_utils`, the formula evaluator with a fake
snapshot), and run the full module tests locally against a database with Enterprise installed. Do not add `documents` to
the base module's test dependencies.

## Checklist for a bug fix

- [ ] A test reproduces the bug and fails before the fix
- [ ] Test lives in the module that owns the fixed code and is imported in `tests/__init__.py`
- [ ] No live network calls in standard tests (Document Server, docbuilder, converter, oforms all mocked)
- [ ] Existing tests still pass (`--test-tags` for the touched module); coverage for `onlyoffice_odoo` stays ≥ 60%
- [ ] Consider whether the same test is needed on the other Odoo-version code lines
