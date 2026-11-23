# Maintaining ONLYOFFICE for Odoo

State as of 2026-11-23. This file holds what the code and the rules do not show: what the product is, where it runs,
how it is published, what is unfinished and what is planned. Rules and commands are in `CLAUDE.md`, module internals and
coding rules are in `.claude/skills/`, and the release procedure is in `.claude/skills/release/SKILL.md`.

## 1. What it is

**Odoo addons that run inside Odoo**, not a separate service. This repository holds three addons. They are connected
only through `depends` in their manifests:

| Addon                       | What it does                                                                                                                                                                         | Needs                                                      |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| `onlyoffice_odoo`           | Base connector. Opens attachments (`ir.attachment`) in the ONLYOFFICE editor. Holds the settings, JWT, the save callback and the preview.                                            | Odoo Community                                             |
| `onlyoffice_odoo_documents` | Integration with the Enterprise Documents app: create, share with ONLYOFFICE roles, share links, conversion, Odoo spreadsheets ↔ XLSX with `ODOO_*` formulas, Desktop Editors mode. | **Odoo Enterprise** (`documents`, `documents_spreadsheet`) |
| `onlyoffice_odoo_templates` | Fillable PDF form templates filled with data of Odoo records; the `onlyoffice-pdf` report type. Co-authored with the partner Data Dance s.r.o., who also sends pull requests.        | Odoo Community                                             |

A fourth addon lives in its own repository and is maintained together with these: **`onlyoffice_odoo_dms`**
(`git.onlyoffice.com/ONLYOFFICE/onlyoffice_odoo_dms`, mirrored to `github.com/ONLYOFFICE/onlyoffice_odoo_dms`). It
integrates ONLYOFFICE with the OCA `dms` module and depends on `onlyoffice_odoo` and `dms`. Users open and create files
in DMS directories, and the addon resolves ONLYOFFICE roles per user, per DMS group and per share link. It is
co-authored with Data Dance. Its branches are `develop` and `17.0` (released, 1.0.3) and `feature/18.0` (not released).

The addons use four services of ONLYOFFICE Docs (Document Server): the editor (`api.js` and the save callback), the
converter, docbuilder, and the Automation API of the editor (the `ODOO_*` spreadsheet functions, inserting field keys
into a template). How each one is used: skills `onlyoffice-odoo-core` and `odoo-controllers-jwt`.

**Docs editions.** The editor and conversion work on any edition. Docbuilder and the Automation API are needed for
templates and the `ODOO_*` formulas, so CI and e2e run the **Developer Edition** (`onlyoffice/documentserver-de`).
Without the Automation API, the template editor shows a warning and falls back to copying field keys.

### Supported versions

| Odoo | Status                                                        |
| ---- | ------------------------------------------------------------- |
| 16   | **not supported** (branch `16.0`, base addon 3.x)             |
| 17   | supported; the next release is planned as the last one for 17 |
| 18   | supported                                                     |
| 19   | supported                                                     |
| 20   | in development, never released                                |

Branches are listed in `CLAUDE.md`, the version lines of the addons in the release skill. ONLYOFFICE Docs: checked
against 9.4.x and 10.0.x. The code has no minimum-version check.

## 2. Main features (user scenarios)

**`onlyoffice_odoo`**

