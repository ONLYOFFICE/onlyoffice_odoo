// Copyright (C) 2026 Ascensio System SIA
import type { Page, Route } from "@playwright/test"

/** A form of the gallery that points to a PDF this Odoo serves itself: downloading it needs no internet. */
export const GALLERY_FORM_URL = "http://localhost:8069/onlyoffice/template/template_content/hr.employee_Employee.pdf"

/**
 * Stubs the form gallery API (oforms.onlyoffice.com, proxied by /onlyoffice/oforms*) with one form named `name`.
 * The proxy routes themselves are unit-tested in onlyoffice_odoo/tests/test_oforms.py.
 */
export async function stubFormGallery(page: Page, name: string) {
  const form = {
    id: 1,
    attributes: {
      name_form: name,
      file_oform: { data: [{ attributes: { url: GALLERY_FORM_URL, ext: ".pdf" } }] },
    },
  }
  const reply = (result: unknown) => (route: Route) =>
    route.fulfill({ json: { jsonrpc: "2.0", id: route.request().postDataJSON().id, result } })
  await page.route("**/onlyoffice/oforms/locales", reply({ data: [{ code: "en", name: "English" }] }))
  await page.route("**/onlyoffice/oforms/category-types", reply({ data: [] }))
  await page.route("**/onlyoffice/oforms", reply({ data: [form], meta: { pagination: { total: 1 } } }))
}

/** Picks the form named `name` in the open gallery dialog and confirms it. */
export async function pickGalleryForm(page: Page, name: string) {
  const gallery = page.getByRole("dialog").filter({ has: page.locator(".o_onlyoffice_kanban_record") })
  await gallery.locator(".o_onlyoffice_kanban_record", { hasText: name }).getByTitle("Select document").click()
  await gallery.getByRole("button", { name: "Create" }).click()
}
