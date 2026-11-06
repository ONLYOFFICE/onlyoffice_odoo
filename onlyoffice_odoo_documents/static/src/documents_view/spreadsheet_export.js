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
 * The value of an argument of a formula, as the spreadsheet computes it, or the default when there is none.
 * @param {Object} model the spreadsheet model.
 * @param {String} sheetId the sheet of the formula.
 * @param {Object} arg the argument (an AST node), or undefined.
 * @param {*} defaultValue the value of a missing argument.
 * @returns {*} the value; an Error when it is an error.
 */
function argumentValue(model, sheetId, arg, defaultValue) {
  if (!arg) {
    return defaultValue
  }
  const { astToFormula } = odoo.loader.modules.get("@odoo/o-spreadsheet")
  try {
    const value = model.getters.evaluateFormula(sheetId, "=" + astToFormula(arg))
    return value && typeof value === "object" ? new Error(String(value.value || value.message)) : value
  } catch (error) {
    return error instanceof Error ? error : new Error(String(error))
  }
}

/**
 * The cells of a dynamic pivot (ODOO.PIVOT.TABLE) as Odoo shows the table: its title, then a ODOO.PIVOT.HEADER or
 * ODOO.PIVOT formula per cell, as a pivot inserted from Odoo. Null when Odoo shows an error instead.
 * @param {Object} model the spreadsheet model, its data loaded.
 * @param {String} sheetId the sheet of the formula.
 * @param {Object} call the ODOO.PIVOT.TABLE call (an AST node).
 * @returns {String[][]|null} the content of the cells, column by column.
 */
function dynamicPivotCells(model, sheetId, call) {
  const { makePivotFormula } = odoo.loader.modules.get("@spreadsheet/pivot/pivot_helpers")
  const [pivotArg, rowCountArg, totalArg, titlesArg] = call.args
  const pivotId = argumentValue(model, sheetId, pivotArg)
  const rowCount = argumentValue(model, sheetId, rowCountArg, 10000)
  const includeTotal = argumentValue(model, sheetId, totalArg, true)
  const includeTitles = argumentValue(model, sheetId, titlesArg, true)
  if ([pivotId, rowCount, includeTotal, includeTitles].some((value) => value instanceof Error)) {
    return null
  }
  if (!model.getters.getPivotIds().includes(String(pivotId)) || !(Number(rowCount) >= 0)) {
    return null
  }
  // As ODOO.PIVOT.TABLE of Odoo 17 (pivot_functions.js).
  const id = String(pivotId)
  const table = model.getters.getPivotTableStructure(id)
  const pivotCells = table.getPivotCells(Boolean(includeTotal), Boolean(includeTitles))
  const headerRows = includeTitles ? table.getNumberOfHeaderRows() : 0
  const title = model.getters.getPivotDisplayName(id)
  const end = Math.min(headerRows + Number(rowCount), pivotCells[0].length)
  if (end === 0) {
    return [[title]]
  }
  const cells = []
  for (const column of pivotCells) {
    const contents = []
    for (const pivotCell of column.slice(0, end)) {
      if (!pivotCell.domain) {
        contents.push("")
        continue
      }
      const args = pivotCell.isHeader ? [id, ...pivotCell.domain] : [id, pivotCell.measure, ...pivotCell.domain]
      contents.push(makePivotFormula(pivotCell.isHeader ? "ODOO.PIVOT.HEADER" : "ODOO.PIVOT", args))
    }
    cells.push(contents)
  }
  if (includeTitles) {
    cells[0][0] = title
  }
  return cells
}

/**
 * Add the columns or rows a sheet needs to have ``count`` of them.
 * @param {Object} model the spreadsheet model.
 * @param {String} sheetId the sheet.
 * @param {String} dimension "COL" or "ROW".
 * @param {Number} count the number of columns or rows needed.
 */
function addMissing(model, sheetId, dimension, count) {
  const current = dimension === "COL" ? model.getters.getNumberCols(sheetId) : model.getters.getNumberRows(sheetId)
  if (count > current) {
    model.dispatch("ADD_COLUMNS_ROWS", {
      base: current - 1,
      dimension,
      position: "after",
      quantity: count - current,
      sheetId,
      sheetName: model.getters.getSheetName(sheetId),
    })
  }
}

/**
 * Each dynamic pivot (one ODOO.PIVOT.TABLE formula, its table spread over the cells around) becomes the formulas
 * of its cells, as the table is now, like a pivot inserted from Odoo: ONLYOFFICE cannot spread the result of a
 * function. A table whose cells are taken stays as it is (Odoo shows an error). Only the model of the export
 * changes, not the spreadsheet.
 * @param {Object} model the spreadsheet model, its data loaded.
 */
function splitDynamicPivots(model) {
  const { parse } = odoo.loader.modules.get("@odoo/o-spreadsheet")
  for (const sheetId of model.getters.getSheetIds()) {
    const tables = []
    for (const cell of Object.values(model.getters.getCells(sheetId))) {
      if (!cell.isFormula || !/^=\s*ODOO\.PIVOT\.TABLE\s*\(/i.test(cell.content)) {
        continue
      }
      const call = parse(cell.content)
      if (call.type !== "FUNCALL" || call.value.toUpperCase() !== "ODOO.PIVOT.TABLE") {
        continue
      }
      const cells = dynamicPivotCells(model, sheetId, call)
      if (cells) {
        tables.push({
          cells,
          position: model.getters.getCellPosition(cell.id),
        })
      }
    }
    for (const { cells, position } of tables) {
      const targets = []
      cells.forEach((column, col) => {
        column.forEach((content, row) => {
          targets.push({
            col: position.col + col,
            content,
            own: !col && !row,
            row: position.row + row,
          })
        })
      })
      // The cells the table spreads over, its own cell aside, must be free.
      const isTaken = (target) => {
        if (target.own) {
          return false
        }
        const cell = model.getters.getCell({
          col: target.col,
          row: target.row,
          sheetId,
        })
        return Boolean(cell?.content)
      }
      if (targets.some(isTaken)) {
        continue
      }
      addMissing(model, sheetId, "COL", position.col + cells.length)
      addMissing(model, sheetId, "ROW", position.row + cells[0].length)
      for (const { col, content, own, row } of targets) {
        if (content || own) {
          model.dispatch("UPDATE_CELL", {
            col,
            content,
            row,
            sheetId,
          })
        }
      }
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
  const record = await env.services.orm.call("documents.document", "join_spreadsheet_session", [id])
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
