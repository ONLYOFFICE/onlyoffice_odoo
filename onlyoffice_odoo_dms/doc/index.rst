Prerequisites
=============

Before using this app, you need to install the following:

- A running instance of `ONLYOFFICE Docs <https://www.onlyoffice.com/download-docs.aspx>`_
- The free `DMS (Document Management System) <https://apps.odoo.com/apps/modules/18.0/dms/>`_ module
- The `ONLYOFFICE module for Odoo <https://apps.odoo.com/apps/modules/18.0/onlyoffice_odoo/>`_

App configuration
=================

First, you need to configure the main ONLYOFFICE module for Odoo. Once you complete that setup, the ONLYOFFICE DMS app is ready to use immediately. No additional configuration is required.

To adjust the main app settings within your Odoo, go to *Home menu -> Settings -> ONLYOFFICE*.

In the **Document Server Url**, specify the URL of the installed ONLYOFFICE Docs or the address of ONLYOFFICE Docs Cloud.

**Document Server JWT Secret**: JWT is enabled by default and the secret key is generated automatically to restrict the access to ONLYOFFICE Docs. If you want to specify your own secret key in this field, also specify the same secret key in the ONLYOFFICE Docs `config file <https://api.onlyoffice.com/docs/docs-api/additional-api/signature/>`_ to enable the validation.

**Document Server JWT Header**: Standard JWT header used in ONLYOFFICE is Authorization. In case this header is in conflict with your setup, you can change the header to the custom one.

In case your network configuration doesn't allow requests between the servers via public addresses, specify the ONLYOFFICE Docs address for internal requests from the Odoo server and vice versa.

If you would like the editors to open in the same tab instead of a new one, check the corresponding setting "Open file in the same tab".


Contact us
==========

If you have any questions or suggestions regarding the ONLYOFFICE apps for Odoo, please let us know at `community.onlyoffice.com <https://community.onlyoffice.com>`_.
