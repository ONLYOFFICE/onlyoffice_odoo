Go to **Settings → ONLYOFFICE** after installation.

Document Server URL
===================

Enter the public URL of your ONLYOFFICE Docs instance (e.g.
``https://documentserver.example.com/``).

JWT Security
============

JWT is enabled by default. A secret key is generated automatically to
restrict access to ONLYOFFICE Docs. To use a custom key, enter it in the
**Secret key** field and set the same key in your `ONLYOFFICE Docs
configuration file`_.

If the default ``Authorization`` JWT header conflicts with your setup,
change it to a custom value in the **JWT Header** field.

.. _ONLYOFFICE Docs configuration file: https://api.onlyoffice.com/docs/docs-api/additional-api/signature/

Network Configuration
=====================

If your Odoo and ONLYOFFICE Docs servers cannot reach each other via their
public addresses, fill in the following fields:

* **ONLYOFFICE Docs address for internal requests from the server** — the URL
  that Odoo uses to contact ONLYOFFICE Docs internally.
* **Server address for internal requests from ONLYOFFICE Docs** — the URL
  that ONLYOFFICE Docs uses to call back into Odoo.

Other Settings
==============

* **Open file in the same tab** — when checked, files open in the current
  browser tab instead of a new one.
* **Disable certificate verification** — use only for development/testing
  with self-signed certificates.
* **Demo server** — connect to the public ONLYOFFICE demo server for a
  30-day trial. Do not use with sensitive data.
