/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

import { OnlyofficePreview } from "@onlyoffice_odoo/views/preview/onlyoffice_preview"
import { Dialog } from "@web/core/dialog/dialog"
import { Dropdown } from "@web/core/dropdown/dropdown"
import { DropdownItem } from "@web/core/dropdown/dropdown_item"
import { _t } from "@web/core/l10n/translation"
import { rpc } from "@web/core/network/rpc"
import { Pager } from "@web/core/pager/pager"
import { useService } from "@web/core/utils/hooks"

const { Component, useState, onWillStart, onWillUnmount } = owl

export class FormGallery extends Component {
  static template = "onlyoffice_odoo.FormGallery"

  static components = {
    Dialog,
    Dropdown,
    DropdownItem,
    Pager,
  }

  setup() {
    this.title = _t("Document templates")
    this.action = useService("action")
    this.notification = useService("notification")
    this.rpc = rpc
    this.orm = useService("orm")

    this.searchTimeout = null

    this.state = useState({
      error: null,
      filter: null,
      form: null,
      forms: [],
      ghost: 0,
      limit: 12,
      loading: false,
      locale: {
        code: "en",
        name: "English",
      },
      locales: [
        {
          code: "en",
          name: "English",
        },
      ],
      offset: 0,
      purposes: [],
      search: "",
      total: 0,
      type: "pdf",
    })

    onWillStart(async () => {
      this.state.loading = true
      await this.fetchLocales()
      await Promise.all([this.fetchCategories(), this.fetchOforms()])
      this.state.loading = false
    })

    onWillUnmount(() => {
      if (this.searchTimeout) {
        clearTimeout(this.searchTimeout)
      }
    })
  }

  async fetchLocales() {
    try {
      const response = await this.rpc("/onlyoffice/oforms/locales")
      if (response.data?.length) {
        this.state.locales = response.data
      }
    } catch (_error) {
      this.state.locales = [
        {
          code: "en",
          name: "English",
        },
      ]
    }
  }

  async fetchCategories() {
    try {
      const response = await this.rpc("/onlyoffice/oforms/categories", {
        ext: this.state.type,
        locale: this.state.locale.code,
      })
      this.state.purposes = response.data || []
    } catch (_error) {
      this.state.purposes = []
      this.notification.add(_t("Failed to load categories"), { type: "danger" })
    }
  }

  async fetchOforms() {
    this.state.loading = true
    this.state.form = null
    this.state.error = null

    try {
      const params = {
        ext: this.state.type,
        locale: this.state.locale.code,
        page: Math.floor(this.state.offset / this.state.limit) + 1,
        page_size: this.state.limit,
        purpose: this.state.filter?.purpose,
        search: this.state.search,
        subcategory: this.state.filter?.subcategory,
      }

      const response = await this.rpc("/onlyoffice/oforms", params)

      // A form without a file of the chosen type cannot be previewed or created.
      this.state.forms = (response.data || []).filter((form) => form.file_oform?.length)

      const oKanbanGhost = 4 - (this.state.forms.length % 4)
      if (oKanbanGhost === 4) {
        this.state.ghost = new Array(0).fill()
      } else {
        this.state.ghost = new Array(oKanbanGhost).fill()
      }

      this.state.total = response.meta?.pagination?.total || 0
    } catch (_error) {
      this.state.error = _t("Failed to load forms")
      this.notification.add(_t("Error loading forms"), { type: "danger" })
    }
    this.state.loading = false
  }

  async onChangeType(type) {
    this.state.type = type
    this.state.filter = null
    this.state.offset = 0
    await Promise.all([this.fetchCategories(), this.fetchOforms()])
  }

  async onFilterSelect(filter) {
    this.state.filter = filter
    this.state.offset = 0
    await this.fetchOforms()
  }

  async onSearch(search) {
    if (this.searchTimeout) {
      clearTimeout(this.searchTimeout)
    }

    this.state.search = search

    this.searchTimeout = setTimeout(async () => {
      this.state.offset = 0
      await this.fetchOforms()
    }, 1000)
  }

  async onLocaleChange(locale) {
    this.state.loading = true

    this.state.locale = locale
    this.state.filter = null
    this.state.offset = 0
    await Promise.all([this.fetchCategories(), this.fetchOforms()])

    this.state.loading = false
  }

  async onPageChange({ offset }) {
    this.state.offset = offset
    await this.fetchOforms()
  }

  previewForm(url, title, ext) {
    this.env.services.dialog.add(
      OnlyofficePreview,
      {
        close: () => {
          this.env.services.dialog.close()
        },
        title: title + "." + ext.split(".").pop(),
        url: url,
      },
      {
        onClose: () => {
          return
        },
      },
    )
  }

  selectForm(form) {
    if (this.state.form && this.state.form.id === form.id) {
      this.state.form = null
    } else {
      this.state.form = form
    }
  }

  async download() {
    if (this.props.onDownload && this.state.form) {
      await this.props.onDownload(this.state.form)
      if (this.props.close) {
        this.props.close()
      }
    }
  }
}
