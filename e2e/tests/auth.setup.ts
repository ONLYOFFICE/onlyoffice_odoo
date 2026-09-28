// Copyright (C) 2026 Ascensio System SIA
import { expect, test as setup } from "@playwright/test"

import { AUTH_FILE } from "../fixtures"

setup("log in as admin", async ({ page }) => {
  await page.goto("/web/login")
  await page.locator("#login").fill("admin")
  await page.locator("#password").fill("admin")
  await page.getByRole("button", { name: "Log in", exact: true }).click()
  await expect(page.locator(".o_navbar")).toBeVisible()
  await page.context().storageState({ path: AUTH_FILE })
})
