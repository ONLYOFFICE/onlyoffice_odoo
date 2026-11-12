---
name: release
description:
  Release the ONLYOFFICE Odoo addons (onlyoffice_odoo, onlyoffice_odoo_documents, onlyoffice_odoo_templates) for one or
  more Odoo versions and publish them on the Odoo Apps Store and GitHub releases - version bump, changelogs, checks,
  release PR, tag, store verification, manual steps. Use when asked to prepare, cut, tag or publish a release or a
  hotfix.
---

# Release and publication

A release of an Odoo version = the release branch `<v>.0` moves to a new commit with bumped manifest versions. The Odoo
Apps Store reads that branch; there is nothing to upload. Every push to git.onlyoffice.com is mirrored automatically to
the public `github.com/ONLYOFFICE/onlyoffice_odoo`.

| Odoo | Source branch  | Release branch                   | Version lines (base / documents / templates)  |
| ---- | -------------- | -------------------------------- | --------------------------------------------- |
| 17   | `develop`      | `17.0`                           | 4.x / 4.x / 2.x                               |
| 18   | `feature/18.0` | `18.0`                           | 5.x / 5.x / 3.x                               |
| 19   | `feature/19.0` | `19.0`                           | 6.x / 6.x / 4.x                               |
| 20   | `feature/20.0` | `20.0` (create on first release) | agree on the numbers before the first release |

Read the current numbers from the manifests and `CHANGELOG*.md`; the table only shows the lines.

**Ask the user before every push, PR, merge, tag and GitHub release.** Never force-push.

## 1. Decide the scope

1. Which Odoo versions and which addons change. Compare with the last release:
   `git log --oneline origin/<v>.0..origin/<source branch> -- <addon>/`.
2. Releases go upward: 17 first, then 18, 19, 20. A version is released only after its source branch contains everything
   of the lower one (`git merge-base --is-ancestor origin/develop origin/feature/18.0`, and so on).
3. **Release the three addons of a version together** when the base addon changed: documents and templates import
   `onlyoffice_odoo.controllers.main` (the old `controllers.controllers` / `Onlyoffice_Connector` is gone).
4. Hotfix of a released version: branch `hotfix/<v>` from `origin/<v>.0`, fix, then the same steps; afterwards merge
   `<v>.0` back into the source branch and the hotfix upward (`17.0` → `hotfix/18` → `18.0` → …).

## 2. Bump versions and changelogs (on the source branch)

1. `__manifest__.py` of every released addon: `"version": "<series>.<x>.<y>.<z>"` — keep the series prefix
   (`17.0.4.5.0`); the store expects it. Patch for fixes only, minor for features, major for breaking changes (e.g. the
   controller rename above, data migrations).
2. `CHANGELOG.md` (base), `CHANGELOG documents.md`, `CHANGELOG templates.md`: rename `## Unreleased` (or an empty `##`)
   to `## <x>.<y>.<z>`; sections `## Added` / `## Changed` / `## Fixed`, user-facing wording. Remove empty sections.
3. Migrations run only when the version changes. On 18–20 `onlyoffice_odoo_documents/migrations/0.0.0/post-migrate.py`
   runs on **every** version update and clears the Odoo roles (`none` / `view` / `edit`) older releases wrote into the
   ONLYOFFICE role rows — a documents release without a version bump leaves those rows and breaks access on upgraded
   databases. Data fixes for one version go to `migrations/<new version>/`.
4. Store page: if features or screenshots changed, update `static/description/index.html`, the `images` in the manifest,
   `doc/index.rst`, `README.md` ("Supported formats"). `index.html` rules: English; no JS, modals, iframes, ads; links
   only to files in `static/description/`, YouTube, `mailto:`; Bootstrap classes and basic style attributes only;
   `icon.png` must be a real PNG.
5. Commit: one line, e.g. `chore: release 4.5.0` (or per addon `templates: 2.6.0`).

## 3. Checks (all must pass)

1. CI green on git.onlyoffice.com (Gitea Actions) for the source branch: Lint, test (unit + live Docs; on 18+ also the
   `documents` job), e2e.
2. Manifests parse:
   `python -c "import ast,glob;[ast.literal_eval(open(f,encoding='utf-8').read()) for f in glob.glob('*/__manifest__.py')]"`.
   **A broken manifest unpublishes every app of the repository on the store.**
3. Fresh install on a clean database of that version with Enterprise and Docs Developer Edition: `hr`, then
   `onlyoffice_odoo,onlyoffice_odoo_templates,onlyoffice_odoo_documents` — no errors or warnings in the log.
4. Upgrade: a database with the previous release installed, check out the new branch, `-u` all three addons — no errors;
   existing share roles and templates still work.
5. The manual checklist in `HANDOVER.md` (section 8) on that database, as `admin` and as `demo`.
6. Every `depends` is either core/Enterprise Odoo or an addon published from this repository.

## 4. Release PR, merge, tag

1. Push the source branch. Open a PR on git.onlyoffice.com: `Release/<v>.0`, from the source branch (or `hotfix/<v>`)
   into `<v>.0`. Wait for review and CI, merge.
2. Tag the merge commit on `<v>.0` with the version of the addon the release is about: `v<x>.<y>.<z>`
   (`git tag -a v4.5.0 -m "ONLYOFFICE v4.5.0"` → push the tag). Tags of different addons and versions share one
   namespace — `git tag -l v<x>.<y>.<z>` first; if the tag exists, agree on the name with the team lead.
3. Merge the release branch back into the source branch so they do not diverge (`git merge origin/<v>.0` on the source
   branch), then continue upward to the next version.

## 5. Publish

1. **GitHub release** (manual, on `github.com/ONLYOFFICE/onlyoffice_odoo` once the mirror has the tag): tag
   `v<x>.<y>.<z>`, title `v<x>.<y>.<z>`, body = `# ONLYOFFICE <Addon> v<x>.<y>.<z>` + the changelog section of that
   version. No assets.
2. **Odoo Apps Store**: the store rescans the registered release branches by itself (no upload, no review). After the
   rescan check the app pages (apps.odoo.com/apps/modules/<v>.0/onlyoffice_odoo, …\_documents, …\_templates): new
   version number, description, screenshots. If a page did not update or apps disappeared, look for a scan error (bad
   manifest, missing dependency) and fix it on the release branch at once — the store does it for the whole repository.
3. The DMS addon (`ONLYOFFICE/onlyoffice_odoo_dms`) has its own repository and is released the same way when it changes;
   it depends on `onlyoffice_odoo`, so check it still installs against the new base addon.

## 6. After the release

- Source branch: add an empty `## Unreleased` to the changelogs only when the next change lands (do not leave empty
  headings in a release).
- Tell the team the released versions; update the version table in `HANDOVER.md` if a version line or support status
  changed (for example, 17 stops being supported after its last release).
