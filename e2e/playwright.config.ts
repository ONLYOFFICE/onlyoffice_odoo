// Copyright (C) 2026 Ascensio System SIA
import { defineConfig } from "@playwright/test"

import { AUTH_FILE } from "./fixtures"
import { ODOO_URL } from "./helpers/env"

// Projects run in a chain: login -> settings (connects the Document Server) -> editor, templates.
export default defineConfig({
  testDir: "tests",
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 240_000,
  expect: { timeout: 30_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: ODOO_URL,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  projects: [
    { name: "login", testMatch: "auth.setup.ts" },
    { name: "settings", testMatch: "settings.spec.ts", dependencies: ["login"], use: { storageState: AUTH_FILE } },
    {
      name: "editor",
      testMatch: ["editor.spec.ts", "access.spec.ts"],
      dependencies: ["settings"],
      use: { storageState: AUTH_FILE },
    },
    { name: "templates", testMatch: "templates.spec.ts", dependencies: ["settings"], use: { storageState: AUTH_FILE } },
  ],
})
