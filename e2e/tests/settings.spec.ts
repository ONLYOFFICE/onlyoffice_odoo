// Copyright (C) 2026 Ascensio System SIA
import type { Page } from "@playwright/test"

import { expect, test } from "../fixtures"
import { DOC_SERVER, PARAM } from "../helpers/env"

const UNREACHABLE = "http://localhost:9/"

const field = (page: Page, name: string) => page.locator(`[name="${name}"] input`)

// The negative case runs first: the positive one leaves Docs connected for the editor tests.
test.describe.configure({ mode: "serial" })

test.beforeEach(async ({ page }) => {
  await page.goto("/web#action=onlyoffice_odoo.action_onlyoffice_config_settings")
})

test("save an unreachable Docs address → validation error, address is not stored", async ({ page, odoo }) => {
  await field(page, "doc_server_public_url").fill(UNREACHABLE)
  await field(page, "doc_server_inner_url").fill("") // the form prefills it with the reachable default
  await page.getByRole("button", { name: "Save" }).click()

  await expect(page.getByRole("dialog")).toContainText("ONLYOFFICE cannot be reached")
  expect(await odoo.getParam(PARAM.publicUrl)).not.toBe(UNREACHABLE)
})

test("save the Docs connection → validation passes, settings are stored", async ({ page, odoo }) => {
  await field(page, "doc_server_public_url").fill(DOC_SERVER.publicUrl)
  await field(page, "doc_server_inner_url").fill(DOC_SERVER.innerUrl)
  await field(page, "doc_server_odoo_url").fill(DOC_SERVER.odooUrl)
  await field(page, "doc_server_jwt_secret").fill(DOC_SERVER.jwtSecret)
  await page.getByRole("button", { name: "Save" }).click()

  // Saving runs healthcheck, CommandService and a test conversion before the values are written.
  await expect.poll(() => odoo.getParam(PARAM.publicUrl), { timeout: 60_000 }).toBe(DOC_SERVER.publicUrl)
})
