---
name: odoo-owl-assets
description:
  OWL components, XML templates, asset bundles, registries, patches of Enterprise Documents components, and the editor
  Automation API usage in the ONLYOFFICE Odoo frontend (static/src of all three modules). Use for JS/OWL work, including
  editor open buttons, dialogs, Documents view patches, report handlers and scripts loaded outside the bundle.
---

# OWL and Assets

## Where frontend code lives

Per-file maps are in the module skills (`onlyoffice-odoo-base` / `-documents` / `-templates`, section `static/src/`).
What matters for JS work across modules:

| Module                      | Extension points used                                                                                                                                                                                                                                                                                                                                                                                            | Asset bundle (`web.assets_backend`)                                                                                                                                                                                                                                        |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `onlyoffice_odoo`           | client action `onlyoffice_editor` (`registry…add(..., { force: true })`); `patch(AttachmentList)` + `t-inherit="mail.AttachmentList"`; shared dialogs `FormGallery`, `OnlyofficePreview`                                                                                                                                                                                                                         | `actions/*`, `components/*/*.xml`, `models/*.js`, `views/**/*`, `css/*`. `js/odoo_custom_functions_init.js` is **deliberately outside** the bundle (raw `<script>` / `loadScript`): the minifier strips the JSDoc `@customfunction` comments `Api.AddCustomFunction` needs |
| `onlyoffice_odoo_documents` | `patch(DocumentsKanbanController/ListController)` via a mixin + `t-inherit="documents.DocumentsViews.ControlPanel"`; `patch(DocumentsInspector)` + `t-inherit="documents.DocumentsInspector.buttons"`; `OnlyofficeSelectorPanel extends SpreadsheetSelectorPanel` + `patch(SpreadsheetSelectorDialog)`; `patch(DocumentsKanbanRecord)`; services `desktop_restriction`, `desktop_auth` (Desktop Editors UA only) | listed explicitly and in order (desktop scripts first, then `models/*.js`, `components/*/*.xml`, `documents_view/**/*`, `onlyoffice_create_template/**/*`, `spreadsheet_selector/**/*`, `css/*.css`). A new top-level `css/*.scss` would not match                         |
| `onlyoffice_odoo_templates` | client action `onlyoffice_template_editor`; `patch(FormController/ListController).getStaticActionMenuItems`; view `onlyoffice_kanban` (`registry.category("views")`); field widget `onlyoffice_template_tree` (`registry.category("fields")`); `registry.category("ir.actions.report handlers")` for `onlyoffice-pdf`; `env.bus` events `onlyoffice-template-*`                                                  | `css/*`, `views/**/*`, `js/report/action_manager_report.esm.js`                                                                                                                                                                                                            |

New files must match an existing glob or be added to the manifest explicitly. After changing globs, restart with
`-u <module>`.

## Component pattern

Base skeleton for 17/18/19 (Odoo 20 uses Owl 3 — see "Owl 3 (Odoo 20)" below; other deltas are in the version table):

```javascript
/** @odoo-module **/ // required on 17, optional on 18/19
// Copyright (C) 2026 Ascensio System SIA

import { Component, useState, onWillStart } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { registry } from "@web/core/registry"

export class MyComponent extends Component {
  static template = "onlyoffice_odoo.MyComponent"
  static props = {
    attachmentId: { type: Number, required: true },
    close: { type: Function, optional: true },
  }

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.state = useState({ loading: true })
    onWillStart(async () => await this.load())
  }
}
```

Template file next to it, registered by the manifest glob:

```xml
<templates xml:space="preserve">
  <t t-name="onlyoffice_odoo.MyComponent">
    <div class="oo_my_component">...</div>
  </t>
</templates>
```

Existing code uses both `import { Component } from "@odoo/owl"` and `const { Component, useState } = owl`; new code
should import from `@odoo/owl` and declare `static template` / `static props` / `static components` (older files set
`MyComponent.template = ...` after the class — either is accepted by lint, but do not mix styles inside one file).

## Owl 3 (Odoo 20)

Odoo 20 ships Owl 3 with a thin compatibility layer (`web/static/src/owl2/owl3_compatibility_layer.js`: `useEnv`,
`useSubEnv`, `useLayoutEffect`, `onWillRender`, portals). Everything else must be written the Owl 3 way:

