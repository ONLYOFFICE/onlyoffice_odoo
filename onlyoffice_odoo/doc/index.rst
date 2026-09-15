Prerequisites
=============

To be able to work with office files within Odoo, you will need an instance of ONLYOFFICE Docs. You can install the `self-hosted version`_ of the editors (free Community build or scalable Enterprise version), or opt for `ONLYOFFICE Docs`_ Cloud which doesn't require downloading and installation.

ONLYOFFICE app configuration
============================

After the app installation, adjust its settings within your Odoo (*Home menu -> Settings -> ONLYOFFICE*).
In the **Document Server Url**, specify the URL of the installed ONLYOFFICE Docs or the address of ONLYOFFICE Docs Cloud.

**Document Server JWT Secret**: JWT is enabled by default and the secret key is generated automatically to restrict the access to ONLYOFFICE Docs. if you want to specify your own secret key in this field, also specify the same secret key in the ONLYOFFICE Docs `config file`_ to enable the validation.

**Document Server JWT Header**: Standard JWT header used in ONLYOFFICE is Authorization. In case this header is in conflict with your setup, you can change the header to the custom one.

In case your network configuration doesn't allow requests between the servers via public addresses, specify the ONLYOFFICE Docs address for internal requests from the Odoo server and vice versa.

For security reasons, the address that Odoo uses to reach ONLYOFFICE Docs must not point to the local machine or to a private network (``localhost``, ``127.0.0.1``, ``10.x.x.x``, ``172.16.x.x``, ``192.168.x.x``, Docker service names). Such addresses are rejected when the settings are saved. If ONLYOFFICE Docs runs in the same private network as Odoo, allow local addresses in the Odoo configuration file and restart Odoo::

    [onlyoffice]
    allow_local_address = True

Details of failed connection checks are written to the Odoo server log; the settings form shows only a generic message.

If you would like the editors to open in the same tab instead of a new one, check the corresponding setting "Open file in the same tab".

.. image:: settings.png
    :width: 800


Contact us
==========

If you have any questions or suggestions regarding the ONLYOFFICE app for Odoo, please let us know at https://forum.onlyoffice.com

.. _self-hosted version: https://www.onlyoffice.com/download-docs.aspx
.. _ONLYOFFICE Docs: https://www.onlyoffice.com/docs-registration.aspx
.. _config file: https://api.onlyoffice.com/docs/docs-api/additional-api/signature/
