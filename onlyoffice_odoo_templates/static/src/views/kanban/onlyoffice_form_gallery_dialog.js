/** @odoo-module **/
import { Dialog } from "@web/core/dialog/dialog"
import { Dropdown } from "@web/core/dropdown/dropdown"
import { DropdownItem } from "@web/core/dropdown/dropdown_item"
import { _t } from "@web/core/l10n/translation"
import { Pager } from "@web/core/pager/pager"
import { useService } from "@web/core/utils/hooks"
import { OnlyofficePDFPreview } from "../widget/onlyoffice_pdf_preview"

const { Component, useState, onWillStart } = owl

export class FormGalleryDialog extends Component {
  static template = "onlyoffice_odoo_templates.FormGalleryDialog"

  static components = {
    Dialog,
    Dropdown,
    DropdownItem,
    Pager,
  }

  setup() {
    this.title = _t("Form Gallery")
    this.action = useService("action")
    this.notification = useService("notification")
    this.rpc = useService("rpc")

    this.state = useState({
      categories: [],
      error: null,
      form: null,
      forms: [],
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
      search: "",
      subcategories: {},
      subcategory: {
        category_type: "category",
        id: "all",
      },
      total: 0,
    })

    onWillStart(async () => {
      this.state.loading = true
      await this.fetchLocales()
      await this.fetchCategoryTypes()
      await this.fetchOforms()
      this.state.loading = false
    })
  }

  async fetchLocales() {
    try {
      const url = "/onlyoffice/oforms/locales"
      const response = await this.rpc(url)

      let localesData = []
      if (Array.isArray(response)) {
        localesData = response.map((item) => ({
          code: item.code,
          name: item.name || item.code,
        }))
      } else if (response && response.data) {
        localesData = response.data
      }

      this.state.locales = localesData
    } catch (_error) {
      this.state.locales = [
        {
          code: "en",
          name: "English",
        },
      ]
    }
  }

  async fetchCategoryTypes() {
    try {
      const response = await this.rpc("/onlyoffice/oforms/category-types", { locale: this.state.locale.code })
      this.state.categories = response.data || []
      response.data.forEach(async (categoryTypes) => {
        await this.fetchSubcategories(categoryTypes.categoryId)
      })
    } catch (_error) {
      this.notification.add(_t("Failed to load categories"), { type: "danger" })
    }
  }

  async fetchSubcategories(categoryId) {
    try {
      const category = this.state.categories.find((c) => c.categoryId === categoryId)
      const response = await this.rpc("/onlyoffice/oforms/subcategories", {
        category_type: category.type,
        locale: this.state.locale.code,
      })

      this.state.subcategories[categoryId] = response.data || []
    } catch (_error) {
      this.state.subcategories[categoryId] = []
    }
  }

  async fetchOforms() {
    this.state.form = null
    this.state.error = null

    try {
      const params = {
        ["filters[" + this.state.subcategory.category_type + "][$eq]"]: this.state.subcategory.id,
        locale: this.state.locale.code,
        "pagination[pageSize]": this.state.limit,
        "pagination[page]": Math.floor(this.state.offset / this.state.limit) + 1,
      }

      if (this.state.search) {
        params["filters[name_form][$containsi]"] = this.state.search
      }

      const response = await this.rpc("/onlyoffice/oforms", { params: params })

      this.state.forms = response.data || []
      this.state.total = response.meta?.pagination?.total || 0
    } catch (_error) {
      this.state.error = _t("Failed to load forms")
      this.notification.add(_t("Error loading forms"), { type: "danger" })
    }
  }

  async onSubcategorySelect(subcategory) {
    this.state.subcategory = subcategory
    this.state.offset = 0
    await this.fetchOforms()
  }

  async onAllSubcategorySelect() {
    this.state.subcategory = {
      category_type: "category",
      id: "all",
    }
    this.state.offset = 0
    await this.fetchOforms()
  }

  async onSearch(search) {
    this.state.search = search
    this.state.offset = 0
    await this.fetchOforms()
  }

  async onLocaleChange(locale) {
    this.state.locale = locale
    this.state.subcategory = {
      category_type: "category",
      id: "all",
    }
    this.state.offset = 0
    await this.fetchCategoryTypes()
    await this.fetchOforms()
  }

  async onPageChange({ offset }) {
    this.state.offset = offset
    await this.fetchOforms()
  }

  getImageUrl(form) {
    const imageData = form.attributes?.template_image?.data
    if (!imageData) {
      return null
    }
    return (
      imageData.attributes.formats.medium?.url ||
      imageData.attributes.formats.small?.url ||
      imageData.attributes.formats.thumbnail?.url
    )
  }

  getPreviewUrl(form) {
    return form.attributes?.card_prewiew?.data?.attributes?.url
  }

  previewForm(path, name) {
    const url = `/onlyoffice/template/gallery/preview?form_path=${encodeURIComponent(path)}`

    this.env.services.dialog.add(
      OnlyofficePDFPreview,
      {
        close: () => {
          this.env.services.dialog.close()
        },
        title: "PDF Preview - " + name,
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
    if (this.state.form) {
      this.action.doAction({
        context: {
          default_hide_file_field: true,
          default_name: this.state.form.attributes.name_form,
          url: this.state.form.attributes.file_oform.data[0].attributes.url,
        },
        res_model: "onlyoffice.odoo.templates",
        target: "current",
        type: "ir.actions.act_window",
        view_mode: "form",
        views: [[false, "form"]],
      })
    }
  }
}