```javascript
import { Component, onWillStart, proxy, signal, t, useProps } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"

export class MyComponent extends Component {
  static template = "onlyoffice_odoo.MyComponent"
  props = useProps({ attachmentId: t.number(), close: t.function().optional() }) // or useProps() for "any props"

  setup() {
    this.orm = useService("orm")
    this.state = proxy({ loading: true }) // was useState
    this.inputRef = signal.ref() // was useRef("input"); read it as this.inputRef(), not .el
    onWillStart(async () => await this.load())
  }
}
```

```xml
<t t-name="onlyoffice_odoo.MyComponent">
  <input t-ref="this.inputRef" t-att-value="this.state.name" t-on-input="(ev) => this.state.name = ev.target.value" />
  <span t-out="this.props.attachmentId" />
</t>
```

- No `useState`, `useRef`, `useChildSubEnv` (use `useSubEnv`); `static props` / `static defaultProps` **throw**. A
  component without `useProps` has no `this.props`. Inherited props come from the parent class's `useProps`.
- Templates have no implicit component scope: every member is `this.xxx` (state, props, methods, getters). Bare names
  are loop variables (`t-as`), `t-set` values, slot scope or globals (`Object`, `Math`). Prop bindings keep `.bind`:
  `onUpdate.bind="this.onPageChange"`.
- `t-esc` is deprecated → `t-out`. `t-model` only accepts a signal (`signal("")` with `.set`); for `proxy` state use
  `t-att-value` + `t-on-input`, as core does. `t-foreach` over a number throws.
- xpath anchors of inherited core/Enterprise templates contain `this.` too (`//DropdownItem[@onSelected='this.onX']`). A
  non-matching xpath breaks the whole view with an unrelated-looking error
  (`Cannot read properties of undefined (reading 'push')` in `initiateRender`).
- `useAutofocus({ ref: signal.ref() })` needs an explicit ref. Services can still be used through `useService`; the
  legacy `registry.category("services")` and `env.services` keep working, but `env.debug` / `env.isSmall` throw.
- Notifications validate `type`: only `info`, `success`, `warning`, `danger` (`"error"` throws).
- Renders are scheduled with `requestAnimationFrame`: in a hidden/background browser nothing re-renders (headless test
  runs are fine).

## Icons (Odoo 20)

Font Awesome is not loaded anymore: `fa fa-*` classes render nothing. Use Material Symbols through the `oi` class —
`<i class="oi" data-icon="folder"/>`, sizes `oi-2x`/`oi-3x`/`oi-4x`, `oi-fw`, `oi-spin` (spinner:
`data-icon="autorenew"`), `oi-filled`. View buttons and action menu items take the bare name (`icon="edit"`,
`icon: "print"`). The font is a **subset**: check that a name renders (e.g. `language` does not — use `translate`). CSS
that swapped a glyph with a Font Awesome code point (`content: "\f058"`) must use the ligature name
(`content: "check_circle"`).

## Common services and calls

- `orm` — model calls: `this.orm.call("onlyoffice.odoo", "get_same_tab")`, `advanced_share_data`,
  `get_fields_for_model`, `join_spreadsheet_session`, ...
- rpc for custom JSON routes (`/onlyoffice/editor/get_config`, `/onlyoffice/documents/file/create`, ...):
  - 17: `this.rpc = useService("rpc")` (or `this.env.services.rpc`)
  - 18/19/20: `import { rpc } from "@web/core/network/rpc"` (no service)
  - Several routes return a JSON string — the client does `JSON.parse(json)`; keep that when touching either side.
- `action` — open the editor:
  `doAction({ type: "ir.actions.client", tag: "onlyoffice_editor", target: "current", params: { attachment_id | document_id } })`
  when `same_tab` is on, otherwise `window.open("/onlyoffice/editor/...")`. Desktop Editors (`AscDesktopEditor` UA)
  always use the new-tab URL.
- `notification`, `dialog`, `ui` (`ui.block/unblock` around long conversions), `router` (`pushState` of ids in the
  editor actions).
