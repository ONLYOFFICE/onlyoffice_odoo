// Copyright (C) 2026 Ascensio System SIA
import type { Page, Route } from "@playwright/test"

import type { Odoo } from "./odoo"

/** A form of the gallery that points to a PDF this Odoo serves itself: downloading it needs no internet. */
export const GALLERY_FORM_URL = "http://localhost:8069/onlyoffice/template/template_content/hr.employee_Employee.pdf"

const FORM_FILES_URL = "onlyoffice_connector.form_files_url"

/**
 * Runs `test` with the folder of GALLERY_FORM_URL set as a mirror of the gallery files (the server takes forms only
 * from them), removed whatever happens: a later run must not download from this Odoo.
 */
export async function withFormFilesMirror(odoo: Odoo, test: () => Promise<void>) {
  await odoo.call("ir.config_parameter", "set_param", [FORM_FILES_URL, GALLERY_FORM_URL.replace(/[^/]*$/, "")])
  try {
    await test()
  } finally {
    await odoo.call("ir.config_parameter", "set_param", [FORM_FILES_URL, false])
  }
}

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
