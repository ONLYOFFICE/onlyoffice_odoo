// Copyright (C) 2026 Ascensio System SIA

import { readFile } from "node:fs/promises"
import path from "node:path"

import type { Page } from "@playwright/test"

import { expect, test } from "../fixtures"
import {
  contextOf,
  documentChecksum,
  editorConfig,
  documentFile,
  newDocument,
  newDocumentsUser,
  newFolder,
  newMenuItem,
  openFolder,
  selectDocument,
  xlsxSheets,
} from "../helpers/documents"
import { typeInEditor, waitForEditor } from "../helpers/editor"
import { pickGalleryForm, stubFormGallery } from "../helpers/gallery"
import { PARAM, SAVE_GRACE_MS } from "../helpers/env"
import { type Odoo, rpc } from "../helpers/odoo"
import { officeText } from "../helpers/office"

/** The document is saved back after leaving the editor (see SAVE_GRACE_MS) and contains the typed text. */
async function expectSaved(odoo: Odoo, documentId: number, checksum: string, text: string) {
  const leftAt = Date.now()
  await expect.poll(() => documentChecksum(odoo, documentId), { timeout: 5_000 + SAVE_GRACE_MS }).not.toBe(checksum)
  test.info().annotations.push({ type: "save-latency", description: `${Date.now() - leftAt} ms` })
  expect(await officeText(await documentFile(odoo, documentId))).toContain(text)
}

/** Documents of `folderId` named `name`. */
function inFolder(odoo: Odoo, folderId: number, name: string) {
  return odoo.call<number[]>("documents.document", "search", [
    [
      ["name", "=", name],
      ["folder_id", "=", folderId],
    ],
  ])
}

/** New → "Create with ONLYOFFICE" → Blank: the dialog where the format and the title are chosen. */
async function openBlankCreateDialog(page: Page) {
  await newMenuItem(page, "Create with ONLYOFFICE")
  await page.getByRole("dialog").getByText("Blank", { exact: true }).click()
  await page.getByRole("dialog").getByRole("button", { name: "Create", exact: true }).click()
  return page.getByRole("dialog").filter({ has: page.locator("#title") })
}

/** Contacts named after `marker` in their list view, then the cog menu → Spreadsheet → "Insert list in spreadsheet". */
async function openInsertListDialog(page: Page, odoo: Odoo, marker: string) {
  await odoo.call("res.partner", "create", [
    [
      { name: `${marker} A`, ref: marker },
      { name: `${marker} B`, ref: marker },
    ],
  ])
  await page.goto("/web#action=base.action_partner_form&view_type=list")
  await page.locator(".o_searchview_input").fill(marker)
  await page.keyboard.press("Enter")
  await expect(page.locator(".o_data_row")).toHaveCount(2)
  await page.locator(".o_cp_action_menus button").first().click()
  await page.locator(".o-dropdown--menu").getByText("Spreadsheet", { exact: true }).hover()
  await page.getByText("Insert list in spreadsheet").click()
  return page.getByRole("dialog")
}

