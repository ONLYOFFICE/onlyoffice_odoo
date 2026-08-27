---
name: odoo-migration-17-18-19
description:
  Porting ONLYOFFICE module changes between Odoo 17, 18 and 19 code lines via merge, plus a reference of framework
  differences between the versions. Use for any port, merge, version-compatibility question, or when writing
  version-correct code on any branch whose manifest version is 18.0.x or 19.0.x.
---

# Porting 17 → 18 → 19

This skill has two uses:

1. **Port workflow** — moving changes forward through merges.
2. **Version reference** — the difference tables below tell you which API to use in the code you are editing right now.
   Pick the column by the `__manifest__.py` version prefix (`17.0.x` / `18.0.x` / `19.0.x`), never by the branch name —
   work branches forked from the integration branches (`feature/18.0`, `feature/19.0`) can be named anything.

## Workflow

A change ports forward from whichever code line it was made on, toward newer ones — 17 → 18 → 19 is the typical path,
but a fix can just as well start on 18 and only need porting to 19. The integration branches are `feature/18.0` and
`feature/19.0`; new 18/19 work is usually done on branches forked from them and merged back.

1. Finish and test the change on its original code line.
2. If an 18 code line is affected and the change didn't originate there, merge into the 18 integration branch
   (`feature/18.0`) or a branch forked from it. Resolve conflicts in favor of the 18 API.
3. If a 19 code line is affected and the change didn't originate there, merge the 18 result into the 19 integration
   branch (`feature/19.0`) or a fork of it. Resolve for the 19 API.
4. Run the module tests on each target; confirm each target's manifest prefix before resolving anything.

Rules:

- Never skip an intermediate version when porting forward (e.g. don't merge 17 straight into 19) — go through each
  version in between, applying its checklist.
- Keep compatibility edits (API renames) in separate commits from behavior changes when possible — it makes the next
  merge easier.
- Verify against the real target source. Do not trust memory for renamed APIs; open the same file in the target Odoo
  branch (github.com/odoo/odoo, github.com/odoo/enterprise) or a local checkout.
- Never change the manifest version prefix or bump the version yourself — that is a separate release process.

## 17 → 18: changes that hit these modules

| Area                       | 17                                          | 18                                                                                                                      | Affects                             |
| -------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| Access checks              | `check_access_rights` / `check_access_rule` | `has_access(op)` / `check_access(op)`                                                                                   | controllers everywhere              |
| Views                      | `<tree>`                                    | `<list>` (tree deprecated)                                                                                              | template/form views                 |
| Documents app (Enterprise) | `documents.folder`, `documents.share`       | folders became documents (`type="folder"`); sharing reworked into an access/permission model; `documents.share` removed | most of `onlyoffice_odoo_documents` |
| Chatter in form views      | `<div class="oe_chatter">...`               | `<chatter/>` tag                                                                                                        | any form view with chatter          |
| JS module header           | `/** @odoo-module **/` required             | optional                                                                                                                | all JS                              |
| rpc service                | `useService("rpc")`                         | import `rpc` from `@web/core/network/rpc`                                                                               | OWL components                      |
| SQL                        | strings accepted                            | `SQL()` builder recommended                                                                                             | any raw SQL                         |

Port checklist (18):

- [ ] Replace access-check calls; grep for `check_access_rights` and `check_access_rule`
- [ ] Rework Documents integration: folder ids, share links, access roles
- [ ] Re-check every JS patch of Documents components against 18 sources
- [ ] Rename tree views to list; re-test all views
- [ ] Run tests (do not bump the manifest version)

## 18 → 19: changes that hit these modules

| Area               | 18                         | 19                                                                              | Affects                        |
| ------------------ | -------------------------- | ------------------------------------------------------------------------------- | ------------------------------ |
| SQL constraints    | `_sql_constraints` list    | `models.Constraint()` class attributes                                          | any model with SQL constraints |
| OWL                | 2.x                        | 3.x — stricter props validation                                                 | all components and patches     |
| `res.users` create | `groups_id` in vals worked | `groups_id` ignored in `create()`; add via `group.write({"users": [(4, uid)]})` | test setUp code                |
| Raw SQL            | discouraged                | `SQL()` builder required                                                        | any raw SQL                    |
| Python             | 3.10+                      | 3.12+                                                                           | dependency checks              |
| Documents app      | 18 access model            | changed again — re-verify                                                       | `onlyoffice_odoo_documents`    |

Port checklist (19):

- [ ] Convert `_sql_constraints` to `models.Constraint`
- [ ] Update OWL props to object form (`{ type, required, optional }`)
- [ ] Fix user creation in tests (groups after create)
- [ ] Wrap any raw SQL in `SQL()`
- [ ] Re-verify all Enterprise `documents` touch points
- [ ] Run tests (do not bump the manifest version)

## Merge conflict rules

- Config/util modules (`config_utils`, `jwt_utils`, `file_utils`, `url_utils`) rarely differ between branches — take the
  incoming change, then re-apply version-specific bits.
- Controllers and `onlyoffice_odoo_documents` differ the most — resolve hunk by hunk with the target-version API open
  next to you.
- If a 17 feature has no 18/19 equivalent API, port the intent, not the code: find how the target Documents app models
  the same concept.
- After any merge, grep the diff for 17-only names (`documents.share`, `check_access_rights`, `<tree`) before
  committing.

## Version detection

The `__manifest__.py` version prefix is the source of truth (`17.0.x` / `18.0.x` / `19.0.x`) — check it in the module
you are editing. Branch names only hint at the target. If the manifest prefix does not match the version you expected to
work on, stop and ask before changing anything.
