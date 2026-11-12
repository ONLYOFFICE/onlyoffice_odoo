# Handover: ONLYOFFICE for Odoo

State as of 2026-11-12. Day-to-day commands and rules are in `CLAUDE.md`; the release procedure is in
`.claude/skills/release/SKILL.md`; module internals are in the other skills of `.claude/skills/`.

## 1. Integration type

**Odoo addons that run inside Odoo**, not a separate service. This repository holds three addons. They are connected
only through `depends` in their manifests:

| Addon                       | What it does                                                                                                                                                                         | Depends on                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `onlyoffice_odoo`           | Base connector. Opens attachments (`ir.attachment`) in the ONLYOFFICE editor. Holds the settings, JWT, the save callback and the preview.                                            | `base`, `mail`; Python `pyjwt`                                                     |
| `onlyoffice_odoo_documents` | Integration with the Enterprise Documents app: create, share with ONLYOFFICE roles, share links, conversion, Odoo spreadsheets ↔ XLSX with `ODOO_*` formulas, Desktop Editors mode. | `onlyoffice_odoo`, `documents`, `documents_spreadsheet` (**Odoo Enterprise only**) |
| `onlyoffice_odoo_templates` | Fillable PDF form templates filled with data of Odoo records; the `onlyoffice-pdf` report type. Co-authored with the partner Data Dance s.r.o., who also sends pull requests.        | `onlyoffice_odoo`, `web`                                                           |

The handover also includes a fourth addon in its own repository, **`onlyoffice_odoo_dms`**
(`git.onlyoffice.com/ONLYOFFICE/onlyoffice_odoo_dms`, mirrored to `github.com/ONLYOFFICE/onlyoffice_odoo_dms`). It
integrates ONLYOFFICE with the OCA `dms` module and depends on `onlyoffice_odoo` and `dms`. Users open and create files
in DMS directories, and the addon resolves ONLYOFFICE roles per user, per DMS group and per share link. It is
co-authored with Data Dance. Its branches are `develop` and `17.0` (released, 1.0.3) and `feature/18.0` (not released).

### How it talks to ONLYOFFICE Docs (Document Server)

All traffic to the Document Server goes through `onlyoffice_request` / `onlyoffice_urlopen` in
`onlyoffice_odoo/controllers/main.py`. These helpers apply the certificate setting and swap the public Docs address for
the inner one.

- **Editor.** The browser loads `api.js` from Docs. Docs downloads the file from `/onlyoffice/file/content/<id>`. When
  the file is saved, Docs posts a callback to `/onlyoffice/editor/callback/<id>`. On status 2/3, Odoo downloads the
  result and writes it to the attachment. Documents has its own share-link callback.
- **Converter** (`/converter`). Used to check the settings, to convert formats (documents) and to turn a PDF into a PDF
  form (templates).
- **Docbuilder** (`/docbuilder`). Used to fill templates and to read their field keys (templates), and to export Odoo
  spreadsheets to XLSX and insert lists and pivots (documents).
- **Automation API of the editor** (`createConnector`, `Api.AddCustomFunction`). Provides the `ODOO_*` spreadsheet
  functions and inserts field keys into a template.
- **Two JWT layers.** The Docs secret comes from the settings. An internal Odoo secret signs `oo_security_token` on
  public routes.

**Docs editions.** The editor and conversion work on any edition. Docbuilder and the Automation API are needed for
templates and the `ODOO_*` formulas, so CI and e2e run the **Developer Edition** (`onlyoffice/documentserver-de`).
Without the Automation API, the template editor shows a warning and falls back to copying field keys.

### Supported versions

| Odoo | Development branch | Release branch          | Base addon version line | Status                                                        |
| ---- | ------------------ | ----------------------- | ----------------------- | ------------------------------------------------------------- |
| 16   | —                  | `16.0`                  | 3.x                     | **not supported**                                             |
| 17   | `develop`          | `17.0`                  | 4.x                     | supported; the next release is planned as the last one for 17 |
| 18   | `feature/18.0`     | `18.0`                  | 5.x                     | supported                                                     |
| 19   | `feature/19.0`     | `19.0` (default branch) | 6.x                     | supported                                                     |
| 20   | `feature/20.0`     | —                       | —                       | in development, never released                                |

ONLYOFFICE Docs: checked against 9.4.x and 10.0.x. The code has no minimum-version check.

