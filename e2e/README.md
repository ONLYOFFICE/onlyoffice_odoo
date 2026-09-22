# End-to-end tests (Playwright)

Browser tests of the `onlyoffice_odoo` connector against a **live** ONLYOFFICE Docs. CI runs them in
`.github/workflows/e2e.yml` on every push and pull request, in the runtime model of `test.yml`: the OCA Odoo image as
the job container, PostgreSQL and the Document Server as `services`. Odoo and the browser run inside the job container,
so the Document Server is `http://documentserver/` for both and reaches Odoo at the job container address.

| Spec                     | Scenario                                                                                                                                                                                                                                                                 |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/auth.setup.ts`    | Logs in as `admin`; the session is reused by the other projects.                                                                                                                                                                                                         |
| `tests/settings.spec.ts` | Unreachable Docs address → validation error, nothing stored. Real address → validation passes, settings stored.                                                                                                                                                          |
| `tests/editor.spec.ts`   | For docx, xlsx, pptx: post the file to a Discuss channel, "Open in ONLYOFFICE", type, leave → the attachment is saved and contains the typed text. Also for docx in "Open file in the same tab" mode. An rtf (view-only format) opens read-only without a save callback. |
| `tests/access.spec.ts`   | A zip in Discuss has no "Open in ONLYOFFICE" button. Another user opening the editor link of a file in a private chat gets 403.                                                                                                                                          |

Projects run in a chain (`login` → `settings` → `editor`) with one worker: the editor tests need the Document Server
connected by the settings test.

**Save timing.** The task requires the file to be saved 5 s after leaving the editor. The Document Server assembles the
file `savetimeoutdelay` (5 s) after the last user leaves: 6–7 s normally for every leave path (closing the tab, going
back in "same tab" mode), but over 20 s in CI and up to about a minute locally when the Docs container is under load. So
`E2E_SAVE_GRACE_MS` (default 55 s) is added to the check, and the measured latency is recorded as the `save-latency`
annotation in the HTML report. `E2E_SAVE_GRACE_MS=0` makes the check strict.

## Run locally

Requirements: Docker Desktop (or Docker with Compose v2) running, Node.js 20+, ports 8069 and 8080 free (stop a
developer Odoo on 8069 first).

```bash
cd e2e
npm run setup   # once: npm ci + Chromium for Playwright (Linux: also `npx playwright install-deps chromium`)
npm run e2e     # starts the stack, runs the tests, stops the stack
```

`npm run e2e` = `npm run stack:up` (PostgreSQL, Document Server, Odoo 17 with `onlyoffice_odoo` installed in database
`e2e`) → `npm test` → `npm run stack:down`. When a test fails the stack stays up for debugging: `npm run report` opens
the HTML report with traces, `docker compose logs web` shows Odoo, `npm run stack:down` removes everything.

The local stack (`docker-compose.yml`): `postgres:13`, `odoo:17` + `pyjwt` (`odoo/Dockerfile`) on port 8069 and
`onlyoffice/documentserver` (JWT enabled) on port 8080. The settings test stores: Docs address `http://localhost:8080/`,
inner address `http://documentserver/`, Odoo address for Docs `http://web:8069/`. Fixtures are the blank templates in
`onlyoffice_odoo/static/assets/document_templates/en-US/`.

To run against your own Odoo + Document Server instead, skip the `stack:*` scripts and set `E2E_ODOO_URL`,
`E2E_DS_PUBLIC_URL`, `E2E_DS_INNER_URL`, `E2E_ODOO_INNER_URL` (`helpers/env.ts`); the Document Server must use the JWT
secret from `helpers/env.ts`, and the tests overwrite the ONLYOFFICE settings of that database.

Selectors come from Odoo 17 `mail` (`.o-mail-Composer`, `.o-mail-Message`, `.o-mail-AttachmentCard`) and from the
Document Server (`iframe[name="frameEditor"]`, `#toolbar`, `#editor_sdk`); typing goes through the editor canvas at
fixed points of the 1440×900 viewport (`helpers/editor.ts`). Re-check them when porting to 18/19.
