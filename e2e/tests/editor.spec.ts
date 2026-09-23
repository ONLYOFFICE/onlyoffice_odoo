// Copyright (C) 2026 Ascensio System SIA
import { expect, test } from "../fixtures"
import { postFileToNewChannel, type PostedFile } from "../helpers/discuss"
import { typeInEditor, waitForEditor } from "../helpers/editor"
import { PARAM, SAVE_GRACE_MS, template } from "../helpers/env"
import { officeText } from "../helpers/office"
import type { Odoo } from "../helpers/odoo"

/** The attachment is saved back 5 s after leaving the editor (see SAVE_GRACE_MS) and contains the typed text. */
async function expectSaved(odoo: Odoo, { attachment }: PostedFile, text: string) {
  const leftAt = Date.now()
  await expect
    .poll(() => odoo.read("ir.attachment", attachment.id, "checksum"), { timeout: 5_000 + SAVE_GRACE_MS })
    .not.toBe(attachment.checksum)
  test.info().annotations.push({ type: "save-latency", description: `${Date.now() - leftAt} ms` })
  const file = Buffer.from(await odoo.read("ir.attachment", attachment.id, "datas"), "base64")
  expect(await officeText(file)).toContain(text)
}

for (const format of ["docx", "xlsx", "pptx"] as const) {
  test(`open ${format} from Discuss in a new tab, type, close the tab → file is saved`, async ({
    page,
    context,
    odoo,
  }) => {
    const marker = `E2E-${format}-${Date.now()}`
    const posted = await postFileToNewChannel(page, odoo, template(format), marker)

    const [editor] = await Promise.all([context.waitForEvent("page"), posted.openButton.click()])
    await typeInEditor(editor, format, marker)
    await editor.close()

    await expectSaved(odoo, posted, marker)
  })
}

test("open rtf (view-only format) from Discuss → editor is read-only, no save callback", async ({
  page,
  context,
  odoo,
}) => {
  const rtf = { name: "e2e.rtf", mimeType: "application/rtf", buffer: Buffer.from("{\\rtf1\\ansi View only}") }
  const posted = await postFileToNewChannel(page, odoo, rtf, "e2e rtf")

  const [editor] = await Promise.all([context.waitForEvent("page"), posted.openButton.click()])
  await waitForEditor(editor)

  // Without a callback URL Docs has nowhere to save the file back to.
  const config = await editor.evaluate(() => (window as any).config.editorConfig)
  expect(config.mode).toBe("view")
  expect(config.callbackUrl).toBeUndefined()
})

test.describe("Open file in the same tab", () => {
  test.beforeAll(({ odoo }) => odoo.setParam(PARAM.sameTab, true))
  test.afterAll(({ odoo }) => odoo.setParam(PARAM.sameTab, false))

  test("open docx from Discuss in the same tab, type, go back → file is saved", async ({ page, odoo }) => {
    const marker = `E2E-same-tab-${Date.now()}`
    const posted = await postFileToNewChannel(page, odoo, template("docx"), marker)

    await posted.openButton.click()
    await typeInEditor(page, "docx", marker)
    await page.goBack()

    await expectSaved(odoo, posted, marker)
  })
})
