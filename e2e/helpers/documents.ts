// Copyright (C) 2026 Ascensio System SIA
import { readFileSync } from "node:fs"

import { type Browser, type BrowserContext, expect, type Page } from "@playwright/test"
import JSZip from "jszip"

import { waitForEditor } from "./editor"
import { template } from "./env"
import { DB, type Odoo } from "./odoo"

/** A Documents folder of the administrator, by default editable by all internal users. */
export function newFolder(odoo: Odoo, name: string, vals = {}) {
  return odoo.call<number>("documents.document", "create", [{ name, type: "folder", access_internal: "edit", ...vals }])
}

/** A document in `folderId`; without `content` the blank template of its extension. */
export function newDocument(odoo: Odoo, folderId: number, name: string, content?: Buffer, vals = {}) {
  const file = content ?? readFileSync(template(name.split(".").pop()!))
  return odoo.call<number>("documents.document", "create", [
    { name, folder_id: folderId, datas: file.toString("base64"), ...vals },
  ])
}

/** The current file of a document. */
export async function documentFile(odoo: Odoo, documentId: number) {
  const [attachmentId] = await odoo.read<[number, string]>("documents.document", documentId, "attachment_id")
  return Buffer.from(await odoo.read("ir.attachment", attachmentId, "datas"), "base64")
}

export async function documentChecksum(odoo: Odoo, documentId: number) {
  const [attachmentId] = await odoo.read<[number, string]>("documents.document", documentId, "attachment_id")
  return odoo.read("ir.attachment", attachmentId, "checksum")
}

/** Opens the Documents app on a folder: the internal-user link of the folder (`/odoo/documents/<access_token>`). */
export async function openFolder(page: Page, odoo: Odoo, folderId: number) {
  await page.goto(`/odoo/documents/${await odoo.read("documents.document", folderId, "access_token")}`)
}

/** Opens the folder in the Documents app and selects the document named exactly `name`. */
export async function selectDocument(page: Page, odoo: Odoo, folderId: number, name: string) {
  await openFolder(page, odoo, folderId)
  await page.locator(".o_kanban_record").getByTitle(name, { exact: true }).click()
}

/** An action of the selection in the top bar; Documents 19 moves the ones that do not fit under "More". */
export async function selectionAction(page: Page, name: string) {
  await page.getByRole("button", { name: "Share", exact: true }).waitFor()
  const action = page.getByRole("button", { name, exact: true })
  if (!(await action.isVisible())) {
    await page.getByRole("button", { name: /^More/ }).click()
  }
  await action.click()
}

/**
 * "New" menu of the Documents control panel, where the module adds its "… with ONLYOFFICE" items. In 19 the button name
 * carries its caret icon, and the items are menuitems or plain buttons ("Convert with ONLYOFFICE").
 */
export async function newMenuItem(page: Page, name: string) {
  await page.getByRole("button", { name: /^New\b/ }).click()
  await page.locator(".o-dropdown--menu").getByText(name, { exact: true }).click()
}

/** An internal user of the Documents app, its password is its login. */
export function newDocumentsUser(odoo: Odoo, login: string) {
  return odoo.newUser(login, ["base.group_user", "documents.group_documents_user"])
}

/** The "demo" user of the demo data, created when the database has none (password "demo"). */
export async function demoUser(odoo: Odoo) {
  const [id] = await odoo.call<number[]>("res.users", "search", [[["login", "=", "demo"]]])
  return id ? { id, login: "demo" } : newDocumentsUser(odoo, "demo")
}

/** A browser context of another user (or of a visitor without `login`), not sharing the admin session. */
export async function contextOf(browser: Browser, login?: string) {
  const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
  if (login) {
    await context.request.post("/web/session/authenticate", {
      data: { jsonrpc: "2.0", params: { db: DB, login, password: login } },
    })
  }
  return context
}

/** The config passed to DocsAPI.DocEditor on an editor page; undefined on any other page (403, 404). */
export function editorConfig(page: Page) {
  return page.evaluate(() => (window as any).config)
}

/** The tab opened by `click` and its editor config, once the editor is loaded; no config when access is refused. */
export async function openedEditor(context: BrowserContext, click: () => Promise<void>) {
  const [editor] = await Promise.all([context.waitForEvent("page"), click()])
  await editor.waitForLoadState()
  const config = await editorConfig(editor)
  if (config) {
    await waitForEditor(editor)
  }
  return { config, editor }
}

/**
 * Shares the document or folder named `name` of `folderId` by link through the Share panel of the Documents app:
 * sets "Access through link" to `role` (unless omitted) and returns the link of "Copy Links".
 */
export async function shareByLink(page: Page, odoo: Odoo, folderId: number, name: string, role?: string) {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"])
  await openFolder(page, odoo, folderId)
  // A click opens a folder; Space selects the record whatever its type. Right after the folder opens the key is
  // sometimes lost, so it is pressed again until the selection shows its Share button.
  const card = page.locator(".o_kanban_record").filter({ has: page.getByText(name, { exact: true }) })
  const share = page.getByRole("button", { name: "Share", exact: true })
  await expect(async () => {
    if (!(await share.isVisible())) {
      await card.focus()
      await page.keyboard.press(" ")
    }
    await expect(share).toBeVisible({ timeout: 2_000 })
  }).toPass({ timeout: 30_000 })
  await share.click()

  const dialog = page.getByRole("dialog")
  if (role) {
    // A select menu of the role labels; a change is saved before the link can be copied.
    await dialog.getByRole("textbox", { name: "Access through link" }).click()
    await page
      .locator(".o_select_menu_item")
      .filter({ hasText: new RegExp(`^${ROLE_LABELS[role]}$`) })
      .click()
    await dialog.getByRole("button", { name: "Save", exact: true }).click()
  }
  await dialog.getByRole("button", { name: /Copy Links$/ }).click()
  const link = await page.evaluate(() => navigator.clipboard.readText())
  await dialog.getByRole("button", { name: "Done" }).click()
  return link
}

/** Labels of the roles in the Share dialog. */
const ROLE_LABELS: Record<string, string> = {
  none: "None",
  view: "Viewer",
  edit: "Editor",
  commenter: "Commenter",
  reviewer: "Reviewer",
  form_filling: "Form Filling",
  custom_filter: "Custom Filter",
}

const unescapeXml = (xml: string) =>
  xml
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")

/** The workbook XML of an XLSX and the XML of its sheets by name, with the entities of the text unescaped. */
export async function xlsxSheets(file: Buffer) {
  const zip = await JSZip.loadAsync(file)
  const workbook = await zip.file("xl/workbook.xml")!.async("string")
  const rels = await zip.file("xl/_rels/workbook.xml.rels")!.async("string")
  const sheets: Record<string, string> = {}
  for (const [, name, rId] of workbook.matchAll(/<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"/g)) {
    const target = new RegExp(`Id="${rId}"[^>]*Target="/?(?:xl/)?([^"]+)"`).exec(rels)![1]
    sheets[name] = unescapeXml(await zip.file(`xl/${target}`)!.async("string"))
  }
  return { workbook, sheets }
}
