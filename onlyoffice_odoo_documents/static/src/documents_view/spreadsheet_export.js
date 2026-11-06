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
 * Each dynamic pivot (one PIVOT formula, its table spread over the cells around) becomes the formulas of its cells,
 * as "Convert to individual formulas" of Odoo does: ONLYOFFICE cannot spread the result of a function. A table that
 * cannot spread (cells around taken) stays as it is, as Odoo shows an error. Only the model of the export changes,
 * not the spreadsheet.
 * @param {Object} model the spreadsheet model, its data loaded.
 */
function splitDynamicPivots(model) {
  const pivotFormulas = []
  for (const sheetId of model.getters.getSheetIds()) {
    for (const cell of Object.values(model.getters.getCells(sheetId))) {
      if (cell.isFormula && /^=\s*PIVOT\s*\(/i.test(cell.content)) {
        pivotFormulas.push(model.getters.getCellPosition(cell.id))
      }
    }
  }
  for (const position of pivotFormulas) {
    // The table is spread once the formula is computed; an error (cells around taken) is left as Odoo shows it.
    const evaluated = model.getters.getEvaluatedCell(position)
    const pivotId = model.getters.getPivotIdFromPosition(position)
    if (!pivotId || evaluated.type === "error") {
      continue
    }
    const pivot = model.getters.getPivot(pivotId)
    pivot.init()
    if (!pivot.isValid()) {
      continue
    }
    model.dispatch("SPLIT_PIVOT_FORMULA", {
      ...position,
      pivotId,
    })
    // The split leaves the corner of the title empty: the title stays, as the table showed it.
    if (typeof evaluated.value === "string" && evaluated.value && !model.getters.getCell(position)?.content) {
      model.dispatch("UPDATE_CELL", {
        ...position,
        content: evaluated.value,
      })
    }
  }
}

/**
 * The data with the revisions applied. When Odoo cannot export it, no data and the failure: the server then takes the
 * last saved snapshot, and the caller tells the user what that means for the file.
 * @param {Object} model the spreadsheet model.
 * @returns {{data: Object|undefined, dataExportFailed: boolean}} the data, or the failure.
 */
function exportSpreadsheetData(model) {
  try {
    return {
      data: model.exportData(),
      dataExportFailed: false,
    }
  } catch (error) {
    console.warn("The spreadsheet data could not be exported, the last snapshot is used:", error)
    return {
      data: undefined,
      dataExportFailed: true,
    }
  }
}

/**
 * Export an Odoo Spreadsheet with the native o-spreadsheet engine, so charts
 * and other advanced formatting are kept. Throws if the export fails.
 * @param {Object} env the environment of the component that exports.
 * @param {Number} id documents.document id of the Odoo Spreadsheet.
 * @returns {Promise<{base64: string, name: string, data: Object, dataExportFailed: boolean, sheetNames: string[]}>}
 * the file, and the data it was made from (revisions applied; undefined with dataExportFailed when Odoo could not
 * export it) with its sheet names as the export wrote them.
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
  splitDynamicPivots(model)
  // The formulas of the split pivots load their data too.
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
    ...exportSpreadsheetData(model),
    name: record.name,
    sheetNames,
  }
}