- Downloads: `download({ url, data })` from `@web/core/network/download` (templates fill, report handler); base64 → Blob
  for the convert dialog.

## Editor Automation API (connector)

Used by the template editor and the spreadsheet functions:

- `window.docEditor = new DocsAPI.DocEditor("doceditor", config)`; `config.events.onDocumentReady` is the hook.
- `const connector = docEditor.createConnector()`; `connector.executeMethod("GetVersion", [], cb)` doubles as a license
  probe (templates show a warning when the Automation API is not licensed and fall back to copying the key).
- `connector.callCommand(() => { ... Api.* ... })` runs inside the editor sandbox: no closures over page variables —
  pass data through `Asc.scope.*`; only `Api`/`Asc` are available; each function must inline what it needs.
- `connector.attachEvent("onClick", ...)` + `executeMethod("GetCurrentContentControlPr", ...)` to read the selected form
  field.
- Clean up on unmount: `connector.disconnect()`, `docEditor.destroyEditor()`, remove the `api.js` script tag, delete
  `window.DocsAPI` (see `TemplateEditor`).

## Patching existing views (Documents app, web client)

Use `patch` from `@web/core/utils/patch` to extend Enterprise/web components (kanban/list controllers, inspector,
spreadsheet selector, form/list controllers, `AttachmentList`). Keep patches minimal: add methods, call
`super.setup(...arguments)`, do not rewrite `setup` when a hook can be appended. For templates, use `t-inherit` with
`t-inherit-mode="extension"` and stable xpath anchors (`hasclass(...)`). Version-sensitive — these break most often
during 18/19 ports, so keep each patch in its own file with the patched component named in an import at the top.

## Version notes (for ports)

| Topic                         | 17                                                                     | 18                                                                | 19                                                                        | 20                                                                              |
| ----------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| OWL                           | 2.x                                                                    | 2.x                                                               | 2.x (stricter props, check breaking changes)                              | 3.x + compat layer — see "Owl 3 (Odoo 20)"                                      |
| `/** @odoo-module **/` header | required                                                               | optional                                                          | optional                                                                  | optional                                                                        |
| rpc                           | `useService("rpc")`                                                    | `rpc` import from `@web/core/network/rpc`                         | same as 18                                                                | same as 18                                                                      |
| Documents app JS              | `DocumentsInspector`, kanban/list controllers, `ShareRoute`            | reworked (access model, no `documents.share`, inspector replaced) | reworked again — re-check every patch                                     | templates use `this.`; "All" section (`getSelectedFolderId()` is `false`)       |
| Spreadsheet selector          | `@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/*` | verify paths and API                                              | verify paths and API                                                      | panel uses `this.domain`, `get_spreadsheets` → `{records, total}`, `model` prop |
| Chatter attachments           | `@mail/core/common/attachment_list`                                    | verify module path and template name                              | verify                                                                    | loops over `attachmentGroups`; `attachment` is a `t-set`                        |
| Props declarations            | plain or object form                                                   | same                                                              | object form expected (`{ type, required/optional }`), stricter validation | `props = useProps({...})` with `t.*`; `static props` throws                     |
| Kanban "New" button           | in `web.KanbanView`                                                    | same                                                              | same                                                                      | separate `web.KanbanView.Buttons`, set via the view's `buttonTemplate`          |
| Icons                         | Font Awesome                                                           | Font Awesome                                                      | Font Awesome                                                              | Material Symbols (`oi` + `data-icon`), see "Icons (Odoo 20)"                    |

On every branch, open the same-version source of the patched component before changing a patch; do not assume a
selector/method from another version still exists.

## Checklist

- [ ] File covered by a manifest asset glob (or intentionally excluded and loaded by `<script>`/`loadScript`, with a
      comment saying why)
- [ ] Template name prefixed with the module name
- [ ] Props declared with types; no implicit props (20: `useProps`, members prefixed with `this.` in templates)
- [ ] Icons exist in the target version's icon font
- [ ] Services via `useService`, no global imports of legacy widgets
- [ ] Patches isolated per file and documented
- [ ] `same_tab` and Desktop Editors behavior respected when opening the editor
- [ ] Editor/connector resources released on unmount
- [ ] Tested with an actual editor open/save round trip
