---
name: update-assets
description:
  Update the vendored ONLYOFFICE assets of onlyoffice_odoo - the formats list (ONLYOFFICE/document-formats, branch
  master) and the blank new-file templates per language (ONLYOFFICE/document-templates, branch main/new) - by copying
  them from their upstream repositories, then adapting code, docs, changelog and tests. Use when asked to update the
  formats list or the file templates, to add a language for new files, or when a format or template is wrong.
---

# Update the vendored assets

## Why they are vendored

Two ONLYOFFICE repositories are shared by many integrations:

- `onlyoffice_odoo/static/assets/document_formats/` ← `https://git.onlyoffice.com/ONLYOFFICE/document-formats`, branch
  `master`. `onlyoffice-docs-formats.json` lists every extension with its type, actions (`view`, `edit`, `fill`, …),
  conversion targets and mime types.
- `onlyoffice_odoo/static/assets/document_templates/` ← `https://git.onlyoffice.com/ONLYOFFICE/document-templates`,
  branch `main/new`. `<locale>/new.docx`, `new.xlsx`, `new.pptx`, `new.pdf` (blank PDF form) per language, plus
  `default/`.

Other integrations connect them as git submodules. The Odoo Apps Store pulls the addons straight from the release
branch and **does not fetch submodules**, so here they are hard-committed copies. That is why:

- **Never edit them by hand.** The next update overwrites the change. A fix to a format or a template goes to the
  upstream repository first, then comes here with an update.
- The folders are an exact copy of the upstream tree (without `.git`): no Odoo-specific files inside, nothing removed.
- Lint skips them (`.pre-commit-config.yaml`, `.prettierignore`, `.editorconfig` exclude `**/assets/**`). Never let a
  formatter touch them; the upstream files keep their own BOM and CRLF line endings.

Who reads them: `utils/format_utils.py` → `file_utils.can_view` / `can_edit` / `can_fill_form` (Python); the chatter
patch, the Documents inspector patch and the convert dialog fetch
`/onlyoffice_odoo/static/assets/document_formats/onlyoffice-docs-formats.json` (JS);
`file_utils.get_default_file_template(lang, ext)` reads the templates (documents `file/create`, templates `create()`);
e2e uses `document_templates/en-US/new.*` as fixtures.

## Procedure

Do one repository per run and per commit. The assets are the same on every Odoo version line: update on 17 and merge
upward like any fix (`CLAUDE.md`).

1. **Branch.** From a fresh `develop`: `chore/17.0-update-formats` or `chore/17.0-update-templates`.
2. **Fetch upstream** into a temporary folder outside the repository (the scratchpad), read-only:

   ```bash
   git clone --depth 1 -b master   https://git.onlyoffice.com/ONLYOFFICE/document-formats   <tmp>/formats
   git clone --depth 1 -b main/new https://git.onlyoffice.com/ONLYOFFICE/document-templates <tmp>/templates
   git -C <tmp>/formats rev-parse HEAD    # the upstream commit, for the commit message
   ```

3. **Compare first:** `diff -rq --exclude=.git <tmp>/formats onlyoffice_odoo/static/assets/document_formats`. No
   output → already up to date, stop. Otherwise read what changed upstream: the `CHANGELOG.md` of document-formats, or
   the list of added / removed / changed locale folders of document-templates.
4. **Mirror the tree** (replace the folder content, so removed upstream files are removed here too):

   ```bash
   DST=onlyoffice_odoo/static/assets/document_formats      # or document_templates
   find "$DST" -mindepth 1 -delete
   cp -r <tmp>/formats/. "$DST"/ && rm -rf "$DST/.git"
   ```

5. **Check the diff.** `git status` and `git diff --stat -- onlyoffice_odoo/static/assets` must list only the files that
   changed upstream. If every text file shows as changed with no content change, it is line endings (`core.autocrlf`):
   `diff -rq --strip-trailing-cr` against the clone tells, and `git checkout -- <file>` restores the unchanged ones.
