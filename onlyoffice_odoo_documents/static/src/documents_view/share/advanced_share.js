/** @odoo-module **/
// Copyright (C) 2026 Ascensio System SIA

/* eslint-disable @stylistic/implicit-arrow-linebreak */
/* eslint-disable @stylistic/function-paren-newline */
/* eslint-disable @stylistic/indent */
/* eslint-disable @stylistic/multiline-ternary */

import { Dialog } from "@web/core/dialog/dialog"
import { Domain } from "@web/core/domain"
import { TagsList } from "@web/core/tags_list/tags_list"
import { useService } from "@web/core/utils/hooks"
import { Many2XAutocomplete } from "@web/views/fields/relational_utils"

const { Component, useState, onWillStart } = owl

const ROLE_ORDER = {
  editor: 0,
  reviewer: 1,
  // eslint-disable-next-line sort-keys
  form_filling: 2,
  // eslint-disable-next-line sort-keys
  custom_filter: 3,
  // eslint-disable-next-line sort-keys
  commenter: 4,
  viewer: 5,
  // eslint-disable-next-line sort-keys
  none: 6,
}

export class ShareDialog extends Component {
  static components = {
    Dialog,
    Many2XAutocomplete,
    TagsList,
  }

  static template = "onlyoffice_odoo_documents.ShareDialog"

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.action = useService("action")

    this.state = useState({
      document: null,
      hasChanges: false,
      initialInternalAccess: null,
      initialLinkAccess: null,
      internalAccess: "none",
      internalAccessRoles: {},
      linkAccess: "viewer",
      linkAccessRoles: {},
      loading: true,
      newUserAccess: "editor",
      saving: false,
      userNames: {},
      users: [],
      usersAccess: [],
      usersAccessBackup: [],
      usersAccessRoles: {},
      usersInput: null,
    })