test("create a document with ONLYOFFICE in a folder, type, close the tab → saved as a new version", async ({
  page,
  context,
  odoo,
}) => {
  const marker = `E2E-documents-${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  await openFolder(page, odoo, folderId)

  const create = await openBlankCreateDialog(page)
  await create.locator("#title").fill(marker) // a Document (docx) is selected by default
  const [editor] = await Promise.all([
    context.waitForEvent("page"),
    create.getByRole("button", { name: "Create", exact: true }).click(),
  ])

  const [documentId] = await inFolder(odoo, folderId, `${marker}.docx`)
  const checksum = await documentChecksum(odoo, documentId)
  await typeInEditor(editor, "docx", marker)
  await editor.close()

  await expectSaved(odoo, documentId, checksum, marker)
  const previous = await odoo.read<number[]>("documents.document", documentId, "previous_attachment_ids")
  const names = await odoo.call<{ name: string }[]>("ir.attachment", "read", [previous, ["name"]])
  expect(names.map((attachment) => attachment.name)).toEqual([`${marker} (1).docx`])
})

test("open a document from the Documents app → the editor opens in a new tab", async ({ page, context, odoo }) => {
  const marker = `E2E-open-${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  const documentId = await newDocument(odoo, folderId, `${marker}.xlsx`)

  await selectDocument(page, odoo, folderId, `${marker}.xlsx`)
  const [editor] = await Promise.all([
    context.waitForEvent("page"),
    page.getByRole("button", { name: "Open in ONLYOFFICE" }).click(),
  ])

  await waitForEditor(editor)
  expect(editor.url()).toContain(`/onlyoffice/editor/document/${documentId}`)
  expect((await editorConfig(editor)).editorConfig.mode).toBe("edit")
})

test("a colleague gets the ONLYOFFICE role of the document: commenter → comments only, none → 403", async ({
  browser,
  odoo,
}) => {
  const marker = `e2e-colleague-${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  const commented = await newDocument(odoo, folderId, `${marker}.docx`)
  const hidden = await newDocument(odoo, folderId, `${marker}-hidden.docx`)
  const colleague = await newDocumentsUser(odoo, marker)
  await odoo.call("onlyoffice.odoo.documents.access.user", "create", [
    { document_id: commented, user_id: colleague.partnerId, role: "commenter" },
  ])
  await odoo.call("onlyoffice.odoo.documents.access", "create", [{ document_id: hidden, internal_users: "none" }])

  const context = await contextOf(browser, colleague.login)
  const page = await context.newPage()
  await page.goto(`/onlyoffice/editor/document/${commented}`)
  await waitForEditor(page)
  const config = await editorConfig(page)
  expect(config.editorConfig.mode).toBe("edit")
  expect(config.document.permissions).toEqual({ edit: false, comment: true })

  const response = await page.goto(`/onlyoffice/editor/document/${hidden}`)
  expect(response?.status()).toBe(403)
  await context.close()
})

test("a visitor with an edit link opens the document from the share page, types, leaves → saved", async ({
  browser,
  odoo,
}) => {
  const marker = `E2E-link-${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  const documentId = await newDocument(odoo, folderId, `${marker}.docx`, undefined, { access_via_link: "view" })
  await odoo.call("onlyoffice.odoo.documents.access", "create", [{ document_id: documentId, link_access: "edit" }])
  const token = await odoo.read("documents.document", documentId, "access_token")
  const checksum = await documentChecksum(odoo, documentId)

  const context = await contextOf(browser)
  const share = await context.newPage()
  await share.goto(`/documents/${token}`)
  const [editor] = await Promise.all([
    context.waitForEvent("page"),
    share.getByRole("link", { name: "Open in ONLYOFFICE" }).click(),
  ])
  await waitForEditor(editor)
  expect((await editorConfig(editor)).editorConfig.callbackUrl).toContain("/onlyoffice/documents/share/callback/")
  await typeInEditor(editor, "docx", marker)
  await editor.close()

  await expectSaved(odoo, documentId, checksum, marker)
  await context.close()
})

test("convert a docx with ONLYOFFICE → the PDF is saved in the same folder", async ({ page, odoo }) => {
  const marker = `E2E-convert-${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  await newDocument(odoo, folderId, `${marker}.docx`)

  await selectDocument(page, odoo, folderId, `${marker}.docx`)
  await newMenuItem(page, "Convert with ONLYOFFICE")
  const dialog = page.getByRole("dialog")
  await dialog.locator("#onlyoffice-convert-format").selectOption("pdf")
  await expect(dialog.getByLabel("Save to Documents")).toBeChecked()
  await dialog.getByRole("button", { name: "Convert", exact: true }).click()

  const converted = () =>
    odoo.call<number[]>("documents.document", "search", [
      [
        ["name", "=", `${marker}.pdf`],
        ["folder_id", "=", folderId],
      ],
    ])
  await expect.poll(converted, { timeout: 120_000 }).toHaveLength(1)
  const pdf = await documentFile(odoo, (await converted())[0])
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-")
})

test("convert an Odoo spreadsheet to XLSX with formulas → ODOO_LIST cells evaluated by Odoo in the editor", async ({
  page,
  context,
  odoo,
}) => {
  const marker = `e2e-sheet-${Date.now()}`
  await odoo.call("res.partner", "create", [{ name: `${marker} partner`, ref: marker }])
  const folderId = await newFolder(odoo, marker)
  // Version 1 data: the browser migrates it like any new spreadsheet; ODOO.LIST keeps its name in 18.
  const data = {
    version: 1,
    sheets: [{ id: "sheet1", name: "Sheet1", cells: { A1: { content: '=ODOO.LIST(1,1,"name")' } } }],
    lists: {
      1: { id: "1", name: "Partners", model: "res.partner", domain: [["ref", "=", marker]], columns: ["name"] },
    },
  }
  const spreadsheetId = await odoo.call<number>("documents.document", "create", [
    {
      name: marker,
      folder_id: folderId,
      handler: "spreadsheet",
      mimetype: "application/o-spreadsheet",
      spreadsheet_data: JSON.stringify(data),
    },
  ])

  await selectDocument(page, odoo, folderId, marker)
  const evaluated = context.waitForEvent("response", {
    predicate: (response) => response.url().includes("/onlyoffice/documents/evaluate_formulas_batch"),
    timeout: 240_000,
  })
  const [editor] = await Promise.all([
    context.waitForEvent("page", { timeout: 180_000 }), // native export + docbuilder, then the editor opens
    page.getByRole("button", { name: "Convert to ONLYOFFICE XLSX (with formulas)" }).click(),
  ])
  await waitForEditor(editor)

  const [xlsxId] = await odoo.call<number[]>("documents.document", "search", [
    [["onlyoffice_spreadsheet_source_id", "=", spreadsheetId]],
  ])
  const { workbook, sheets } = await xlsxSheets(await documentFile(odoo, xlsxId))
  expect(sheets.Sheet1).toContain('ODOO_LIST(1,1,"name")')
  expect(workbook).toContain('name="_OdooMetadata"')
  const values = (await (await evaluated).json()).result.values
  expect(Object.values(values)).toContain(`${marker} partner`)
})

test("insert an Odoo list into an XLSX → a new sheet of ODOO_LIST formulas", async ({ page, odoo }) => {
  const marker = `e2e-insert-${Date.now()}`
  await odoo.call("res.partner", "create", [
    [
      { name: `${marker} A`, ref: marker },
      { name: `${marker} B`, ref: marker },
    ],
  ])
  const folderId = await newFolder(odoo, marker)
  const documentId = await newDocument(odoo, folderId, `${marker}.xlsx`)

  // The spreadsheet selector of Odoo sends this for "Insert list in spreadsheet" → an ONLYOFFICE XLSX.
  const result = await rpc<Record<string, unknown>>(page, "/onlyoffice/documents/insert_list_in_xlsx", {
    document_id: documentId,
    list_data: { model: "res.partner", domain: `[('ref', '=', '${marker}')]`, columns: [{ name: "name" }] },
    threshold: 2,
    name: "E2E Partners",
  })

  expect(result).toMatchObject({ success: true, id: "1", sheet_name: "E2E Partners" })
  const { workbook, sheets } = await xlsxSheets(await documentFile(odoo, documentId))
  expect(sheets["E2E Partners"]).toContain('ODOO_LIST_HEADER(1,"name")')
  expect(sheets["E2E Partners"]).toContain('ODOO_LIST(1,2,"name")')
  expect(workbook).toContain('name="_OdooMetadata"')
  const metadata = JSON.parse(await odoo.read("documents.document", documentId, "onlyoffice_spreadsheet_metadata"))
  expect(metadata.lists["1"].model).toBe("res.partner")
})

const GALLERY_PDF = path.resolve(__dirname, "../../onlyoffice_odoo_templates/data/templates/hr.employee/Employee.pdf")

for (const [tile, ext, documentType] of [
  ["Spreadsheet", "xlsx", "cell"],
  ["Presentation", "pptx", "slide"],
  ["PDF form", "pdf", "pdf"],
] as const) {
  test(`create a blank ${ext} with ONLYOFFICE → it opens in the editor`, async ({ page, context, odoo }) => {
    const marker = `E2E-create-${ext}-${Date.now()}`
    const folderId = await newFolder(odoo, marker)
    await openFolder(page, odoo, folderId)

    const create = await openBlankCreateDialog(page)
    await create.getByText(tile, { exact: true }).click()
    await create.locator("#title").fill(marker)
    const [editor] = await Promise.all([
      context.waitForEvent("page"),
      create.getByRole("button", { name: "Create", exact: true }).click(),
    ])

    await waitForEditor(editor)
    const config = await editorConfig(editor)
    expect(config.document.fileType).toBe(ext)
    expect(config.documentType).toBe(documentType)
    expect(await inFolder(odoo, folderId, `${marker}.${ext}`)).toHaveLength(1)
  })
}

test("create a document from the form gallery → the chosen form is in the folder", async ({ page, context, odoo }) => {
  const marker = `E2E gallery ${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  await stubFormGallery(page, marker)
  await openFolder(page, odoo, folderId)

  await newMenuItem(page, "Create with ONLYOFFICE")
  await page.getByRole("dialog").getByText("From Template", { exact: true }).click()
  await page.getByRole("dialog").getByRole("button", { name: "Create", exact: true }).click()
  const [editor] = await Promise.all([context.waitForEvent("page"), pickGalleryForm(page, marker)])

  await waitForEditor(editor)
  const [documentId] = await inFolder(odoo, folderId, `${marker}.pdf`)
  expect((await documentFile(odoo, documentId)).equals(await readFile(GALLERY_PDF))).toBe(true)
})

test("Create & Set Permissions creates the document and opens its share panel", async ({ page, odoo }) => {
  const marker = `E2E-permissions-${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  await openFolder(page, odoo, folderId)

  const create = await openBlankCreateDialog(page)
  await create.locator("#title").fill(marker)
  await create.getByRole("button", { name: "Create&Set Permissions" }).click()

  await expect(page.getByRole("dialog").getByText("General access")).toBeVisible()
  expect(await inFolder(odoo, folderId, `${marker}.docx`)).toHaveLength(1)
})

test.describe("Open file in the same tab", () => {
  test.beforeAll(({ odoo }) => odoo.setParam(PARAM.sameTab, true))
  test.afterAll(({ odoo }) => odoo.setParam(PARAM.sameTab, false))

  test("open a document from the Documents app → the editor opens in the app", async ({ page, odoo }) => {
    const marker = `E2E-same-tab-${Date.now()}`
    const folderId = await newFolder(odoo, marker)
    const documentId = await newDocument(odoo, folderId, `${marker}.docx`)

    await selectDocument(page, odoo, folderId, `${marker}.docx`)
    const [config] = await Promise.all([
      page.waitForResponse("**/onlyoffice/editor/get_config").then(async (response) => (await response.json()).result),
      page.getByRole("button", { name: "Open in ONLYOFFICE" }).click(),
    ])

    await waitForEditor(page)
    expect(config.document_id).toBe(documentId)
    expect(page.context().pages()).toHaveLength(1)
  })
})

test("convert a docx with ONLYOFFICE without saving → the PDF is downloaded", async ({ page, odoo }) => {
  const marker = `E2E-convert-download-${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  await newDocument(odoo, folderId, `${marker}.docx`)

  await selectDocument(page, odoo, folderId, `${marker}.docx`)
  await newMenuItem(page, "Convert with ONLYOFFICE")
  const dialog = page.getByRole("dialog")
  await dialog.locator("#onlyoffice-convert-format").selectOption("pdf")
  await dialog.getByLabel("Save to Documents").uncheck()
  const [file] = await Promise.all([
    page.waitForEvent("download", { timeout: 120_000 }),
    dialog.getByRole("button", { name: "Convert", exact: true }).click(),
  ])

  expect(file.suggestedFilename()).toBe(`${marker}.pdf`)
  expect((await readFile(await file.path())).subarray(0, 5).toString()).toBe("%PDF-")
  expect(await inFolder(odoo, folderId, `${marker}.pdf`)).toHaveLength(0)
})

test("open an Odoo spreadsheet in ONLYOFFICE → an XLSX copy with the computed values", async ({
  page,
  context,
  odoo,
}) => {
  const marker = `e2e-sheet-copy-${Date.now()}`
  const [last] = await odoo.call<number[]>("documents.document", "search", [[["handler", "=", "spreadsheet"]]], {
    order: "id desc",
    limit: 1,
  })
  // An Odoo spreadsheet made by Odoo itself: a list of contacts inserted into a blank spreadsheet.
  const dialog = await openInsertListDialog(page, odoo, marker)
  await dialog.getByRole("button", { name: "Confirm" }).click()
  await page.locator(".o-spreadsheet").waitFor()
  const [spreadsheetId] = await odoo.call<number[]>("documents.document", "search", [
    [
      ["handler", "=", "spreadsheet"],
      ["id", ">", last ?? 0],
    ],
  ])
  const folderId = await newFolder(odoo, marker)
  await odoo.call("documents.document", "write", [[spreadsheetId], { folder_id: folderId }])

  await selectDocument(page, odoo, folderId, await odoo.read("documents.document", spreadsheetId, "name"))
  const [editor] = await Promise.all([
    context.waitForEvent("page", { timeout: 120_000 }),
    page.getByRole("button", { name: "Open in ONLYOFFICE" }).click(),
  ])
  await waitForEditor(editor)

  const [copyId] = await odoo.call<number[]>("documents.document", "search", [
    [["onlyoffice_spreadsheet_source_id", "=", spreadsheetId]],
  ])
  const text = await officeText(await documentFile(odoo, copyId))
  expect(text).toContain(`${marker} A`)
  expect(text).toContain(`${marker} B`)
  expect(text).not.toContain("ODOO")
})

test("insert an Odoo pivot into an XLSX → a new sheet of ODOO_PIVOT formulas", async ({ page, odoo }) => {
  const marker = `e2e-pivot-${Date.now()}`
  await odoo.call("res.partner", "create", [
    [
      { name: `${marker} company`, ref: marker, is_company: true },
      { name: `${marker} person`, ref: marker },
    ],
  ])
  const folderId = await newFolder(odoo, marker)
  const documentId = await newDocument(odoo, folderId, `${marker}.xlsx`)

  // "Insert pivot in spreadsheet" of a pivot view → the ONLYOFFICE tab of the spreadsheet selector sends this.
  const result = await rpc<Record<string, unknown>>(page, "/onlyoffice/documents/insert_pivot_in_xlsx", {
    document_id: documentId,
    pivot_data: {
      model: "res.partner",
      domain: [["ref", "=", marker]],
      measures: ["__count"],
      rowGroupBys: ["is_company"],
      colGroupBys: [],
    },
    name: "E2E Pivot",
  })

  expect(result).toMatchObject({ success: true, id: "1", sheet_name: "E2E Pivot" })
  const { sheets } = await xlsxSheets(await documentFile(odoo, documentId))
  expect(sheets["E2E Pivot"]).toContain('ODOO_PIVOT_HEADER(1,"is_company","true")')
  expect(sheets["E2E Pivot"]).toContain('ODOO_PIVOT(1,"__count","is_company","false")')
  expect(sheets["E2E Pivot"]).toContain('ODOO_PIVOT(1,"__count")')
})

test("insert a list of contacts into an XLSX from the ONLYOFFICE tab of the spreadsheet selector", async ({
  page,
  odoo,
}) => {
  const marker = `e2e-selector-${Date.now()}`
  const folderId = await newFolder(odoo, marker)
  const documentId = await newDocument(odoo, folderId, `${marker}.xlsx`)

  const dialog = await openInsertListDialog(page, odoo, marker)
  await dialog.getByText("ONLYOFFICE", { exact: true }).click()
  await dialog
    .locator(".o-spreadsheet-grid", { hasText: `${marker}.xlsx` })
    .locator(".o-spreadsheet-grid-image")
    .click()
  await dialog.getByRole("button", { name: "Confirm" }).click()

  await waitForEditor(page) // the XLSX opens in the editor
  const { sheets } = await xlsxSheets(await documentFile(odoo, documentId))
  const inserted = Object.values(sheets).find((sheet) => sheet.includes("ODOO_LIST("))
  expect(inserted).toContain('ODOO_LIST_HEADER(1,"complete_name")')
  expect(inserted).toContain('ODOO_LIST(1,2,"complete_name")')
  const metadata = JSON.parse(await odoo.read("documents.document", documentId, "onlyoffice_spreadsheet_metadata"))
  expect(metadata.lists["1"].model).toBe("res.partner")
  expect(metadata.lists["1"].domain).toContain(marker) // the search of the list view
})

test("ONLYOFFICE Desktop Editors: the app opens on Documents and signs in to the desktop app", async ({
  browser,
  odoo,
}) => {
  const context = await browser.newContext({
    storageState: test.info().project.use.storageState as string,
    userAgent: "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36 AscDesktopEditor/9.0.0",
  })
  // The desktop app's bridge: records the commands the page sends to it.
  await context.addInitScript(() => {
    const commands: string[][] = []
    ;(window as any).AscDesktopEditor = { execCommand: (...args: string[]) => commands.push(args) }
    ;(window as any).desktopCommands = commands
  })
  const page = await context.newPage()

  await page.goto("/odoo/discuss")
  await expect(page).toHaveURL(/action-documents\.document_action/)
  await expect(page.locator("body")).toHaveClass(/desktop-editor-mode/)
  const [command, params] = (await page.evaluate(() => (window as any).desktopCommands))[0]
  expect(command).toBe("portal:login")
  const [adminId] = await odoo.call<number[]>("res.users", "search", [[["login", "=", "admin"]]])
  expect(JSON.parse(params)).toMatchObject({ provider: "odoo", userId: String(adminId) })

  const response = await page.goto("/Products/Files")
  expect(response?.url()).toContain("action-documents.document_action")
  await context.close()
})
