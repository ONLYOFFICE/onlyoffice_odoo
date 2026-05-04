// Copyright (C) 2026 Ascensio System SIA

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
      var accessToken = window.odooAccessToken

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
      Asc.scope.odooAccessToken = accessToken
      Asc.scope.odooServerUrl = window.location.origin

      connector.callCommand(() => {
        var documentId = Asc.scope.odooDocumentId
        var accessToken = Asc.scope.odooAccessToken
        var serverUrl = Asc.scope.odooServerUrl

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
            _pendingFormulas.push({ formula: formula, resolve: resolve })
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
                      access_token: accessToken,
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
                    for (var i = 0; i < batch.length; i++) batch[i].resolve("#ERROR: " + e.message)
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
            _pendingFormulas.push({ formula: formula, resolve: resolve })
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
                      access_token: accessToken,
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
                    for (var i = 0; i < batch.length; i++) batch[i].resolve("#ERROR: " + e.message)
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
            if (arguments[i] === undefined || arguments[i] === null) break
            var a = arguments[i]
            parts.push(typeof a === "string" ? '"' + a + '"' : a)
          }
          var formula = "=ODOO_PIVOT(" + parts.join(",") + ")"
          return new Promise(function (resolve) {
            _pendingFormulas.push({ formula: formula, resolve: resolve })
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
                      access_token: accessToken,
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
                    for (var i = 0; i < batch.length; i++) batch[i].resolve("#ERROR: " + e.message)
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
            if (arguments[i] === undefined || arguments[i] === null) break
            var a = arguments[i]
            parts.push(typeof a === "string" ? '"' + a + '"' : a)
          }
          var formula = "=ODOO_PIVOT_HEADER(" + parts.join(",") + ")"
          return new Promise(function (resolve) {
            _pendingFormulas.push({ formula: formula, resolve: resolve })
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
                      access_token: accessToken,
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
                    for (var i = 0; i < batch.length; i++) batch[i].resolve("#ERROR: " + e.message)
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
          if (rowCount !== undefined && rowCount !== null) parts.push(rowCount)
          if (includeTotal !== undefined && includeTotal !== null) parts.push(includeTotal)
          if (includeColumnTitles !== undefined && includeColumnTitles !== null) parts.push(includeColumnTitles)
          var formula = "=ODOO_PIVOT_TABLE(" + parts.join(",") + ")"
          return new Promise(function (resolve) {
            _pendingFormulas.push({ formula: formula, resolve: resolve })
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
                      access_token: accessToken,
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
                    for (var i = 0; i < batch.length; i++) batch[i].resolve("#ERROR: " + e.message)
                  })
              }, 50)
            }
          })
        }

        /**
         * Get the current value of an Odoo spreadsheet filter.
         * @customfunction
         * @param {string} filterName The label of the filter.
         * @returns {string} The current filter value.
         */
        async function ODOO_FILTER_VALUE(filterName) {
          var formula = '=ODOO_FILTER_VALUE("' + filterName + '")'
          return new Promise(function (resolve) {
            _pendingFormulas.push({ formula: formula, resolve: resolve })
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
                      access_token: accessToken,
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
                    for (var i = 0; i < batch.length; i++) batch[i].resolve("#ERROR: " + e.message)
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
          if (date !== undefined && date !== null) parts.push('"' + date + '"')
          var formula = "=ODOO_CURRENCY_RATE(" + parts.join(",") + ")"
          return new Promise(function (resolve) {
            _pendingFormulas.push({ formula: formula, resolve: resolve })
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
                      access_token: accessToken,
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
                    for (var i = 0; i < batch.length; i++) batch[i].resolve("#ERROR: " + e.message)
                  })
              }, 50)
            }
          })
        }

        // Register all functions with ONLYOFFICE API
        Api.AddCustomFunction(ODOO_LIST)
        Api.AddCustomFunction(ODOO_LIST_HEADER)
        Api.AddCustomFunction(ODOO_PIVOT)
        Api.AddCustomFunction(ODOO_PIVOT_HEADER)
        Api.AddCustomFunction(ODOO_PIVOT_POSITION)
        Api.AddCustomFunction(ODOO_PIVOT_TABLE)
        Api.AddCustomFunction(ODOO_FILTER_VALUE)
        Api.AddCustomFunction(ODOO_CURRENCY_RATE)
      })

      // Force recalculation after a delay so that cells which evaluated
      // before the custom functions were registered (#NAME? errors) get
      // re-evaluated with the now-available functions.
      setTimeout(function () {
        try {
          connector.callCommand(function () {
            // Empty command — with default isNoCalc=false this triggers
            // a full recalculation of all formulas in the spreadsheet.
          })
        } catch (e) {
          console.warn("ODOO recalculation trigger failed:", e)
        }
      }, 3000)
    } catch (error) {
      console.warn("ODOO custom functions not available:", error.message)
    }
  }
})()