6. **Adapt the code** (see the checklists below). Code changes go to their own commits, with tests, after the asset
   commit.
7. **Changelog:** a user-facing line in `CHANGELOG.md` (base addon) under `## Unreleased`, in the style of the earlier
   ones: `## Added` — `- open to view vsdx, vssx, … diagram formats`, `- Catalan, Danish, … empty file templates`;
   `## Changed` — `- support tsv`. Do not copy the upstream changelog.
8. **Commit** the assets alone, one line:
   - `chore: update formats list (https://git.onlyoffice.com/ONLYOFFICE/document-formats/commit/<sha>)`
   - `chore: update file templates (https://git.onlyoffice.com/ONLYOFFICE/document-templates/commit/<sha>)`

   Older commits link the GitHub mirror (`github.com/ONLYOFFICE/document-formats/commit/<sha>`); the commit sha is the
   same.

9. **Verify:** `onlyoffice_odoo` unit tests (`test_file_utils.py` reads both assets), and e2e for a formats update that
   touches docx / xlsx / pptx / rtf or for a templates update that touches `en-US`. Ask before starting them.
10. **PR** into `develop`, then merge upward. After the merges
    `git diff develop origin/feature/<v>.0 -- onlyoffice_odoo/static/assets` must be empty on every line.

## After a formats update

- **New action names.** The code reads only `view`, `edit` and `fill` (`file_utils`, `attachment_card_onlyoffice.js`,
  `documents_inspector_onlyoffice.js`). Upstream also has `comment`, `review`, `customfilter`, `encrypt`,
  `auto-convert`, `lossy-edit`; they are ignored. A new action that should change behavior (e.g. `lossy-edit` → open
  for editing with a warning) is a feature: separate change, test, changelog.
- **A format gains or loses `edit`** (e.g. xls becomes editable): the chatter button, the Documents "Open" mode and
  view-only mode change for that extension. Check the e2e test that relies on a view-only format (`rtf` in
  `e2e/tests/editor.spec.ts`).
- **Removed formats** (e.g. docxf / oform): `grep -rni "<ext>"` over the three addons, tests and e2e (outside
  `static/assets`).
- **New conversion targets:** the convert dialog takes them from `convert` automatically; no code change.
- **Supported formats lists** in `README.md` ("Supported formats"); also check `<addon>/doc/index.rst` and
  `static/description/index.html` if a format is named there.
- The JSON must stay loadable with `encoding="utf-8"` (`format_utils.get_supported_formats`); upstream has no BOM in it
  today. If it gains one, switch the reader to `utf-8-sig` in the same change.

## After a templates update

- **New locale folder → mapping.** `file_utils.get_default_file_template` resolves the folder through the `locale_path`
  dict: the user's lang with `_` → `-`, exact key first, then the language prefix, then `default`. A folder without a
  key is never used. Add a key for the new language (prefix such as `"hr": "hr-HR"`; a full code only when one
  language has several folders, e.g. `sr-Latn-RS` / `sr-Cyrl-RS`) and a test. A full-code key must match the lang as
  Odoo gives it after `_` → `-` (`pt_BR` → `pt-BR`): the lookup is case-sensitive, so the existing `pt-br` and `en-gb`
  keys never match and those users get `pt-PT` / `en-US`.
- Folders without a key today: `ar-SA`, `be-BY`, `hr-HR`, `hy-AM`, `lo-LA`, `ms-MY`, `si-LK`, `sl-SI`, `sq-AL`,
  `sr-Cyrl-RS`, `sr-Latn-RS`, `ur-PK`. Fix them in a code change, not in an asset commit.
- **Removed locale folder:** remove its key, otherwise opening a new file for that language fails with
  `FileNotFoundError`.
- Every locale folder must have all four files (`docx`, `xlsx`, `pptx`, `pdf`); `pdf` is also the blank template of
  `onlyoffice_odoo_templates`.
- The changelog names the languages, not the locale codes.
