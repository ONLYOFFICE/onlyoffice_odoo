/** @odoo-module **/

import { Component, useRef, useState, onWillStart } from "@odoo/owl"
import { CheckBox } from "@web/core/checkbox/checkbox"
import { rpc } from "@web/core/network/rpc"
import { unique } from "@web/core/utils/arrays"
import { useService } from "@web/core/utils/hooks"
import { fuzzyLookup } from "@web/core/utils/search"

class ExportDataItem extends Component {
  setup() {
    this.state = useState({ subfields: [] })
    onWillStart(() => {
      if (this.props.isExpanded) {
        return this.toggleItem(this.props.field, false)
      }
    })
  }

  async toggleItem(field, isUserToggle) {
    const id = field.id
    if (this.props.isFieldExpandable(id)) {
      if (this.state.subfields.length) {
        this.state.subfields = []
      } else {
        const subfields = await this.props.loadFields(id, !isUserToggle)
        if (subfields) {
          this.state.subfields = isUserToggle ? subfields : this.props.filterSubfields(subfields)
        } else {
          this.state.subfields = []
        }
      }
    } else if (isUserToggle) {
      this.env.bus.trigger("onlyoffice-template-create-form", field)
    }
  }
}

ExportDataItem.template = "onlyoffice_odoo_templates.ExportDataItem"
ExportDataItem.components = { ExportDataItem }
ExportDataItem.props = {
  field: {
    optional: true,
    type: Object,
  },
  filterSubfields: Function,
  isExpanded: Boolean,
  isFieldExpandable: Function,
  isTechnicalName: Boolean,
  loadFields: Function,
}

export class ExportData extends Component {
  setup() {
    this.dialog = useService("dialog")
    this.notification = useService("notification")
    this.orm = useService("orm")
    this.rpc = rpc
    this.searchRef = useRef("search")

    this.knownFields = {}
    this.expandedFields = {}

    this.state = useState({
      exportList: [],
      isTechnicalName: false,
      search: [],
    })

    onWillStart(async () => {
      await this.fetchFields()
    })
  }

  get fieldsAvailable() {
    if (this.searchRef.el && this.searchRef.el.value) {
      return this.state.search.length && Object.values(this.state.search)
    }
    return Object.values(this.knownFields)
  }

  get rootFields() {
    if (this.searchRef.el && this.searchRef.el.value) {
      const rootFromSearchResults = this.fieldsAvailable.map((f) => {
        if (f.parent) {
          const parentEl = this.knownFields[f.parent.id]
          return this.knownFields[parentEl.parent ? parentEl.parent.id : parentEl.id]
        }
        return this.knownFields[f.id]
      })
      return unique(rootFromSearchResults)
    }

    return this.fieldsAvailable.filter(({ parent }) => !parent)
  }

  filterSubfields(subfields) {
    let subfieldsFromSearchResults = []
    let searchResults = null
    if (this.searchRef.el && this.searchRef.el.value) {
      searchResults = this.lookup(this.searchRef.el.value)
    }
    const fieldsAvailable = Object.values(searchResults || this.knownFields)
    if (this.searchRef.el && this.searchRef.el.value) {
      subfieldsFromSearchResults = fieldsAvailable
        .filter((f) => f.parent && this.knownFields[f.parent.id].parent)
        .map((f) => f.parent)
    }
    const availableSubFields = unique([...fieldsAvailable, ...subfieldsFromSearchResults])
    return subfields.filter((a) => availableSubFields.some((b) => a.id === b.id))
  }

  async fetchFields() {
    this.state.search = []
    this.knownFields = {}
    this.expandedFields = {}
    await this.loadFields()
    if (this.searchRef.el) {
      this.searchRef.el.value = ""
    }
  }

  isFieldExpandable(id) {
    return this.knownFields[id].children && id.split("/").length < 4
  }

  async loadFields(id, preventLoad = false) {
    let model = this.props.resModel
    let parentField = null
    let parentParams = {}
    if (id) {
      if (this.expandedFields[id]) {
        return this.expandedFields[id].fields
      }
      parentField = this.knownFields[id]
      model = parentField.params && parentField.params.model
      parentParams = {
        exclude: [parentField.relation_field],
        ...parentField.params,
        parent_name: parentField.string,
      }
    }
    if (preventLoad) {
      return
    }
    const fields = await this.getExportedFields(model, parentParams)
    for (const field of fields) {
      field.formattedString = field.string.split("/").pop()
      field.formattedId = field.id.split("/").pop()
      field.parent = parentField
      if (!this.knownFields[field.id]) {
        this.knownFields[field.id] = field
      }
    }
    if (id) {
      this.expandedFields[id] = { fields }
    }
    return fields
  }

  async getExportedFields(model, parentParams = {}) {
    const fields = await this.orm.call("onlyoffice.odoo.templates", "get_fields_for_model", [
      model,
      parentParams.prefix || "",
      parentParams.parent_name || "",
      parentParams.exclude,
    ])

    return fields
  }

  onSearch(ev) {
    this.state.search = this.lookup(ev.target.value)
  }

  onCleanSearch() {
    this.searchRef.el.value = ""
    this.state.search = []
  }

  lookup(value) {
    let lookupResult = null
    if (this.state.isTechnicalName) {
      lookupResult = fuzzyLookup(value, Object.values(this.knownFields), (field) => field.id.replaceAll("/", " "))
    } else {
      lookupResult = fuzzyLookup(value, Object.values(this.knownFields), (field) => field.string.replaceAll("/", " "))
    }
    return lookupResult
  }

  onToggleDisplayOption(value) {
    // This.onCleanSearch()
    this.state.isTechnicalName = value
  }
}
ExportData.components = {
  CheckBox,
  ExportDataItem,
}
ExportData.props = { resModel: String }
ExportData.template = "onlyoffice_odoo_templates.ExportData"
