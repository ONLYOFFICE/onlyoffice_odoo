/** @odoo-module **/

/*
 *
 * (c) Copyright Ascensio System SIA 2024
 *
 */

import { registerPatch } from "@mail/model/model_core"
import { attr } from "@mail/model/model_field"

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

registerPatch({
  name: "Attachment",
  recordMethods: {
    async onClickOnlyofficeEdit(ev) {
      ev.stopPropagation()
      const demo = JSON.parse(
        await this.messaging.rpc({
          method: "get_demo",
          model: "onlyoffice.odoo",
        }),
      )
      if (demo && demo.mode && demo.date) {
        const isValidDate = (d) => d instanceof Date && !isNaN(d)
        demo.date = new Date(Date.parse(demo.date))
        if (isValidDate(demo.date)) {
          const today = new Date()
          const difference = Math.floor((today - demo.date) / (1000 * 60 * 60 * 24))
          if (difference > 30) {
            this.messaging.userNotificationManager.sendNotification({
              message: this.env._t(
                "The 30-day test period is over, you can no longer connect to demo ONLYOFFICE Docs server",
              ),
              title: this.env._t("ONLYOFFICE Docs server"),
              type: "warning",
            })
            return
          }
        }
      }

      const { same_tab } = JSON.parse(
        await this.messaging.rpc({
          method: "get_same_tab",
          model: "onlyoffice.odoo",
        }),
      )
      if (same_tab) {
        this.openSameTabOnlyofficeEditor()
      } else {
        this.openNewTabOnlyofficeEditor()
      }
    },
    openNewTabOnlyofficeEditor() {
      window.open(this.onlyofficeEditorUrl, "_blank")
    },
    openSameTabOnlyofficeEditor() {
      const action = {
        params: { attachment_id: this.id },
        tag: "onlyoffice_editor",
        target: "current",
        type: "ir.actions.client",
      }
      return this.env.services.action.doAction(action)
    },
  },
  // eslint-disable-next-line sort-keys
  fields: {
    onlyofficeCanEdit: attr({
      compute() {
        return oo_editable_formats.includes(this.extension.toLowerCase())
      },
    }),
    onlyofficeCanView: attr({
      compute() {
        return oo_viewable_formats.includes(this.extension.toLowerCase())
      },
    }),
    onlyofficeEditorUrl: attr({
      compute() {
        const accessTokenQuery = this.accessToken ? `?access_token=${this.accessToken}` : ""
        return `/onlyoffice/editor/${this.id}${accessTokenQuery}`
      },
    }),
  },
})
