// Copyright (C) 2026 Ascensio System SIA
import path from "node:path"

import { test as base } from "@playwright/test"

import { Odoo } from "./helpers/odoo"

/** Session of the administrator, saved by `tests/auth.setup.ts` and reused by the other projects. */
export const AUTH_FILE = path.resolve(__dirname, ".auth/admin.json")

export const test = base.extend<object, { odoo: Odoo }>({
  odoo: [async ({}, use) => use(new Odoo()), { scope: "worker" }],
})

export { expect } from "@playwright/test"