## 2. Main features (user scenarios)

**`onlyoffice_odoo`**

1. Open an attachment (Discuss, the chatter of any record) in ONLYOFFICE, in a new tab or in the same tab ("Open file in
   the same tab"). Co-edit it; the file is saved back to the attachment.
2. View-only mode for formats that cannot be edited (rtf, odt, vsdx, …) and for users without write access.
3. Preview of documents in the editor (`/onlyoffice/preview`).
4. Settings (Settings → ONLYOFFICE): Docs address, Docs inner address, Odoo address for Docs, JWT secret and header,
   disable certificate verification, demo server, and a connection check on save.

**`onlyoffice_odoo_documents`** (Enterprise) 5. Open a document from Documents in ONLYOFFICE. Every save adds a
version. 6. Create a blank docx / xlsx / pptx / pdf, or a form from the ONLYOFFICE form gallery, in the current
folder. 7. Share with ONLYOFFICE roles (17: `viewer`, `commenter`, `reviewer`, `editor`, `form_filling`,
`custom_filter`; 18+: `view` / `edit` plus the same extra roles). Roles go to all employees, to a link or to single
users, and **never exceed the user's rights in Odoo**. 8. Open and edit through a Documents share link ("Open in
ONLYOFFICE" on the share page). 9. Convert a document to another format, saving it to Documents or downloading it. 10.
Turn an Odoo spreadsheet into an XLSX: a static copy, or an XLSX with live `ODOO_*` formulas that Odoo computes. Also
"Freeze and share", and inserting Odoo lists and pivots into an existing XLSX. 11. ONLYOFFICE Desktop Editors: sign-in
and a restricted UI (`/Products/Files`, `desktop_*.js`).

**`onlyoffice_odoo_templates`** 12. Create a PDF-form template for an Odoo model: blank, from an uploaded PDF (converted
to a form), or from the form gallery. Insert the model's fields in the editor. 13. Print one record, or several records
as a ZIP, from the form or list view. Includes a preview and "Disable form fields after printing". 14. The
`onlyoffice-pdf` report (`ir.actions.report`), also used for mail attachments. 15. Demo templates for the addons that
are already installed (CRM, Sales, HR, …), and their export in Settings. 16. Template user and manager groups. A
template can be saved to Documents when Documents is installed.

## 3. Build

There is no build step. An addon is a folder of Python / JS / XML, and Odoo bundles the assets itself. A "build" is the
branch content plus the version in the manifests.

- **Toolchain:**
  - Python 3.10 (CI image `ghcr.io/oca/oca-ci/py3.10-odoo<v>.0`).
  - PostgreSQL 12 in CI, 13 in the e2e stack.
  - Node 20 for e2e, Node 22.9.0 for the pre-commit hooks.
  - ruff `v0.15.21` (pinned in pre-commit).
  - pylint-odoo `9.1.3`. It is pinned because newer versions do not know some checks listed in `.pylintrc`.
  - prettier 3.3.3 with plugin-xml 3.4.1, and eslint 9.
- **Dev setup:** see `CONTRIBUTING.md` (`npm install`, venv, `pip install -e .[dev]`, `pre-commit install`).
- **Non-standard parts:**
  - `onlyoffice_odoo/static/assets/document_formats/` is a vendored copy of `ONLYOFFICE/document-formats`. It is updated
    by a commit named `update formats list (<link to the upstream commit>)`. Formats are never hard-coded: Python and JS
    read `onlyoffice-docs-formats.json`. `static/assets/document_templates/` holds the blank files per language.
  - pre-commit regenerates the addon READMEs (`oca-gen-addon-readme` from `readme/`) and `requirements.txt`. The
    prettier hook may fail the first commit attempt; run `git add` and commit again.
  - On 17, CI has no Enterprise. It creates stub `documents` / `documents_spreadsheet` manifests, so
    `onlyoffice_odoo_documents` has **no automated tests on 17**. None are planned, because support for 17 ends after
    its next release.
  - On 18–20 the `documents` job of `test.yml` / `e2e.yml` needs Enterprise addons that come from a private source. It
    runs only in Gitea Actions and is skipped on the GitHub mirror
    (`if: !startsWith(github.server_url, 'https://github.com')`).
- **Private dependencies:** Odoo Enterprise, of the same version, is needed to run or test `onlyoffice_odoo_documents`
  locally.
- **Repositories:** the main repository is `git@git.onlyoffice.com:ONLYOFFICE/onlyoffice_odoo.git`. Pull requests and CI
  (Gitea Actions) live there. It is push-mirrored automatically to the **public**
  `github.com/ONLYOFFICE/onlyoffice_odoo`, where the same workflows run and outside contributors open issues and pull
  requests. Everything pushed to any branch becomes public.

## 4. Publishing to marketplaces

- **Odoo Apps Store (apps.odoo.com)** is the only marketplace. The store lists the apps "ONLYOFFICE", "ONLYOFFICE
  Documents" and "ONLYOFFICE Templates" (and "ONLYOFFICE DMS" from its own repository) for each Odoo version. All of
  them are free (no `price` in the manifests).
  - The store pulls code from the registered git repository, using one branch per Odoo version
    (`ssh://…/onlyoffice_odoo#17.0`). Releasing means updating the release branch `<v>.0`; there is no upload.
  - There is no manual review. Instead, the store scans the repository, and **any manifest error or missing dependency
    unpublishes every module of that repository**. The store can also unpublish an app without notice.
  - The store page comes from the manifest (`name`, `summary`, `images`, `website`, `support`), `static/description/`
    (`icon.png` must be a real PNG, `index.html`) and `doc/index.rst`.
  - `index.html` is sanitized. It must be in English, with no JS, modals or ads, and no external links except resources
    inside `static/description/`, YouTube and `mailto:`. Styling is limited to Bootstrap classes plus basic color, font,
    margin, padding and border attributes. Anything else is stripped.
  - The store expects the Odoo series in `version` (`17.0.x.y.z`). This prefix is present on the development branches
    since July 2026; the previous releases were made without it.
- **GitHub releases** are created by hand on `github.com/ONLYOFFICE/onlyoffice_odoo` for each release tag. The body is
  the changelog of the released addon, titled `# ONLYOFFICE <Addon> vX.Y.Z`.
- **OCA.** The branches `OCA/17.0` and `OCA/18.0` prepared the base addon for the Odoo Community Association: READMEs
  from fragments, documents / templates removed. The work **stopped before publication**, and nothing was submitted to
  OCA.
- Step-by-step instructions are in `.claude/skills/release/SKILL.md`.

## 5. Implicit knowledge

- **The version comes from the manifest.** The prefix `17.0.` / `18.0.` / … in `__manifest__.py` decides which Odoo APIs
  to use, not the branch name.
- **Never bump versions or touch `CHANGELOG*` headings in ordinary changes.** Bumping is a release step. Without a bump,
  Odoo does not upgrade the module on existing databases, so new fields and access rules appear only after `-u`.
- **`onlyoffice_odoo_documents/migrations/0.0.0/post-migrate.py` (18–20)** runs on every version update of the addon. It
  clears the Odoo roles (`none` / `view` / `edit`) that older releases copied into the ONLYOFFICE role rows, which would
  otherwise hide the current Odoo rights. It runs only when the version is bumped.
- **Release the three addons together.** `controllers/controllers.py` of the base addon became `main.py`
  (`Onlyoffice_Connector` → `OnlyofficeConnector`), and older documents / templates releases import the old one.
- **Fixes flow upward.** A fix goes to 17 (`develop`, through a PR), then `develop` → `feature/18.0` → `feature/19.0` →
  `feature/20.0` by merge commits, one version at a time. In each version, review every incoming change and adapt it to
  that version: the version's code wins over the 17 code. There are no PRs for 18–20; merges and commits go straight to
  `feature/<v>.0`. Never force-push. Version deltas worth remembering:

  - 17 roles are `viewer` / `editor` and links are `documents.share`; 18+ use `view` / `edit` and `access_via_link`.
  - In 17, `onlyoffice.odoo.documents.access.user.user_id` is a `res.users`; in 18+ it is a `res.partner`.
  - 19+ uses `type="jsonrpc"` routes.
  - 20 uses `ir.config_parameter.get_str` / `set_str`, binary `read()` returns `{'content': …}`, and access rules live
    in `ir.access.csv`. Odoo 20 also listens on 127.0.0.1 by default.

  The full list is in the skill `odoo-migration-17-18-19`.

- **`env.cr.commit()` is intentional in three places; add no new ones.**
  - Creating the internal JWT secret (`config_utils.get_internal_jwt_secret`), so that a rollback does not drop it.
  - The docbuilder cache (`spreadsheet_docbuilder._store_docbuilder_data`), because the Docs callback arrives in another
    transaction.
  - Converting a template PDF into a form (`onlyoffice_odoo_templates/models/onlyoffice_odoo_templates.py`,
    `_onchange_file`).
- **Duplicated code paths:** the save callback (base addon and the documents share callback), and template filling
  (`templates/controllers/controllers.py` and `models/ir_actions_report.py`). When you change one, check the other.
- **URLs:**
  - Build them with `config_utils.get_base_or_odoo_url(env)`, never from `request.httprequest.host`.
  - Compare them by parsing (`urlparse`: scheme, host, port, path on a directory boundary), never with `startswith`.
  - Every new address check has to be tried against host spoofing (`host@attacker.com`), redirects, 4xx and timeouts.
- **The docbuilder token in documents is a cache key** (a uuid stored in an attachment), not a JWT.
- **`evaluate_formulas_batch` is a public CORS route.** The editor sandbox calls it without an Odoo session. Access is
  checked through an internal JWT that carries `document_id`. The token user's env is used, never `sudo()` for reads.
- **XLSX metadata (`_OdooMetadata` sheet) is untrusted**, because anyone who uploads a file writes it. Put it into pages
  with `scriptsafe` only.
- **Docs saves the file about 5 s after the last user leaves** (`savetimeoutdelay`), and up to a minute under load. The
  e2e tests wait `E2E_SAVE_GRACE_MS` (55 s).
- Demo templates are created only for addons installed **before** templates. That is why CI installs `hr` first.
- Run ruff only on the addon folders. A sibling `.enterprise/` checkout would otherwise be reformatted.
- The skill files in `.claude/skills/` are kept up to date as part of fixes. When a fix changes a rule a skill
  describes, update the skill in the same change.

## 6. Tech debt and unfinished branches

**Tech debt**

- There are no `onlyoffice_odoo_documents` tests on 17; on 18–20 they exist and run in Gitea CI.
- Two `TODO`s in `onlyoffice_odoo_templates/controllers/controllers.py`: a skipped field type, and `.sudo()` when
  reading the record.

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

**Automated:**

- Unit tests of `onlyoffice_odoo` and `onlyoffice_odoo_templates`, including tests against a live Docs (tag
  `external_docserver`).
- On 18–20, also `onlyoffice_odoo_documents`.
- e2e Playwright (`e2e/`): settings, the editor for docx / xlsx / pptx / rtf, "same tab", access, templates (print, ZIP,
  report, preview, PDF → form, gallery, export).

All of them run in CI on every push and pull request; see `CLAUDE.md` for running them locally.

**Manual checklist before a release.** Run it on Odoo of that version with Enterprise and Docs Developer Edition, signed
in as `admin` and as a user without admin rights (`demo`):

- [ ] Settings: save the Docs address, inner address and Odoo address. The check passes, and a wrong address is
      rejected.
- [ ] Discuss: open docx / xlsx / pptx in ONLYOFFICE, type, close. Within about a minute the attachment holds the text.
- [ ] Documents: open a docx, type, close. The file is saved and a new version appears.
- [ ] Documents: create a docx / xlsx / pptx / pdf, and create one from the form gallery.
- [ ] Documents: convert docx → pdf, with "Save to Documents" and without (download).
- [ ] Share link with role view → the editor is read-only; with role edit → the edit is saved; wrong token → 404.
- [ ] Share dialog with ONLYOFFICE roles: `demo` without write access never gets edit mode. On 18+, an expired
      invitation gives nothing.
- [ ] Odoo spreadsheet → XLSX with formulas: `ODOO_LIST` / `ODOO_PIVOT` values in the editor match Odoo, and global
      filters apply. Insert a list into an XLSX. Open and close it without editing → no new version.
- [ ] Templates: print an employee from the form and two from the list (ZIP), print through the `onlyoffice-pdf` report,
      and attach that report to a mail.
- [ ] As `demo`: a document of another user, or of someone else's private chat, does not open (403 / no editor).
- [ ] After upgrading from the previous release (`-u` of all three addons on an old database), existing share roles
      still work.
