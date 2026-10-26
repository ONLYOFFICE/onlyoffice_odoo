// Copyright (C) 2026 Ascensio System SIA
// Links of the Documents app (Share → "Anyone with the link" → Copy Link) opened by a visitor and by the "demo" user.
// The administrator generates every link through the Share panel; the rights are read from the editor config.
// Tests of known bugs expect the correct behaviour and are marked as failing (see knownBug); E2E_STRICT=1 runs them as
// plain tests, to see how they fail.
import type { Page } from "@playwright/test"

import { expect, knownBug, test } from "../fixtures"
import { contextOf, demoUser, newDocument, newFolder, openedEditor, shareByLink } from "../helpers/documents"
import type { Odoo } from "../helpers/odoo"

/** What each ONLYOFFICE role allows in the editor: editorConfig.mode and document.permissions. */
const ROLES = {
  view: { mode: "view", permissions: { edit: false } },
  commenter: { mode: "edit", permissions: { edit: false, comment: true } },
  reviewer: { mode: "edit", permissions: { edit: false, review: true } },
  edit: { mode: "edit", permissions: { edit: true } },
  custom_filter: { mode: "edit", permissions: { edit: true, modifyFilter: false } },
  form_filling: { mode: "edit", permissions: { edit: false, fillForms: true } },
} as const
type Role = keyof typeof ROLES

/**
 * Link roles opened by a visitor, one per kind of editor setting: the mapping of every role is unit-tested
 * (onlyoffice_odoo_documents/tests/test_share.py) and saving through an edit link is in documents.spec.ts.
 */
const LINK_ROLES: [Role, string][] = [
  ["view", "docx"],
  ["commenter", "docx"],
  ["custom_filter", "xlsx"],
  ["form_filling", "pdf"],
]

/** Link roles followed by demo: the same bug refuses them all, a read-only and an edit role are enough. */
const DEMO_LINK_ROLES: [Role, string][] = [
  ["view", "docx"],
  ["edit", "docx"],
]

const rights = (config: any) => config && { mode: config.editorConfig.mode, permissions: config.document.permissions }

/** A folder only the administrator can see: whatever is in it is reachable only through the links. */
function privateFolder(odoo: Odoo, name: string) {
  return newFolder(odoo, name, { access_internal: "none" })
}

