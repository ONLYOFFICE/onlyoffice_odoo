---
name: onlyoffice-odoo-templates
description:
  Fillable PDF templates module (onlyoffice_odoo_templates) — docbuilder fill flow, field mapping from Odoo records, the
  onlyoffice-pdf report converter. Use for any change inside onlyoffice_odoo_templates.
---

# onlyoffice_odoo_templates

Builds PDFs from Odoo record data through the Document Server docbuilder service. `depends: onlyoffice_odoo, web`.

## Code map

- `models/onlyoffice_odoo_templates.py` — model `onlyoffice.odoo.templates`: name, target `ir.model`, PDF-form
  attachment, cached form field keys (`field_keys`), optional linked report.
- `models/onlyoffice_odoo_demo_templates.py` — demo template seed data model.
- `controllers/controllers.py` — fill flow and template-content route; extends `OnlyofficeConnector`/base controllers
  from `onlyoffice_odoo`.
- `controllers/report_controller.py` — adds the `onlyoffice-pdf` report converter so normal Odoo report buttons can
  print through a template.
- `utils/` — field-mapping and formatting helpers used by the fill flow.
- `static/src/` — template form view widgets, report action patch (`action_manager_report.esm.js`) (see
  `odoo-owl-assets`).

## Fill flow

1. `/onlyoffice/template/fill` → POST to `<docserver>/docbuilder` with a callback URL.
2. The Document Server fetches the generated docbuilder script (public route) and the template PDF, then returns URLs of
   the filled PDFs.
3. Odoo downloads them (single PDF or ZIP).
4. Results can also be saved into the Documents app (`onlyoffice_odoo_documents`, when installed).

## Field mapping

Form keys like `partner_id name` walk relations; values are formatted by user language (dates, floats, monetary,
selections).

## Workflow notes

- New field-mapping types should be added to the shared formatting helpers, not inlined in the controller.
- The `onlyoffice-pdf` report converter must keep working for report buttons defined on any model, not just templates
  explicitly configured for it — test against a report action, not just the fill flow.
- For the general bug-fix/feature workflow and repo-wide rules, see `onlyoffice-odoo-core`.
