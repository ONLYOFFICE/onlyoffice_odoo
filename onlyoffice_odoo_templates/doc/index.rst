Prerequisites
=============

To be able to work with office files within Odoo Enterprise, you will need an instance of `ONLYOFFICE Docs <https://www.onlyoffice.com/download-docs.aspx>`_.

**Please note:** You need to obtain a license for ONLYOFFICE Docs with the included Automation API option.

**Please note**: ONLYOFFICE demo templates will only be added to the Odoo modules that are already installed. That's why we strongly recommend installing ONLYOFFICE Templates after installing other Odoo modules such as CRM, Sales, Calendar, etc.

ONLYOFFICE app configuration
============================

All the settings are configured from the `main ONLYOFFICE app for Odoo <https://apps.odoo.com/apps/modules/18.0/onlyoffice_odoo>`_.

To adjust the main app settings within your Odoo, go to *Home menu -> Settings -> ONLYOFFICE*.

In the **Document Server Url**, specify the URL of the installed ONLYOFFICE Docs or the address of ONLYOFFICE Docs Cloud.

**Document Server JWT Secret**: JWT is enabled by default and the secret key is generated automatically to restrict the access to ONLYOFFICE Docs. if you want to specify your own secret key in this field, also specify the same secret key in the ONLYOFFICE Docs `config file <https://api.onlyoffice.com/editors/signature/>`_ to enable the validation.

**Document Server JWT Header**: Standard JWT header used in ONLYOFFICE is Authorization. In case this header is in conflict with your setup, you can change the header to the custom one.

In case your network configuration doesn't allow requests between the servers via public addresses, specify the ONLYOFFICE Docs address for internal requests from the Odoo server and vice versa.

If you would like the editors to open in the same tab instead of a new one, check the corresponding setting "Open file in the same tab".

.. image:: settings.png
    :width: 800


Contact us
============================
If you have any questions or suggestions regarding the ONLYOFFICE app for Odoo, please let us know at `forum.onlyoffice.com <https://forum.onlyoffice.com>`_.
