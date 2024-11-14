/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2024
 *
 */

import { AttachmentList } from "@mail/core/common/attachment_list"
import { _t } from "@web/core/l10n/translation"
import { useService } from "@web/core/utils/hooks"
import { patch } from "@web/core/utils/patch"

const oo_editable_formats = ["docx", "xlsx", "pptx", "pdf"]

const oo_viewable_formats = [
  "djvu",
  "doc",
  "docm",
  "docxf",
  "dot",
  "dotm",
  "dotx",
  "epub",
  "fb2",
  "fodt",
  "html",
  "mht",
  "odt",
  "ott",
  "oxps",
  "rtf",
  "txt",
  "xps",
  "xml",
  "csv",
  "fods",
  "ods",
  "ots",
  "xls",
  "xlsb",
  "xlsm",
  "xlt",
  "xltm",
  "xltx",
  "fodp",
  "odp",
  "otp",
  "pot",
  "potm",
  "potx",
  "pps",
  "ppsm",
  "ppsx",
  "ppt",
  "pptm",
]

patch(AttachmentList.prototype, {
  setup() {
    super.setup(...arguments)
    this.orm = useService("orm")
    this.notification = useService("notification")
  },
  // eslint-disable-next-line sort-keys
  onlyofficeCanOpen(attachment) {
    return oo_editable_formats.includes(attachment.extension) || oo_viewable_formats.includes(attachment.extension)
  },
  async openOnlyoffice(attachment) {
    var demo = await this.orm.call("ir.config_parameter", "get_param", ["onlyoffice_connector.doc_server_demo"])
    var demoDate = await this.orm.call("ir.config_parameter", "get_param", [
      "onlyoffice_connector.doc_server_demo_date",
    ])
    demoDate = new Date(Date.parse(demoDate))
    if (demo && demoDate && demoDate instanceof Date) {
      const today = new Date()
      const difference = Math.floor((today - new Date(Date.parse(demoDate))) / (1000 * 60 * 60 * 24))
      if (difference > 30) {
        this.notification.add(
          _t("The 30-day test period is over, you can no longer connect to demo ONLYOFFICE Docs server"),
          {
            title: _t("ONLYOFFICE Docs server"),
            type: "warning",
          },
        )
        return
      }
    }
    const accessTokenQuery = attachment.accessToken ? `?access_token=${attachment.accessToken}` : ""
    window.open(`/onlyoffice/editor/${attachment.id}${accessTokenQuery}`, "_blank")
  },
})