/** A visitor follows `link`: the portal page of the document or folder. */
async function visit(page: Page, link: string) {
  const response = await page.goto(link)
  expect(response?.status()).toBe(200)
  expect(new URL(page.url()).pathname).toMatch(/^\/documents\//) // /odoo/documents/<token> redirects visitors here
}

for (const [role, ext] of LINK_ROLES) {
  test(`a visitor opens a ${role} link of a ${ext} from its share page → ${role} rights`, async ({
    page,
    browser,
    odoo,
  }) => {
    const marker = `E2E-link-${role}-${Date.now()}`
    const folderId = await privateFolder(odoo, marker)
    await newDocument(odoo, folderId, `${marker}.${ext}`)
    const link = await shareByLink(page, odoo, folderId, `${marker}.${ext}`, role)

    const context = await contextOf(browser)
    const share = await context.newPage()
    await visit(share, link)
    const { config } = await openedEditor(context, () =>
      share.getByRole("link", { name: "Open in ONLYOFFICE" }).click(),
    )

    expect(rights(config)).toEqual(ROLES[role])
    if (role === "view") {
      expect(config.editorConfig.callbackUrl).toBeUndefined()
    } else {
      expect(config.editorConfig.callbackUrl).toContain("/onlyoffice/documents/share/callback/")
    }
    await context.close()
  })
}

/** Closes what the Documents app opens over the list: the preview of a linked document, a dialog. */
async function closeOverlays(page: Page) {
  await page.locator(".o_kanban_record").first().waitFor()
  for (let attempt = 0; attempt < 3 && (await page.locator(".modal, .o-FileViewer").count()); attempt++) {
    await page.keyboard.press("Escape")
    await page.waitForTimeout(500)
  }
}

for (const [role, ext] of DEMO_LINK_ROLES) {
  test(`demo follows a ${role} link of a ${ext} and opens it in ONLYOFFICE → ${role} rights`, async ({
    page,
    browser,
    odoo,
  }) => {
    knownBug("the backend editor ignores the link role, an internal user gets 403")
    const marker = `E2E-demo-link-${role}-${Date.now()}`
    const name = `${marker}.${ext}`
    const folderId = await privateFolder(odoo, marker)
    await newDocument(odoo, folderId, name)
    const link = await shareByLink(page, odoo, folderId, name, role)

    const demo = await contextOf(browser, (await demoUser(odoo)).login)
    const demoPage = await demo.newPage()
    await demoPage.goto(link) // the Documents app, with the document in "Shared with me"
    await closeOverlays(demoPage)
    await demoPage.locator(".o_kanban_record").getByTitle(name, { exact: true }).click()
    const { config, editor } = await openedEditor(demo, () =>
      demoPage.getByRole("button", { name: "Open in ONLYOFFICE" }).click(),
    )

    expect(editor.url()).toContain("/onlyoffice/editor/document/")
    expect(rights(config)).toEqual(ROLES[role])
    await demo.close()
  })
}

for (const folderRole of ["view", "edit"] as const) {
  test(`a visitor opens the documents of a folder shared with ${folderRole} → ${folderRole} rights`, async ({
    page,
    browser,
    odoo,
  }) => {
    const marker = `E2E-folder-${folderRole}-${Date.now()}`
    const boxId = await privateFolder(odoo, `${marker}-box`)
    const folderId = await privateFolder(odoo, marker)
    await odoo.call("documents.document", "write", [[folderId], { folder_id: boxId }])
    await newDocument(odoo, folderId, `${marker}.docx`)
    const link = await shareByLink(page, odoo, boxId, marker, folderRole)

    const context = await contextOf(browser)
    const share = await context.newPage()
    await visit(share, link)
    const card = share.locator("article", { hasText: `${marker}.docx` })
    const { config } = await openedEditor(context, () => card.getByTitle("Open in ONLYOFFICE").click())

    expect(rights(config)).toEqual(ROLES[folderRole])
    await context.close()
  })
}

test("demo opens a folder shared with edit and its document in ONLYOFFICE → edit rights", async ({
  page,
  browser,
  odoo,
}) => {
  const marker = `E2E-demo-folder-${Date.now()}`
  const boxId = await privateFolder(odoo, `${marker}-box`)
  const folderId = await privateFolder(odoo, marker)
  await odoo.call("documents.document", "write", [[folderId], { folder_id: boxId }])
  await newDocument(odoo, folderId, `${marker}.docx`)
  const link = await shareByLink(page, odoo, boxId, marker, "edit")

  const demo = await contextOf(browser, (await demoUser(odoo)).login)
  const demoPage = await demo.newPage()
  await demoPage.goto(link) // the Documents app opened on the folder
  await demoPage.locator(".o_kanban_record").getByTitle(`${marker}.docx`, { exact: true }).click()
  const { config } = await openedEditor(demo, () =>
    demoPage.getByRole("button", { name: "Open in ONLYOFFICE" }).click(),
  )

  expect(rights(config)).toEqual(ROLES.edit)
  await demo.close()
})

/** A folder shared with edit by link, with one document; returns the folder link. */
async function sharedFolderWithDocument(page: Page, odoo: Odoo, marker: string) {
  const boxId = await privateFolder(odoo, `${marker}-box`)
  const folderId = await privateFolder(odoo, marker)
  await odoo.call("documents.document", "write", [[folderId], { folder_id: boxId }])
  await newDocument(odoo, folderId, `${marker}.docx`)
  return { folderId, folderLink: await shareByLink(page, odoo, boxId, marker, "edit") }
}

for (const role of ["view", "commenter"] as const) {
  test(`a ${role} document in a folder shared with edit opens from the folder page with ${role} rights`, async ({
    page,
    browser,
    odoo,
  }) => {
    knownBug("opened from the folder page, a document gets the folder role instead of its own")
    const marker = `E2E-own-${role}-${Date.now()}`
    const { folderId, folderLink } = await sharedFolderWithDocument(page, odoo, marker)
    await shareByLink(page, odoo, folderId, `${marker}.docx`, role)

    const context = await contextOf(browser)
    const share = await context.newPage()
    await visit(share, folderLink)
    const card = share.locator("article", { hasText: `${marker}.docx` })
    const { config } = await openedEditor(context, () => card.getByTitle("Open in ONLYOFFICE").click())

    expect(rights(config)).toEqual(ROLES[role])
    await context.close()
  })
}

test("the link of a document that inherits edit from its shared folder opens with edit rights", async ({
  page,
  browser,
  odoo,
}) => {
  knownBug("without its own ONLYOFFICE role, a document link always opens read-only")
  const marker = `E2E-inherited-${Date.now()}`
  const { folderId } = await sharedFolderWithDocument(page, odoo, marker)
  const link = await shareByLink(page, odoo, folderId, `${marker}.docx`) // Copy Link, rights unchanged

  const context = await contextOf(browser)
  const share = await context.newPage()
  await visit(share, link)
  const { config } = await openedEditor(context, () => share.getByRole("link", { name: "Open in ONLYOFFICE" }).click())

  expect(rights(config)).toEqual(ROLES.edit)
  await context.close()
})

test("a document hidden from the link in a shared folder is neither listed nor opened", async ({
  page,
  browser,
  odoo,
}) => {
  const marker = `E2E-hidden-${Date.now()}`
  const { folderId, folderLink } = await sharedFolderWithDocument(page, odoo, marker)
  await shareByLink(page, odoo, folderId, `${marker}.docx`, "none")
  const [documentId] = await odoo.call<number[]>("documents.document", "search", [[["name", "=", `${marker}.docx`]]])
  const token = await odoo.read("documents.document", documentId, "access_token")
  const folderToken = new URL(folderLink).pathname.split("/").pop()

  const context = await contextOf(browser)
  const share = await context.newPage()
  await visit(share, folderLink)
  await expect(share.locator("article", { hasText: `${marker}.docx` })).toHaveCount(0)
  for (const url of [
    `/onlyoffice/documents/share/${token}/`,
    `/onlyoffice/documents/share/${token}/?folder_token=${folderToken}`,
  ]) {
    expect((await share.goto(url))?.status(), url).toBe(404)
  }
  await context.close()
})
