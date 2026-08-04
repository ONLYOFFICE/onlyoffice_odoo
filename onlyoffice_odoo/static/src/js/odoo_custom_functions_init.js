// Copyright (C) 2026 Ascensio System SIA
/* eslint-disable */

/**
 * ODOO Custom Functions Initializer for ONLYOFFICE Editor
 * This script initializes custom functions when the document is ready
 */

;(function () {
  "use strict"

  // Wait for document ready event from ONLYOFFICE
  window.initializeOdooCustomFunctions = async function () {
    try {
      // Check if we have a document_id (for spreadsheets with ODOO formulas)
      var documentId = window.odooDocumentId
      var jwtToken = window.odooJwtToken
      var filterValues = window.odooFilterValues || {}

      if (!documentId) {
        console.log("No document_id found, skipping ODOO custom functions")
        return
      }

      console.log("Initializing ODOO custom functions for document:", documentId)

      // Wait for docEditor to be available
      if (!window.docEditor) {
        console.warn("docEditor not found")
        return
      }

      // Create connector
      var connector = window.docEditor.createConnector()
      window.connector = connector

      // Pass data via Asc.scope
      Asc.scope.odooDocumentId = documentId
      Asc.scope.odooJwtToken = jwtToken
      Asc.scope.odooServerUrl = window.location.origin
      Asc.scope.odooFilterValues = filterValues

      connector.callCommand(() => {
        var documentId = Asc.scope.odooDocumentId
        var jwtToken = Asc.scope.odooJwtToken
        var serverUrl = Asc.scope.odooServerUrl
        var filterValues = Asc.scope.odooFilterValues || {}

        // Batch queue: collects formulas and sends them in one HTTP request.
        // Each function must inline its own fetch logic (OnlyOffice requirement).
        var _pendingFormulas = []
        var _flushTimer = null

        /**
         * Get the value from an Odoo list.
         * @customfunction
         * @param {number} listId ID of the list.
         * @param {number} index Position of the record in the list (1-based).
         * @param {string} fieldName Name of the field.
         * @returns {string} The value from the list.
         */
        async function ODOO_LIST(listId, index, fieldName) {
          var formula = "=ODOO_LIST(" + listId + "," + index + ',"' + fieldName + '")'
          return new Promise(function (resolve) {
            _pendingFormulas.push({
              formula: formula,
              resolve: resolve,
            })
            if (_flushTimer === null) {
              _flushTimer = setTimeout(function () {
                var batch = _pendingFormulas.splice(0)
                _flushTimer = null
                fetch(serverUrl + "/onlyoffice/documents/evaluate_formulas_batch", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                      document_id: documentId,
                      formulas: batch.map(function (b) {
                        return b.formula
                      }),
                      jwt_token: jwtToken,
                    },
                  }),
                })
                  .then(function (r) {
                    return r.json()
                  })
                  .then(function (data) {
                    var v = data.result && data.result.values ? data.result.values : {}
                    for (var i = 0; i < batch.length; i++) {
                      var val = v[batch[i].formula]
                      batch[i].resolve(val !== undefined && val !== null ? val : "")
                    }
                  })
                  .catch(function (e) {
                    for (var i = 0; i < batch.length; i++) {
                      batch[i].resolve("#ERROR: " + e.message)
                    }
                  })
              }, 50)
            }
          })
        }

        /**
         * Get the header of a list.
         * @customfunction
         * @param {number} listId ID of the list.
         * @param {string} fieldName Name of the field.
         * @returns {string} The header value.
         */
        async function ODOO_LIST_HEADER(listId, fieldName) {
          var formula = "=ODOO_LIST_HEADER(" + listId + ',"' + fieldName + '")'
          return new Promise(function (resolve) {
            _pendingFormulas.push({
              formula: formula,
              resolve: resolve,
            })
            if (_flushTimer === null) {
              _flushTimer = setTimeout(function () {
                var batch = _pendingFormulas.splice(0)
                _flushTimer = null
                fetch(serverUrl + "/onlyoffice/documents/evaluate_formulas_batch", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                      document_id: documentId,
                      formulas: batch.map(function (b) {
                        return b.formula
                      }),
                      jwt_token: jwtToken,
                    },
                  }),
                })
                  .then(function (r) {
                    return r.json()
                  })
                  .then(function (data) {
                    var v = data.result && data.result.values ? data.result.values : {}
                    for (var i = 0; i < batch.length; i++) {
                      var val = v[batch[i].formula]
                      batch[i].resolve(val !== undefined && val !== null ? val : "")
                    }
                  })
                  .catch(function (e) {
                    for (var i = 0; i < batch.length; i++) {
                      batch[i].resolve("#ERROR: " + e.message)
                    }
                  })
              }, 50)
            }
          })
        }

        /**
         * Get the value from an Odoo pivot.
         * @customfunction
         * @param {number} pivotId ID of the pivot.
         * @param {string} measure Name of the measure.
         * @param {string} [domain_field_1] First group-by field name.
         * @param {string} [domain_value_1] First group-by value.
         * @param {string} [domain_field_2] Second group-by field name.
         * @param {string} [domain_value_2] Second group-by value.
         * @param {string} [domain_field_3] Third group-by field name.
         * @param {string} [domain_value_3] Third group-by value.
         * @param {string} [domain_field_4] Fourth group-by field name.
         * @param {string} [domain_value_4] Fourth group-by value.
         * @param {string} [domain_field_5] Fifth group-by field name.
         * @param {string} [domain_value_5] Fifth group-by value.
         * @param {string} [domain_field_6] Sixth group-by field name.
         * @param {string} [domain_value_6] Sixth group-by value.
         * @param {string} [domain_field_7] Seventh group-by field name.
         * @param {string} [domain_value_7] Seventh group-by value.
         * @param {string} [domain_field_8] Eighth group-by field name.
         * @param {string} [domain_value_8] Eighth group-by value.
         * @param {string} [domain_field_9] Ninth group-by field name.
         * @param {string} [domain_value_9] Ninth group-by value.
         * @param {string} [domain_field_10] Tenth group-by field name.
         * @param {string} [domain_value_10] Tenth group-by value.
         * @returns {number} The aggregated pivot value.
         */
        async function ODOO_PIVOT(
          pivotId,
          measure,
          domain_field_1,
          domain_value_1,
          domain_field_2,
          domain_value_2,
          domain_field_3,
          domain_value_3,
          domain_field_4,
          domain_value_4,
          domain_field_5,
          domain_value_5,
          domain_field_6,
          domain_value_6,
          domain_field_7,
          domain_value_7,
          domain_field_8,
          domain_value_8,
          domain_field_9,
          domain_value_9,
          domain_field_10,
          domain_value_10,
        ) {
          var parts = [pivotId, '"' + measure + '"']
          for (var i = 2; i < arguments.length; i++) {
            if (arguments[i] === undefined || arguments[i] === null) {
              break
            }
            var a = arguments[i]
            parts.push(typeof a === "string" ? '"' + a + '"' : a)
          }
          var formula = "=ODOO_PIVOT(" + parts.join(",") + ")"
          return new Promise(function (resolve) {
            _pendingFormulas.push({
              formula: formula,
              resolve: resolve,
            })
            if (_flushTimer === null) {
              _flushTimer = setTimeout(function () {
                var batch = _pendingFormulas.splice(0)
                _flushTimer = null
                fetch(serverUrl + "/onlyoffice/documents/evaluate_formulas_batch", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                      document_id: documentId,
                      formulas: batch.map(function (b) {
                        return b.formula
                      }),
                      jwt_token: jwtToken,
                    },
                  }),
                })
                  .then(function (r) {
                    return r.json()
                  })
                  .then(function (data) {
                    var v = data.result && data.result.values ? data.result.values : {}
                    for (var i = 0; i < batch.length; i++) {
                      var val = v[batch[i].formula]
                      batch[i].resolve(val !== undefined && val !== null ? val : "")
                    }
                  })
                  .catch(function (e) {
                    for (var i = 0; i < batch.length; i++) {
                      batch[i].resolve("#ERROR: " + e.message)
                    }
                  })
              }, 50)
            }
          })
        }

        /**
         * Get the header of a pivot group.
         * @customfunction
         * @param {number} pivotId ID of the pivot.
         * @param {string} [domain_field_1] First group-by field name.
         * @param {string} [domain_value_1] First group-by value.
         * @param {string} [domain_field_2] Second group-by field name.
         * @param {string} [domain_value_2] Second group-by value.
         * @param {string} [domain_field_3] Third group-by field name.
         * @param {string} [domain_value_3] Third group-by value.
         * @param {string} [domain_field_4] Fourth group-by field name.
         * @param {string} [domain_value_4] Fourth group-by value.
         * @param {string} [domain_field_5] Fifth group-by field name.
         * @param {string} [domain_value_5] Fifth group-by value.
         * @param {string} [domain_field_6] Sixth group-by field name.
         * @param {string} [domain_value_6] Sixth group-by value.
         * @param {string} [domain_field_7] Seventh group-by field name.
         * @param {string} [domain_value_7] Seventh group-by value.
         * @param {string} [domain_field_8] Eighth group-by field name.
         * @param {string} [domain_value_8] Eighth group-by value.
         * @param {string} [domain_field_9] Ninth group-by field name.
         * @param {string} [domain_value_9] Ninth group-by value.
         * @param {string} [domain_field_10] Tenth group-by field name.
         * @param {string} [domain_value_10] Tenth group-by value.
         * @returns {string} The header display value.
         */
        async function ODOO_PIVOT_HEADER(
          pivotId,
          domain_field_1,
          domain_value_1,
          domain_field_2,
          domain_value_2,
          domain_field_3,
          domain_value_3,
          domain_field_4,
          domain_value_4,
          domain_field_5,
          domain_value_5,
          domain_field_6,
          domain_value_6,
          domain_field_7,
          domain_value_7,
          domain_field_8,
          domain_value_8,
          domain_field_9,
          domain_value_9,
          domain_field_10,
          domain_value_10,
        ) {
          var parts = [pivotId]
          for (var i = 1; i < arguments.length; i++) {
            if (arguments[i] === undefined || arguments[i] === null) {
              break
            }
            var a = arguments[i]
            parts.push(typeof a === "string" ? '"' + a + '"' : a)
          }
          var formula = "=ODOO_PIVOT_HEADER(" + parts.join(",") + ")"
          return new Promise(function (resolve) {
            _pendingFormulas.push({
              formula: formula,
              resolve: resolve,
            })
            if (_flushTimer === null) {
              _flushTimer = setTimeout(function () {
                var batch = _pendingFormulas.splice(0)
                _flushTimer = null
                fetch(serverUrl + "/onlyoffice/documents/evaluate_formulas_batch", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                      document_id: documentId,
                      formulas: batch.map(function (b) {
                        return b.formula
                      }),
                      jwt_token: jwtToken,
                    },
                  }),
                })
                  .then(function (r) {
                    return r.json()
                  })
                  .then(function (data) {
                    var v = data.result && data.result.values ? data.result.values : {}
                    for (var i = 0; i < batch.length; i++) {
                      var val = v[batch[i].formula]
                      batch[i].resolve(val !== undefined && val !== null ? val : "")
                    }
                  })
                  .catch(function (e) {
                    for (var i = 0; i < batch.length; i++) {
                      batch[i].resolve("#ERROR: " + e.message)
                    }
                  })
              }, 50)
            }
          })
        }

        /**
         * Get the absolute ID of an element at a given position in the pivot.
         * @customfunction
         * @param {number} pivotId ID of the pivot.
         * @param {string} fieldName Field name.
         * @param {number} position Position index.
         * @returns {string} The element ID.
         */
        function ODOO_PIVOT_POSITION(pivotId, fieldName, position) {
          return "#ERROR: ODOO_PIVOT_POSITION cannot be called from the spreadsheet"
        }

        /**
         * Get a full pivot table as a 2D range.
         * @customfunction
         * @param {number} pivotId ID of the pivot.
         * @param {number} [rowCount] Maximum number of data rows.
         * @param {number} [includeTotal] Include totals (1 or 0).
         * @param {number} [includeColumnTitles] Include column titles (1 or 0).
         * @returns {string} The pivot table data.
         */
        async function ODOO_PIVOT_TABLE(pivotId, rowCount, includeTotal, includeColumnTitles) {
          var parts = [pivotId]
          if (rowCount !== undefined && rowCount !== null) {
            parts.push(rowCount)
          }
          if (includeTotal !== undefined && includeTotal !== null) {
            parts.push(includeTotal)
          }
          if (includeColumnTitles !== undefined && includeColumnTitles !== null) {
            parts.push(includeColumnTitles)
          }
          var formula = "=ODOO_PIVOT_TABLE(" + parts.join(",") + ")"
          return new Promise(function (resolve) {
            _pendingFormulas.push({
              formula: formula,
              resolve: resolve,
            })
            if (_flushTimer === null) {
              _flushTimer = setTimeout(function () {
                var batch = _pendingFormulas.splice(0)
                _flushTimer = null
                fetch(serverUrl + "/onlyoffice/documents/evaluate_formulas_batch", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                      document_id: documentId,
                      formulas: batch.map(function (b) {
                        return b.formula
                      }),
                      jwt_token: jwtToken,
                    },
                  }),
                })
                  .then(function (r) {
                    return r.json()
                  })
                  .then(function (data) {
                    var v = data.result && data.result.values ? data.result.values : {}
                    for (var i = 0; i < batch.length; i++) {
                      var val = v[batch[i].formula]
                      batch[i].resolve(val !== undefined && val !== null ? val : "")
                    }
                  })
                  .catch(function (e) {
                    for (var i = 0; i < batch.length; i++) {
                      batch[i].resolve("#ERROR: " + e.message)
                    }
                  })
              }, 50)
            }
          })
        }

        /**
         * Get the current value of an Odoo spreadsheet filter.
         * Resolves synchronously from filter values pre-computed by the server.
         * @customfunction
         * @param {string} filterName The label of the filter.
         * @returns {string} The current filter value.
         */
        async function ODOO_FILTER_VALUE(filterName) {
          if (filterName in filterValues) {
            return filterValues[filterName]
          }
          var formula = '=ODOO_FILTER_VALUE("' + filterName + '")'
          return new Promise(function (resolve) {
            _pendingFormulas.push({
              formula: formula,
              resolve: resolve,
            })
            if (_flushTimer === null) {
              _flushTimer = setTimeout(function () {
                var batch = _pendingFormulas.splice(0)
                _flushTimer = null
                fetch(serverUrl + "/onlyoffice/documents/evaluate_formulas_batch", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                      document_id: documentId,
                      formulas: batch.map(function (b) {
                        return b.formula
                      }),
                      jwt_token: jwtToken,
                    },
                  }),
                })
                  .then(function (r) {
                    return r.json()
                  })
                  .then(function (data) {
                    var v = data.result && data.result.values ? data.result.values : {}
                    for (var i = 0; i < batch.length; i++) {
                      var val = v[batch[i].formula]
                      batch[i].resolve(val !== undefined && val !== null ? val : "")
                    }
                  })
                  .catch(function (e) {
                    for (var i = 0; i < batch.length; i++) {
                      batch[i].resolve("#ERROR: " + e.message)
                    }
                  })
              }, 50)
            }
          })
        }

        /**
         * Get the exchange rate between two currencies.
         * @customfunction
         * @param {string} currencyFrom Source currency code.
         * @param {string} currencyTo Target currency code.
         * @param {string} [date] Date for the rate.
         * @returns {number} The exchange rate.
         */
        async function ODOO_CURRENCY_RATE(currencyFrom, currencyTo, date) {
          var parts = ['"' + currencyFrom + '"', '"' + currencyTo + '"']
          if (date !== undefined && date !== null) {
            parts.push('"' + date + '"')
          }
          var formula = "=ODOO_CURRENCY_RATE(" + parts.join(",") + ")"
          return new Promise(function (resolve) {
            _pendingFormulas.push({
              formula: formula,
              resolve: resolve,
            })
            if (_flushTimer === null) {
              _flushTimer = setTimeout(function () {
                var batch = _pendingFormulas.splice(0)
                _flushTimer = null
                fetch(serverUrl + "/onlyoffice/documents/evaluate_formulas_batch", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                      document_id: documentId,
                      formulas: batch.map(function (b) {
                        return b.formula
                      }),
                      jwt_token: jwtToken,
                    },
                  }),
                })
                  .then(function (r) {
                    return r.json()
                  })
                  .then(function (data) {
                    var v = data.result && data.result.values ? data.result.values : {}
                    for (var i = 0; i < batch.length; i++) {
                      var val = v[batch[i].formula]
                      batch[i].resolve(val !== undefined && val !== null ? val : "")
                    }
                  })
                  .catch(function (e) {
                    for (var i = 0; i < batch.length; i++) {
                      batch[i].resolve("#ERROR: " + e.message)
                    }
                  })
              }, 50)
            }
          })
        }

        Api.AddCustomFunction(ODOO_LIST)
        Api.AddCustomFunction(ODOO_LIST_HEADER)
        Api.AddCustomFunction(ODOO_PIVOT)
        Api.AddCustomFunction(ODOO_PIVOT_HEADER)
        Api.AddCustomFunction(ODOO_PIVOT_POSITION)
        Api.AddCustomFunction(ODOO_PIVOT_TABLE)
        Api.AddCustomFunction(ODOO_FILTER_VALUE)
        Api.AddCustomFunction(ODOO_CURRENCY_RATE)
      })

      // Poll sheets: wait until no #BUSY! cells remain, then check for #NAME?.
      // Returns "busy" / "name_error" / "ok".
      window._odooRetryCount = window._odooRetryCount || 0
      window._odooPollCount = window._odooPollCount || 0

      console.log(
        "[ODOO-CHECK] Starting odooCheckSheets, retryCount=" +
          window._odooRetryCount +
          ", pollCount=" +
          window._odooPollCount,
      )

      function odooCheckSheets() {
        console.log("[ODOO-CHECK] odooCheckSheets() called")
        connector.callCommand(
          function () {
            var sheets = Api.GetSheets()
            var activeSheet = Api.GetActiveSheet()
            var activeName = activeSheet.GetName()
            var hasBusy = false
            var hasName = false
            for (var i = 0; i < sheets.length; i++) {
              var sheetName = sheets[i].GetName()
              sheets[i].SetActive()
              var range = sheets[i].GetUsedRange()
              var rangeAddr = range.GetAddress()

              if (!hasBusy) {
                var busyMatch = range.Find({
                  What: "#BUSY!",
                  LookIn: "xlValues",
                  LookAt: "xlWhole",
                })
                if (busyMatch) {
                  var busyAddr = busyMatch.GetAddress()
                  var busyFormula = busyMatch.GetFormula()
                  if (busyFormula && busyFormula.toUpperCase().indexOf("ODOO") !== -1) {
                    hasBusy = true
                  }
                }
              }
              if (!hasName) {
                var nameMatch = range.Find({
                  What: "#NAME?",
                  LookIn: "xlValues",
                  LookAt: "xlWhole",
                })
                if (nameMatch) {
                  var firstAddr = nameMatch.GetAddress()
                  do {
                    var f = nameMatch.GetFormula()
                    if (f && f.toUpperCase().indexOf("ODOO") !== -1) {
                      hasName = true
                      break
                    }
                    nameMatch = range.FindNext(nameMatch)
                  } while (nameMatch && nameMatch.GetAddress() !== firstAddr)
                }
              }
              if (hasBusy) {
                break
              }
            }
            // Restore original active sheet
            for (var j = 0; j < sheets.length; j++) {
              if (sheets[j].GetName() === activeName) {
                sheets[j].SetActive()
                break
              }
            }
            var result = hasBusy ? "busy" : hasName ? "name_error" : "ok"
            return result
          },
          function (status) {
            console.log("[ODOO-CHECK] callback fired, status=" + JSON.stringify(status) + ", type=" + typeof status)
            if (status === "busy" && window._odooPollCount < 10) {
              window._odooPollCount++
              console.log("[ODOO-CHECK] #BUSY! detected, polling... (" + window._odooPollCount + "/10)")
              setTimeout(odooCheckSheets, 2000)
            } else if (status === "name_error" && window._odooRetryCount < 3) {
              window._odooRetryCount++
              window._odooPollCount = 0
              console.log(
                "[ODOO-CHECK] #NAME? errors detected, retrying registration (attempt " + window._odooRetryCount + "/3)",
              )
              window.initializeOdooCustomFunctions()
            } else {
              console.log(
                "[ODOO-CHECK] Done. status=" +
                  JSON.stringify(status) +
                  " retryCount=" +
                  window._odooRetryCount +
                  " pollCount=" +
                  window._odooPollCount,
              )
            }
          },
        )
      }
      odooCheckSheets()
    } catch (error) {
      console.warn("ODOO custom functions not available:", error.message)
    }
  }
})()
