// Copyright (C) 2026 Ascensio System SIA
import { readFile } from "node:fs/promises"
import path from "node:path"

import type { FilePayload, Locator, Page, Route } from "@playwright/test"
import JSZip from "jszip"
import { PDFDocument } from "pdf-lib"

import { expect, test } from "../fixtures"
import { waitForEditor } from "../helpers/editor"
import { PARAM } from "../helpers/env"
import type { Odoo } from "../helpers/odoo"

const TEMPLATES = "/web#action=onlyoffice_odoo_templates.action_onlyoffice_odoo_templates"
const EMPLOYEES = "/web#action=hr.open_view_employee_list_my"
const FORM_ACTIONS = ".o_cp_action_menus .dropdown-toggle"
const EMPLOYEE_PDF = path.resolve(__dirname, "../../onlyoffice_odoo_templates/data/templates/hr.employee/Employee.pdf")

/** Opens "Print with ONLYOFFICE" from `menu` and selects "Employee", a demo template installed for hr.employee. */
async function openPrintDialog(page: Page, menu: Locator) {
  await menu.click()
  await page.getByRole("menuitem", { name: "Print with ONLYOFFICE" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.locator('.o_kanban_record_title[title="Employee"]').click()
  return dialog
}

async function download(page: Page, click: () => Promise<void>) {
  const [file] = await Promise.all([page.waitForEvent("download"), click()])
  return { name: file.suggestedFilename(), content: await readFile(await file.path()) }
}

async function print(page: Page, dialog: Locator) {
  return download(page, () => dialog.getByRole("button", { name: "Print", exact: true }).click())
}

async function openPrintDialogOnForm(page: Page, employeeId: number) {
  await page.goto(`${EMPLOYEES}&view_type=form&id=${employeeId}`)
  return openPrintDialog(page, page.locator(FORM_ACTIONS))
}

async function newEmployee(odoo: Odoo, vals: Record<string, string> = {}) {
  const name = `E2E Employee ${Date.now()}`
  return { name, id: await odoo.call<number>("hr.employee", "create", [{ name, ...vals }]) }
}

/** Picks Employee as the template model in the open template form, saves it and returns the template id. */
async function saveTemplateForEmployee(page: Page) {
  await page.locator('[name="template_model_id"] input').fill("Employee")
  await page.getByRole("option", { name: "Employee", exact: true }).click()
  await page.locator(".o_form_button_save").click()
  // Saving a plain PDF converts it through Docs synchronously, and the first conversion on a cold Docs can take over a
  // minute. Wait a bit longer than onlyoffice_request's own 120 s timeout: past that, Odoo would fail the save anyway.
  await expect(page).toHaveURL(/[#&]id=\d+/, { timeout: 150_000 })
  return Number(/[#&]id=(\d+)/.exec(page.url())![1])
}

/** Creates a template through the form; without `file` a blank PDF form is used. */
async function createTemplate(page: Page, name: string, file?: FilePayload) {
  await page.goto(`${TEMPLATES}&view_type=form`)
  await page.locator('[name="name"] input').fill(name)
  if (file) {
    await page.locator('[name="file"] input[type=file]').setInputFiles(file)
  }
  return saveTemplateForEmployee(page)
}

async function templatePdf(odoo: Odoo, templateId: number) {
  const [attachmentId] = await odoo.read<[number, string]>("onlyoffice.odoo.templates", templateId, "attachment_id")
  return Buffer.from(await odoo.read("ir.attachment", attachmentId, "datas"), "base64")
}

test("print an employee from its form → a PDF with the employee's data in the form", async ({ page, odoo }) => {
  const employee = await newEmployee(odoo, { job_title: "E2E Tester", work_email: "e2e@example.com" })
  const [, company] = await odoo.read<[number, string]>("hr.employee", employee.id, "address_id")

  const pdf = await print(page, await openPrintDialogOnForm(page, employee.id))

  expect(pdf.name).toBe(`Employee - ${employee.name}.pdf`)
  const form = (await PDFDocument.load(pdf.content)).getForm()
  expect(form.getTextField("name").getText()).toBe(employee.name)
  expect(form.getTextField("job_title").getText()).toBe("E2E Tester")
  expect(form.getTextField("work_email").getText()).toBe("e2e@example.com")
  expect(form.getTextField("address_id name").getText()).toBe(company) // a field of a related record
})

test("print two employees from the list → a ZIP with one PDF per employee", async ({ page, odoo }) => {
  const name = `E2E Zip ${Date.now()}`
  await odoo.call("hr.employee", "create", [[{ name: `${name} A` }, { name: `${name} B` }]])
  await page.goto(`${EMPLOYEES}&view_type=list`)
  await page.locator(".o_searchview_input").fill(name)
  await page.keyboard.press("Enter")
  await expect(page.locator(".o_data_row")).toHaveCount(2)

  await page.locator("thead .o_list_record_selector input").check()
  const zip = await print(page, await openPrintDialog(page, page.getByRole("button", { name: "Actions" })))

  const files = Object.keys((await JSZip.loadAsync(zip.content)).files).sort()
  expect(files).toEqual([`Employee - ${name} A.pdf`, `Employee - ${name} B.pdf`])
})

test("print an employee through the template's report (onlyoffice-pdf) → a filled PDF", async ({ page, odoo }) => {
  const [templateId] = await odoo.call<number[]>("onlyoffice.odoo.templates", "search", [[["name", "=", "Employee"]]])
  await odoo.call("onlyoffice.odoo.templates", "create_action", [[templateId]]) // "Create associated report"
  const employee = await newEmployee(odoo)
  await page.goto(`${EMPLOYEES}&view_type=form&id=${employee.id}`)

  await page.locator(FORM_ACTIONS).click()
  await page.getByText("Print", { exact: true }).click()
  const pdf = await download(page, () => page.getByRole("menuitem", { name: "Employee Print (ONLYOFFICE)" }).click())

  const form = (await PDFDocument.load(pdf.content)).getForm()
  expect(form.getTextField("name").getText()).toBe(employee.name)
})

test.describe("Disable form fields after printing", () => {
  test.beforeAll(({ odoo }) => odoo.setParam(PARAM.disableFormFields, true))
  test.afterAll(({ odoo }) => odoo.setParam(PARAM.disableFormFields, false))

  test("print an employee → the PDF has no fillable form fields left", async ({ page, odoo }) => {
    const pdf = await print(page, await openPrintDialogOnForm(page, (await newEmployee(odoo)).id))
    expect((await PDFDocument.load(pdf.content)).getForm().getFields()).toHaveLength(0)
  })
})

test("preview a template in the print dialog → the viewer opens", async ({ page, odoo }) => {
  const dialog = await openPrintDialogOnForm(page, (await newEmployee(odoo)).id)

  await dialog.getByRole("button", { name: "Preview" }).click()
  const viewer = page.frameLocator(".o-onlyoffice-body-iframe").frameLocator('iframe[name="frameEditor"]')
  await expect(viewer.locator("#editor_sdk")).toBeVisible({ timeout: 120_000 })
})

test("create a template from a blank PDF form and open it → editor with the model's fields", async ({ page }) => {
  const name = `E2E blank ${Date.now()}`
  await createTemplate(page, name)

  await page.goto(TEMPLATES)
  await page.locator(".o_kanban_record", { hasText: name }).click()
  await waitForEditor(page)
  await expect(page.locator(".o-onlyoffice-template-fields").getByText("Employee Name", { exact: true })).toBeVisible()
})

test("upload a plain PDF as a template → it is converted into a PDF form", async ({ page, odoo }) => {
  const plain = await PDFDocument.create()
  plain.addPage()
  const id = await createTemplate(page, `E2E plain ${Date.now()}`, {
    name: "plain.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await plain.save()),
  })

  // The signature checked by pdf_utils.is_pdf_form.
  expect((await templatePdf(odoo, id)).includes("ONLYOFFICEFORM")).toBe(true)
})

test("create a template from the form gallery → it holds the chosen form", async ({ page, odoo }) => {
  // The gallery API (oforms.onlyoffice.com, proxied by /onlyoffice/oforms*) is stubbed; the chosen form points to a
  // bundled PDF that this Odoo serves itself, so the server-side download needs no internet. The proxy routes are
  // unit-tested in onlyoffice_odoo/tests/test_oforms.py.
  const form = {
    id: 1,
    attributes: {
      name_form: "E2E gallery form",
      file_oform: {
        data: [
          {
            attributes: {
              url: "http://localhost:8069/onlyoffice/template/template_content/hr.employee_Employee.pdf",
              ext: ".pdf",
            },
          },
        ],
      },
    },
  }
  const reply = (result: unknown) => (route: Route) =>
    route.fulfill({ json: { jsonrpc: "2.0", id: route.request().postDataJSON().id, result } })
  await page.route("**/onlyoffice/oforms/locales", reply({ data: [{ code: "en", name: "English" }] }))
  await page.route("**/onlyoffice/oforms/category-types", reply({ data: [] }))
  await page.route("**/onlyoffice/oforms", reply({ data: [form], meta: { pagination: { total: 1 } } }))

  await page.goto(TEMPLATES)
  await page.getByRole("button", { name: "Open Document templates" }).click()
  const gallery = page.getByRole("dialog")
  await gallery
    .locator(".o_onlyoffice_kanban_record", { hasText: "E2E gallery form" })
    .getByTitle("Select document")
    .click()
  await gallery.getByRole("button", { name: "Create" }).click()

  await expect(page.locator('[name="name"] input')).toHaveValue("E2E gallery form")
  await expect(page.locator('[name="file"]')).toBeHidden() // the file comes from the gallery
  const id = await saveTemplateForEmployee(page)
  expect((await templatePdf(odoo, id)).equals(await readFile(EMPLOYEE_PDF))).toBe(true)
})

test("export a demo template in Settings → it is added to the templates", async ({ page, odoo }) => {
  const count = () => odoo.call<number>("onlyoffice.odoo.templates", "search_count", [[["name", "=", "Certificate"]]])
  const before = await count()

  await page.goto("/web#action=onlyoffice_odoo.action_onlyoffice_config_settings")
  await page.getByRole("button", { name: "Manage templates" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByRole("checkbox", { name: "Certificate.pdf" }).check()
  await dialog.getByRole("button", { name: "Export" }).click()

  await expect.poll(count).toBe(before + 1)
})
