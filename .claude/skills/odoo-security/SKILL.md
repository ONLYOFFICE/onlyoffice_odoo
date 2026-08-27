---
name: odoo-security
description:
  Odoo security for the ONLYOFFICE modules - access rights (ir.model.access.csv), groups, record rules, sudo discipline,
  route authentication, and the document role model. Use whenever models, routes, or permissions change, and as a final
  checklist for any change.
---

# Security

## Access rights (ACL)

Every model needs at least one line in `security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.model user,model_my_model,base.group_user,1,1,1,0
```

- No `group_id` = applies to everyone (including portal/public via server code). Avoid unless intended.
- Model reference name: `model_` + model name with dots as underscores.

## Groups

`onlyoffice_odoo_templates` defines its own group in `security/onlyoffice_templates_security.xml`
(`group_onlyoffice_odoo_templates_admin`). Check membership with:

```python
request.env.user.has_group("onlyoffice_odoo_templates.group_onlyoffice_odoo_templates_admin")
```

Template editing is admin-group-only; template filling is for all users. Keep this split when adding features.

## sudo discipline

- Default: run as the real user. On public routes, resolve the user from `oo_security_token` and use `.with_user(user)`.
- `sudo()` only for: reading config parameters, internal bookkeeping (renaming history attachments), and lookups that
  must ignore ACLs — always after the user's own access was already verified.
- Never `sudo()` the actual file read/write on behalf of an unverified caller.

## Document roles (onlyoffice_odoo_documents)

Two models control per-document access on top of standard Odoo rights:

- `onlyoffice.odoo.documents.access` — defaults: `internal_users` role and `link_access` role for one document.
- `onlyoffice.odoo.documents.access.user` — explicit role per user.

Roles: `none`, `viewer`, `commenter`, `reviewer`, `editor`, `form_filling`, `custom_filter`. Resolution order (see
`get_documents_permissions`): owner → per-user role → internal-users default → fallback `viewer`. A role can only lower
what standard Odoo write access allows, never raise it.

## Route authentication summary

| Route kind                    | Required checks                                                                                                                                             |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `auth="user"` UI endpoint     | model ACLs + attachment `validate_access`                                                                                                                   |
| `auth="public"` file/callback | `oo_security_token` → user; Document Server JWT if enabled; then ACL checks as that user                                                                    |
| Share links                   | 17: `documents.share` token via `_get_documents_and_check_access`; 18/19: the share model is gone — use the documents access/permission API of that version |

## Final security checklist (run for every change)

- [ ] New models have ACL lines; new menus/actions restricted to right groups
- [ ] No new `sudo()` without a one-line justification comment
- [ ] Public routes: token validated before any ORM read
- [ ] JWT: incoming tokens decoded and used instead of raw body
- [ ] No secrets (JWT secrets, tokens) in logs or error messages
- [ ] User-controlled strings sanitized before entering configs/filenames
- [ ] Access errors raise `Forbidden`/`AccessError`, not generic 200 responses