    onWillStart(async () => {
      this.state.loading = true
      await this.loadShareData()
      this.state.loading = false
    })
  }

  async loadShareData() {
    const shareData = await this.orm.call("onlyoffice.odoo.documents", "advanced_share_data", [
      { document_id: this.props.document_id },
    ])

    this.state.document = shareData.document
    this.state.usersAccess = this.sortUsersByRole(shareData.users_access)
    this.state.usersAccessBackup = [...this.state.usersAccess]
    this.state.initialInternalAccess = shareData.internal_users
    this.state.initialLinkAccess = shareData.link_access
    this.state.usersAccessRoles = this.roleSorting(shareData.users_access_roles)
    this.state.internalAccess = shareData.internal_users
    this.state.internalAccessRoles = this.roleSorting(shareData.internal_users_roles)
    this.state.linkAccess = shareData.link_access
    this.state.linkAccessRoles = this.roleSorting(shareData.link_access_roles)
  }

  sortUsersByRole = (users) => {
    return [...users].sort((a, b) => ROLE_ORDER[a.role.role] - ROLE_ORDER[b.role.role])
  }

  roleSorting = (role) => {
    return Object.entries(role)
      .sort((a, b) => ROLE_ORDER[a[0]] - ROLE_ORDER[b[0]])
      .map(([key, value]) => ({ [key]: value }))
  }

  getDomain = () => {
    const selectedIds = this.state.users.map((user) => user.id)
    return new Domain([["id", "not in", selectedIds]]).toList()
  }

  get tags() {
    return this.state.users.map((user) => ({
      id: user.id,
      onDelete: () => this.onDeleteTag(user.id),
      text: user.name,
    }))
  }

  onDeleteTag = (id) => {
    this.state.users = this.state.users.filter((user) => user.id !== id)
    this.state.hasChanges = this.state.users.length > 0
  }

  async onAddUsers(users) {
    for (let i = 0; i < users.length; i += 1) {
      if (!users[i].display_name) {
        const userId = users[i].id
        if (!userId || typeof userId !== "number") {
          continue
        }
        try {
          const user = await this.orm.read("res.users", [userId], ["name", "display_name"])
          if (user && user.length > 0) {
            users[i] = {
              display_name: user[0].display_name || user[0].name,
              id: user[0].id,
            }
          }
        } catch (error) {
          console.error("failed to fetch user:", userId, error)
        }
      }
    }

    if (!users?.length) {
      return
    }

    const newUsers = users.filter((u) => !this.state.users.some((existing) => existing.id === u.id))

    if (!newUsers.length) {
      return
    }

    users.forEach((user) => {
      this.state.users.push({
        id: user.id,
        name: user.display_name,
      })
      this.state.userNames[user.id] = user.display_name
    })

    this.state.usersInput = null
    this.state.hasChanges = true
  }

  removeUserAccess = (userId) => {
    this.state.usersAccess = this.state.usersAccess.filter((userAccess) => userAccess.user.id !== userId)
    this.state.users = this.state.users.filter((user) => user.id !== userId)
    this.checkForChanges()
    this.notification.add("User access removed (changes not saved yet)", { type: "warning" })
  }

  onUserRoleAdd = (role) => {
    this.state.newUserAccess = role
  }

  onUserRoleChange = (userId, newRole) => {
    this.state.usersAccess = this.state.usersAccess.map((userAccess) =>
      userAccess.user.id === userId
        ? {
            ...userAccess,
            role: {
              ...userAccess.role,
              role: newRole,
            },
          }
        : userAccess,
    )
    this.checkForChanges()
  }

  onInternalAccessChange = (ev) => {
    this.state.internalAccess = ev.target.value
    this.checkForChanges()
  }

  onLinkAccessChange = (ev) => {
    this.state.linkAccess = ev.target.value
    this.checkForChanges()
  }

  checkForChanges = () => {
    let hasRoleChanges = false
    let hasUserChanges = false

    if (this.state.usersAccessBackup.length) {
      const currentRoles = new Map(this.state.usersAccess.map((user) => [user.user.id, user.role.role]))
      const backupRoles = new Map(this.state.usersAccessBackup.map((user) => [user.user.id, user.role.role]))

      hasRoleChanges = [...currentRoles].some(([id, role]) => backupRoles.get(id) !== role)
      hasUserChanges = [...backupRoles.keys()].some((id) => !currentRoles.has(id))
    }

    this.state.hasChanges =
      hasRoleChanges ||
      hasUserChanges ||
      this.state.internalAccess !== this.state.initialInternalAccess ||
      this.state.linkAccess !== this.state.initialLinkAccess
  }

  resetChanges = () => {
    this.state.newUserAccess = "editor"
    this.state.usersAccess = [...this.state.usersAccessBackup]
    this.state.internalAccess = this.state.initialInternalAccess
    this.state.linkAccess = this.state.initialLinkAccess
    this.state.users = []
    this.state.hasChanges = false
  }

  async save() {
    try {
      this.state.saving = true
      const userAccesses = []

      this.state.usersAccess.forEach((userAccess) => {
        userAccesses.push({
          role: userAccess.role.role,
          user_id: userAccess.user.id,
        })
      })

      this.state.users.forEach((user) => {
        if (!this.state.usersAccess.some((u) => u.user.id === user.id)) {
          userAccesses.push({
            role: this.state.newUserAccess,
            user_id: user.id,
          })
        } else {
          const existingUser = this.state.usersAccess.find((u) => u.user.id === user.id)
          if (existingUser && existingUser.role.role !== this.state.newUserAccess) {
            userAccesses.push({
              role: this.state.newUserAccess,
              user_id: user.id,
            })
          }
        }
      })

      const result = await this.orm.call("onlyoffice.odoo.documents", "advanced_share_save", [
        {
          document_id: this.props.document_id,
          internal_users: this.state.internalAccess,
          link_access: this.state.linkAccess,
          user_accesses: userAccesses,
        },
      ])

      if (result) {
        this.notification.add("Sharing settings saved successfully", { type: "success" })
        await this.loadShareData()
        this.resetChanges()
        this.state.hasChanges = false
        this.state.saving = false
      }
    } catch (error) {
      console.error("Error saving sharing settings:", error)
      this.notification.add("Error saving sharing settings", { type: "danger" })
      this.state.saving = false
    }
  }

  async close() {
    if (this.props.openEditor) {
      const { same_tab } = JSON.parse(await this.orm.call("onlyoffice.odoo", "get_same_tab"))
      if (same_tab) {
        const action = {
          params: { document_id: this.props.document_id[0] },
          tag: "onlyoffice_editor",
          target: "current",
          type: "ir.actions.client",
        }
        return this.action.doAction(action)
      }
      this.props.close()
      return window.open(`/onlyoffice/editor/document/${this.props.document_id[0]}`, "_blank")
    }
    this.props.close()
  }
}
