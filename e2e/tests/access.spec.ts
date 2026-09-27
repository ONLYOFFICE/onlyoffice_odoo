// Copyright (C) 2026 Ascensio System SIA
import { readFileSync } from "node:fs"

import { expect, test } from "../fixtures"
import { postFileToNewChannel } from "../helpers/discuss"
import { template } from "../helpers/env"
import { DB } from "../helpers/odoo"

test("post a zip to Discuss → no Open in ONLYOFFICE button", async ({ page, odoo }) => {
  const zip = { name: "e2e.zip", mimeType: "application/zip", buffer: Buffer.from("not an office file") }
  const posted = await postFileToNewChannel(page, odoo, zip, "e2e zip")

  await expect(page.locator(".o-mail-Message .o-mail-AttachmentCard")).toBeVisible()
  await expect(posted.openButton).toHaveCount(0)
})

test("open the editor link of a file in someone else's private chat → 403, no editor", async ({ browser, odoo }) => {
  const channelId = await odoo.call<number>("discuss.channel", "create", [
    { name: "e2e private", channel_type: "group" },
  ])
  const attachmentId = await odoo.call<number>("ir.attachment", "create", [
    {
      name: "private.docx",
      datas: readFileSync(template("docx")).toString("base64"),
      res_model: "discuss.channel",
      res_id: channelId,
    },
  ])
  const login = `e2e-outsider-${Date.now()}`
  await odoo.call("res.users", "create", [{ name: login, login, password: login }])

  // An empty storage state: otherwise the context inherits (and the login would take over) the admin session.
  const outsider = await browser.newContext({ storageState: { cookies: [], origins: [] } })
  await outsider.request.post("/web/session/authenticate", {
    data: { jsonrpc: "2.0", params: { db: DB, login, password: login } },
  })
  const page = await outsider.newPage()

  const response = await page.goto(`/onlyoffice/editor/${attachmentId}`)
  expect(response?.status()).toBe(403)
  await expect(page.locator("body")).toContainText(`${login} (id=`) // denied as this user, not as a visitor
  await outsider.close()
})
