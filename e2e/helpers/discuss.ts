// Copyright (C) 2026 Ascensio System SIA
import type { FilePayload, Locator, Page } from "@playwright/test"

import type { Odoo } from "./odoo"

export type OfficeFormat = "docx" | "xlsx" | "pptx"

export interface PostedFile {
  /** "Open in ONLYOFFICE" button on the attachment card of the posted message. */
  openButton: Locator
  attachment: { id: number; checksum: string }
}

/** Creates a channel and posts `file` (a path or an in-memory file) there. */
export async function postFileToNewChannel(page: Page, odoo: Odoo, file: string | FilePayload, name: string) {
  const channelId = await odoo.call<number>("discuss.channel", "create", [{ name }])
  await page.goto(`/web#action=mail.action_discuss&active_id=discuss.channel_${channelId}`)

  await page.locator(".o-mail-Composer input[type=file]").setInputFiles(file)
  // Send stays disabled until the upload ends; the attachment is linked to the channel by the post request.
  await Promise.all([
    page.waitForResponse("**/mail/message/post"),
    page.getByRole("button", { name: "Send", exact: true }).click(),
  ])

  const [attachment] = await odoo.call<PostedFile["attachment"][]>(
    "ir.attachment",
    "search_read",
    [
      [
        ["res_model", "=", "discuss.channel"],
        ["res_id", "=", channelId],
      ],
    ],
    { fields: ["checksum"] },
  )
  const openButton = page.locator(".o-mail-Message").getByRole("button", { name: "Open in ONLYOFFICE" })
  return { openButton, attachment } satisfies PostedFile
}
