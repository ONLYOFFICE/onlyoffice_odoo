// Copyright (C) 2026 Ascensio System SIA
import { expect, type Page } from "@playwright/test"

import type { OfficeFormat } from "./discuss"

/** Where a click lands in the blank template at the 1440x900 viewport: page body, a cell, the title placeholder. */
const CLICK_AT: Record<OfficeFormat, { x: number; y: number }> = {
  docx: { x: 700, y: 250 },
  xlsx: { x: 260, y: 160 },
  pptx: { x: 790, y: 290 },
}

/** Waits for the editor: `DocsAPI.DocEditor("doceditor", …)` replaces the `#doceditor` placeholder with this iframe. */
export async function waitForEditor(page: Page) {
  const frame = page.frameLocator('iframe[name="frameEditor"]')
  await expect(frame.locator("#toolbar")).toBeVisible({ timeout: 120_000 })
  return frame
}

/** Types `text` through the editor canvas and gives the change time to reach Docs. */
export async function typeInEditor(page: Page, format: OfficeFormat, text: string) {
  const frame = await waitForEditor(page)
  await page.waitForTimeout(2_000) // the SDK keeps initialising after the toolbar is shown

  await frame.locator("#editor_sdk").click({ position: CLICK_AT[format] })
  await page.keyboard.type(text, { delay: 25 })
  if (format === "xlsx") {
    await page.keyboard.press("Enter") // commit the cell
  }
  await page.waitForTimeout(3_000)
}
