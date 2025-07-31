/** @odoo-module **/
/* eslint-disable @stylistic/implicit-arrow-linebreak */
/* eslint-disable @stylistic/function-paren-newline */
/* eslint-disable @stylistic/indent */
/* eslint-disable @stylistic/multiline-ternary */

import { Dialog } from "@web/core/dialog/dialog"
import { Domain } from "@web/core/domain"
import { useService } from "@web/core/utils/hooks"
import { TagsList } from "@web/views/fields/many2many_tags/tags_list"
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
      internalAccess: "none",
      internalAccessRoles: {},
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
    this.state.usersAccessRoles = this.roleSorting(shareData.users_access_roles)
    this.state.internalAccess = shareData.internal_users
    this.state.internalAccessRoles = this.roleSorting(shareData.internal_users_roles)
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
    if (!users?.length) {
      return
    }

    const newUsers = users.filter((u) => !this.state.users.some((existing) => existing.id === u.id))

    if (!newUsers.length) {
      return
    }

    const names = await this.orm.nameGet(
      "res.users",
      newUsers.map((u) => u.id),
    )

    names.forEach(([id, name]) => {
      this.state.users.push({
        id,
        name,
      })
      this.state.userNames[id] = name
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
    this.state.hasChanges = true
  }

  checkForChanges = () => {
    if (!this.state.usersAccessBackup.length) {
      return
    }

    const currentRoles = new Map(this.state.usersAccess.map((user) => [user.user.id, user.role.role]))
    const backupRoles = new Map(this.state.usersAccessBackup.map((user) => [user.user.id, user.role.role]))

    const hasRoleChanges = [...currentRoles].some(([id, role]) => backupRoles.get(id) !== role)
    const hasUserChanges = [...backupRoles.keys()].some((id) => !currentRoles.has(id))

    this.state.hasChanges =
      hasRoleChanges || hasUserChanges || this.state.internalAccess !== this.state.initialInternalAccess
  }

  resetChanges = () => {
    this.state.newUserAccess = "editor"
    this.state.usersAccess = [...this.state.usersAccessBackup]
    this.state.internalAccess = this.state.initialInternalAccess
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