1. Open an attachment (Discuss, the chatter of any record) in ONLYOFFICE, in a new tab or in the same tab ("Open file in
   the same tab"). Co-edit it; the file is saved back to the attachment.
2. View-only mode for formats that cannot be edited (rtf, odt, vsdx, …) and for users without write access.
3. Preview of documents in the editor (`/onlyoffice/preview`).
4. Settings (Settings → ONLYOFFICE): Docs address, Docs inner address, Odoo address for Docs, JWT secret and header,
   disable certificate verification, demo server, and a connection check on save.

**`onlyoffice_odoo_documents`** (Enterprise)

5. Open a document from Documents in ONLYOFFICE. Every save adds a version.
6. Create a blank docx / xlsx / pptx / pdf, or a form from the ONLYOFFICE form gallery, in the current folder.
7. Share with ONLYOFFICE roles (17: `viewer`, `commenter`, `reviewer`, `editor`, `form_filling`, `custom_filter`; 18+:
   `view` / `edit` plus the same extra roles). Roles go to all employees, to a link or to single users, and **never
   exceed the user's rights in Odoo**.
8. Open and edit through a Documents share link ("Open in ONLYOFFICE" on the share page).
9. Convert a document to another format, saving it to Documents or downloading it.
10. Turn an Odoo spreadsheet into an XLSX: a static copy, or an XLSX with live `ODOO_*` formulas that Odoo computes.
    Also "Freeze and share", and inserting Odoo lists and pivots into an existing XLSX.
11. ONLYOFFICE Desktop Editors: sign-in and a restricted UI (`/Products/Files`, `desktop_*.js`).

**`onlyoffice_odoo_templates`**

12. Create a PDF-form template for an Odoo model: blank, from an uploaded PDF (converted to a form), or from the form
    gallery. Insert the model's fields in the editor.
13. Print one record, or several records as a ZIP, from the form or list view. Includes a preview and "Disable form
    fields after printing".
14. The `onlyoffice-pdf` report (`ir.actions.report`), also used for mail attachments.
15. Demo templates for the addons that are already installed (CRM, Sales, HR, …), and their export in Settings.
16. Template user and manager groups. A template can be saved to Documents when Documents is installed.

## 3. Build and infrastructure

There is no build step. An addon is a folder of Python / JS / XML, and Odoo bundles the assets itself. A "build" is the
branch content plus the version in the manifests. Dev setup is in `CONTRIBUTING.md`, commands are in `CLAUDE.md`.

- **Toolchain:** Python 3.10 in CI on 17–19 and 3.12 on 20 (`ghcr.io/oca/oca-ci/py3.x-odoo<v>.0`). PostgreSQL 12 in CI
  on 17–19 and 16 on 20. Node 20 for e2e and 22.9.0 for the pre-commit hooks. Linter versions are pinned in
  `.pre-commit-config.yaml`.
- **Repositories:** the main repository is `git@git.onlyoffice.com:ONLYOFFICE/onlyoffice_odoo.git`. Pull requests and CI
  (Gitea Actions) live there. It is push-mirrored automatically to the **public**
  `github.com/ONLYOFFICE/onlyoffice_odoo`, where the same workflows run and outside contributors open issues and pull
  requests. Everything pushed to any branch becomes public.
- **Vendored assets:** the formats list and the blank new-file templates in `onlyoffice_odoo/static/assets/` come from
  the shared repositories `ONLYOFFICE/document-formats` (`master`) and `ONLYOFFICE/document-templates` (`main/new`).
  Other integrations use them as submodules; here they are hard-committed, because the Odoo Apps Store does not fetch
  submodules. Update procedure: skill `update-assets`.
- **Private dependencies:** Odoo Enterprise of the same version is needed to run or test `onlyoffice_odoo_documents`. On
  18–20 the `documents` job of `test.yml` / `e2e.yml` gets the Enterprise addons from a private source, so it runs only
  in Gitea Actions and is skipped on the GitHub mirror (`if: !startsWith(github.server_url, 'https://github.com')`). On
  17, CI has no Enterprise and creates stub `documents` / `documents_spreadsheet` manifests.

## 4. Publishing

- **Odoo Apps Store (apps.odoo.com)** is the only marketplace. It lists "ONLYOFFICE", "ONLYOFFICE Documents" and
  "ONLYOFFICE Templates" (and "ONLYOFFICE DMS" from its own repository) for each Odoo version, all free. The store pulls
  the code from the release branch `<v>.0` of the registered repository; there is no upload and no manual review. Any
  manifest error or missing dependency unpublishes every app of the repository, and the store can also unpublish an app
  without notice.
- **GitHub releases** are created by hand on `github.com/ONLYOFFICE/onlyoffice_odoo` for each release tag.
- **OCA.** The branches `OCA/17.0` and `OCA/18.0` prepared the base addon for the Odoo Community Association: READMEs
  from fragments, documents / templates removed. The work **stopped before publication**, and nothing was submitted to
  OCA.

Steps, store page rules and checks: `.claude/skills/release/SKILL.md`.

## 5. Behavior worth knowing

For support and for reading bug reports:

- Docs saves a file about 5 s after the last user leaves the editor (`savetimeoutdelay`), and up to a minute under load.
  "The file was not saved" right after closing is usually this delay.
- Demo templates are created only for the addons installed **before** `onlyoffice_odoo_templates`. An addon installed
  later gets no demo template.
- Without a version bump, Odoo does not upgrade the addons on existing databases: new fields and access rules appear
  only after `-u`.

Coding rules and pitfalls (version deltas, the three `env.cr.commit()` calls, duplicated code paths, URL checks, tokens)
are in `CLAUDE.md` and the skills.

## 6. Tech debt and unfinished branches

**Tech debt**

- `onlyoffice_odoo_documents` has no automated tests on 17. None are planned, because support for 17 ends after its
  next release. On 18–20 the tests exist and run in Gitea CI.
- Two `TODO`s in `onlyoffice_odoo_templates/controllers/controllers.py`: a skipped field type, and `.sudo()` when
  reading the record.
- Inconsistent class and logger names: skill `odoo-code-style`, "Known inconsistencies".

**Unfinished branches**

| Branch                                                         | What is in it                                                                         | State                                                                                                                                                                                     |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `feature/17.0-form-gallery-v2`, `feature/18.0-form-gallery-v2` | Moves the form gallery to the new API (`templates.onlyoffice.com/dashboard/v2/api`).  | **Frozen.** The old gallery API was repaired, and the gallery works on it. Before reviving: merge the fresh `develop` / `feature/18.0` and check the new API against the code again.      |
| `feat/17.0-local-address-check`                                | Rejects local and private Docs addresses (SSRF hardening). The last commit is `temp`. | **Abandoned and unfinished; do not build on it.** If needed, redo it in a shared URL-check helper (parse, not text). Keep in mind that Docs often runs on a private address legitimately. |

Other branches on `origin` are history (releases, OCA, partner work). Leave them as they are.

## 7. Plans and commitments

- No commitments to customers or partners.
- Near term:
  - Release 17 (the last release for 17).
  - Release 18 and 19 from `feature/18.0` / `feature/19.0`; the fixes are already ported.
  - The first release for Odoo 20.

## 8. Smoke checks

- **Automated:** unit tests (including tests against a live Docs) and Playwright e2e run in CI on every push and pull
  request. What they cover: skill `odoo-testing`.
- **Manual:** the checklist before a release is in `.claude/skills/release/SKILL.md`, section 3.
