/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { loadBundle } from "@web/core/assets"

/**
 * A list of the data without its sort (made through the API, not by Odoo) is loaded by Odoo, but its exportData
 * fails on it: the sort is empty, as Odoo reads it.
 * @param {Object} data the spreadsheet data.
 */
function addMissingListSort(data) {
  for (const list of Object.values(data?.lists || {})) {
    if (list && !Array.isArray(list.orderBy)) {
      list.orderBy = []
    }
  }
}

/**
 * The data with the revisions applied; when Odoo cannot export it, nothing: the server then takes the last snapshot.
 * @param {Object} model the spreadsheet model.
 * @returns {Object|undefined} the data, or undefined. // eslint-disable-line jsdoc/check-types
 */
function exportDataOrNothing(model) {
  try {
    return model.exportData()
  } catch (error) {
    console.warn("The spreadsheet data could not be exported, the last snapshot is used:", error)
    return undefined
  }
}

/**
 * Export an Odoo Spreadsheet with the native o-spreadsheet engine, so charts
 * and other advanced formatting are kept. Throws if the export fails.
 * @param {Object} env the environment of the component that exports.
 * @param {Number} id documents.document id of the Odoo Spreadsheet.
 * @returns {Promise<{base64: string, name: string, data: Object, sheetNames: string[]}>} the file, and the data
 * it was made from (revisions applied) with its sheet names as the export wrote them.
 */
export async function exportSpreadsheetNativeXlsx(env, id) {
  await loadBundle("spreadsheet.o_spreadsheet")
  const { createSpreadsheetModel, waitForDataLoaded } = odoo.loader.modules.get("@spreadsheet/helpers/model")
  // Odoo 19 has no join_spreadsheet_session: the data and revisions come as the spreadsheet action gets them.
  const record = await env.services.http.get(`/spreadsheet/data/documents.document/${id}`)
  addMissingListSort(record.data)
  const model = await createSpreadsheetModel({
    data: record.data,
    env,
    revisions: record.revisions,
  })
  await waitForDataLoaded(model)
  const xlsxData = model.exportXLSX()

  const formData = new URLSearchParams({
    files: JSON.stringify(xlsxData.files),
    zip_name: `${record.name}.xlsx`,
  })
  if (odoo.csrf_token) {
    formData.append("csrf_token", odoo.csrf_token)
  }

  const response = await fetch("/spreadsheet/xlsx", {
    body: formData,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    method: "POST",
  })
  if (!response.ok) {
    throw new Error("Failed to export spreadsheet to XLSX")
  }
  const xlsxBlob = await response.blob()

  const base64 = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result.split(",")[1])
    reader.onerror = reject
    reader.readAsDataURL(xlsxBlob)
  })
  // Sheet names as written in the file: Excel cuts a name to 31 characters.
  const workbook = xlsxData.files.find((file) => file.path === "xl/workbook.xml")
  let sheetNames = []
  if (workbook) {
    const workbookXml = new DOMParser().parseFromString(workbook.content, "application/xml")
    sheetNames = Array.from(workbookXml.getElementsByTagName("sheet"), (sheet) => sheet.getAttribute("name"))
  }
  return {
    base64,
    data: exportDataOrNothing(model),
    name: record.name,
    sheetNames,
  }
}
