# Copyright (C) 2026 Ascensio System SIA

# Odoo runs the scripts of "0.0.0" on every update of the module to a new version.


def migrate(cr, version):
    """Clears the roles of Odoo that older versions wrote into the ONLYOFFICE rows.

    Odoo keeps none / view / edit itself; copied into these rows, they would hide its current rights: a document shared
    with everybody would stay closed ("none" was written on every share and for every created file), a member (or a
    group) removed in Odoo would keep their role. Only the roles Odoo does not have stay. Running it again changes
    nothing.
    """
    if not version:
        return
    roles = ("none", "view", "edit")
    cr.execute("UPDATE onlyoffice_odoo_documents_access SET internal_users = NULL WHERE internal_users IN %s", [roles])
    cr.execute("UPDATE onlyoffice_odoo_documents_access SET link_access = NULL WHERE link_access IN %s", [roles])
    cr.execute("DELETE FROM onlyoffice_odoo_documents_access_user WHERE role IN %s", [roles])
    cr.execute("DELETE FROM onlyoffice_odoo_documents_access_group WHERE role IN %s", [roles])
