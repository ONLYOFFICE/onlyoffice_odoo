---
name: odoo-owl-assets
description:
  OWL components, XML templates, asset bundles, registries, and services for the ONLYOFFICE Odoo frontend (static/src).
  Use for JS/OWL work in any of the three modules, including editor open buttons, dialogs, and Documents view patches.
---

# OWL and Assets

## Where frontend code lives

- `onlyoffice_odoo/static/src/` — editor open action, attachment/chatter integration, generic components, CSS.
- `onlyoffice_odoo_documents/static/src/` — Documents kanban/list patches, create-file dialog, share dialog,
  desktop-mode scripts.
- `onlyoffice_odoo_templates/static/src/` — template form view widgets, report action patch
  (`action_manager_report.esm.js`).

Bundles are declared in each `__manifest__.py` under `assets["web.assets_backend"]`. New files must match an existing
glob or be added there explicitly. After changing globs, restart with `-u <module>`.

## Component pattern

Base skeleton (works on 17/18/19; version deltas are in the table below):

```javascript
/** @odoo-module **/ // required on 17, optional on 18/19

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

## Common services here

- `orm` — model calls (`this.orm.call("ir.attachment", ...)`)
- rpc for custom JSON routes such as `/onlyoffice/editor/get_config`:
  - 17: `this.rpc = useService("rpc")`
  - 18/19: `import { rpc } from "@web/core/network/rpc"` (no service)
- `action` — open the editor: `doAction` with `ir.actions.act_url` or a client action; respect the "open in same tab"
  setting (`same_tab` param)
- `notification`, `dialog` — feedback and modals

## Patching existing views (Documents app)

Use `patch` from `@web/core/utils/patch` to extend Enterprise components (kanban controller, inspector). Keep patches
minimal: add methods, do not rewrite `setup` when a hook can be appended. Version-sensitive — these break most often
during 18/19 ports, so keep each patch in its own file with a comment naming the patched component.

## Version notes (for ports)

| Topic                         | 17                   | 18                                            | 19                                                                        |
| ----------------------------- | -------------------- | --------------------------------------------- | ------------------------------------------------------------------------- |
| OWL                           | 2.x                  | 2.x                                           | 3.x (stricter props, check breaking changes)                              |
| `/** @odoo-module **/` header | required             | optional                                      | optional                                                                  |
| rpc                           | `useService("rpc")`  | `rpc` import from `@web/core/network/rpc`     | same as 18                                                                |
| Documents app JS              | 17 structure         | reworked (access model, no `documents.share`) | reworked again — re-check every patch                                     |
| Props declarations            | plain or object form | same                                          | object form expected (`{ type, required/optional }`), stricter validation |

On every branch, open the same-version source of the patched component before changing a patch; do not assume a
selector/method from another version still exists.

## Checklist

- [ ] File covered by a manifest asset glob
- [ ] Template name prefixed with the module name
- [ ] Props declared with types; no implicit props
- [ ] Services via `useService`, no global imports of legacy widgets
- [ ] Patches isolated per file and documented
- [ ] Tested with an actual editor open/save round trip
