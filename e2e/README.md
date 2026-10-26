# End-to-end tests (Playwright)

Browser tests of the `onlyoffice_odoo` connector, the `onlyoffice_odoo_templates` and the `onlyoffice_odoo_documents`
modules against a **live** ONLYOFFICE Docs (Developer Edition: the template editor needs its Automation API, the
spreadsheet features of Documents its docbuilder service). CI runs them in `.github/workflows/e2e.yml` on every push and
pull request, in the runtime model of `test.yml`: the OCA Odoo image as the job container, PostgreSQL and the Document
Server as `services`. Odoo and the browser run inside the job container, so the Document Server is
`http://documentserver/` for both and reaches Odoo at the job container address.

| Spec                      | Scenario                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/auth.setup.ts`     | Logs in as `admin`; the session is reused by the other projects.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `tests/settings.spec.ts`  | Unreachable Docs address → validation error, nothing stored. Real address → validation passes, settings stored.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tests/editor.spec.ts`    | For docx, xlsx, pptx: post the file to a Discuss channel, "Open in ONLYOFFICE", type, leave → the attachment is saved and contains the typed text. Also for docx in "Open file in the same tab" mode. An rtf (view-only format) opens read-only without a save callback.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `tests/templates.spec.ts` | With the "Employee" demo template: print from a form (form fields hold the employee's data), from the list (ZIP), and through the `onlyoffice-pdf` report; "Disable form fields after printing" leaves no form fields; Preview; a blank template opens in the editor; a plain PDF becomes a PDF form; the form gallery (API stubbed) and the Settings export create templates.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `tests/access.spec.ts`    | A zip in Discuss has no "Open in ONLYOFFICE" button. Another user opening the editor link of a file in a private chat gets 403.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tests/documents.spec.ts` | Enterprise Documents: "Create with ONLYOFFICE" in a folder, type, close → saved, the previous version kept as `<name> (1).docx`; "Open in ONLYOFFICE" from the app; a colleague's ONLYOFFICE role (commenter → comments only, none → 403); a visitor with an edit link opens the file from the share page and saves through the share callback; "Convert with ONLYOFFICE" docx → PDF saved in the folder; an Odoo Spreadsheet converted to XLSX with live `ODOO_LIST` formulas (native export + docbuilder) whose values Odoo computes when the editor opens it; an Odoo list inserted into an XLSX through docbuilder; blank xlsx/pptx/pdf and a form of the gallery (API stubbed) created with ONLYOFFICE; "Create & Set Permissions" opens the share panel; the editor in the same tab; conversion downloaded instead of saved; an Odoo Spreadsheet made by Odoo opened as a static XLSX copy; a pivot inserted through docbuilder and a list inserted from the ONLYOFFICE tab of the spreadsheet selector; ONLYOFFICE Desktop Editors mode (redirect to Documents, sign-in of the desktop app). |
| `tests/share.spec.ts`     | Links of the Documents app generated through Share → "Anyone with the link" → Copy Link. A visitor opens document links of the roles view, commenter, custom_filter (xlsx) and form_filling (pdf) — the mapping of every role is unit-tested from the share page and gets that role; `demo` follows a view and an edit link and opens the document in ONLYOFFICE from the Documents app; a folder shared with view/edit opens its documents with that right for a visitor and for `demo`; a document hidden from the link is neither listed nor opened. Tests of known bugs (`knownBug`) expect the correct rights and are marked as failing; `E2E_STRICT=1` runs them as plain tests.                                                                                                                                                                                                                                                                                                                                                                                                              |

Projects run in a chain (`login` → `settings` → `editor`, `templates`, `documents` with `share.spec.ts`) with one
worker: both need the Document Server connected by the settings test. One Document Server serves both modules; the one
of the `test.yml` templates job cannot be reused, because a service lives only as long as its job.

**Save timing.** The task requires the file to be saved 5 s after leaving the editor. The Document Server assembles the
file `savetimeoutdelay` (5 s) after the last user leaves: 6–7 s normally for every leave path (closing the tab, going
back in "same tab" mode), but over 20 s in CI and up to about a minute locally when the Docs container is under load. So
`E2E_SAVE_GRACE_MS` (default 55 s) is added to the check, and the measured latency is recorded as the `save-latency`
annotation in the HTML report. `E2E_SAVE_GRACE_MS=0` makes the check strict.

## Enterprise addons

`onlyoffice_odoo_documents` depends on Odoo Enterprise (`documents`, `documents_spreadsheet`, and through them
`spreadsheet_edition`, `web_enterprise`).

- Locally the compose stack mounts Odoo Enterprise 18.0 from `enterprise-18.0/` next to the repository
  (`e2e/../../enterprise-18.0`, e.g. `odoo/_18/enterprise-18.0` for the repository `odoo/_18/onlyoffice_odoo`) at
  `/mnt/enterprise`; `ENTERPRISE_DIR=/path/to/enterprise` mounts another directory. Any checkout of the series of
  `onlyoffice_odoo/__manifest__.py` will do. The Odoo container stops with an error when one of the four addons above is
  not there (Odoo itself would only skip `onlyoffice_odoo_documents` with a warning).
- In CI the jobs of `onlyoffice_odoo_documents` (`test.yml` jobs `onlyoffice_odoo_documents` and `coverage`, `e2e.yml`)
  run an action of `ONLYOFFICE/onlyoffice_odoo_test` on Gitea and are skipped on GitHub. On GitHub the job
  `playwright (without Documents)` of `e2e.yml` installs only `onlyoffice_odoo` and `onlyoffice_odoo_templates` and runs
  the other tests with `E2E_WITHOUT_DOCUMENTS=1`: the `documents` project (`documents.spec.ts`, `share.spec.ts`) and the
  Documents tests of `templates.spec.ts` are left out. The variable works the same against a local Odoo without
  Documents.

## Run locally

Requirements: Docker Desktop (or Docker with Compose v2) running, Node.js 20+, Odoo Enterprise 18.0 next to the
repository (see above), ports 8069 and 8080 free (stop a developer Odoo on 8069 first).

```bash
cd e2e
npm run setup   # once: npm ci + Chromium for Playwright (Linux: also `npx playwright install-deps chromium`)
npm run e2e     # starts the stack, runs the tests, stops the stack
```

`npm run e2e` = `npm run stack:up` (PostgreSQL, Document Server, Odoo 18 with `hr`, then `onlyoffice_odoo`,
`onlyoffice_odoo_templates` and `onlyoffice_odoo_documents` installed in database `e2e`; `hr` goes first so that the
"Employee" demo template is created) → `npm test` → `npm run stack:down`. When a test fails the stack stays up for
debugging: `npm run report` opens the HTML report with traces, `docker compose logs web` shows Odoo,
`npm run stack:down` removes everything.

The local stack (`docker-compose.yml`): `postgres:15`, `odoo:18.0` + `pyjwt` (`odoo/Dockerfile`, addons path
`/mnt/extra-addons,/mnt/enterprise` from `odoo/odoo.conf`) on port 8069 with the three ONLYOFFICE modules, `hr` and the
Enterprise Documents app installed, and `onlyoffice/documentserver-de` (JWT enabled) on port 8080. The settings test
stores: Docs address `http://localhost:8080/`, inner address `http://documentserver/`, Odoo address for Docs
`http://web:8069/`. Fixtures are the blank templates in `onlyoffice_odoo/static/assets/document_templates/en-US/`.

To run against your own Odoo + Document Server instead, skip the `stack:*` scripts and set `E2E_ODOO_URL`,
`E2E_DS_PUBLIC_URL`, `E2E_DS_INNER_URL`, `E2E_ODOO_INNER_URL` (`helpers/env.ts`); the Document Server must use the JWT
secret from `helpers/env.ts`, and the tests overwrite the ONLYOFFICE settings of that database.

Selectors come from Odoo 18 `mail` (`.o-mail-Composer`, `.o-mail-Message`, `.o-mail-AttachmentCard`) and from the
Document Server (`iframe[name="frameEditor"]`, `#toolbar`, `#editor_sdk`); typing goes through the editor canvas at
fixed points of the 1440×900 viewport (`helpers/editor.ts`). Re-check them when porting to 19.
