# Copyright (C) 2026 Ascensio System SIA
# Odoo 18 with the Python dependency of the ONLYOFFICE modules and the Enterprise addons path.
FROM odoo:18.0
USER root
# The image is Ubuntu 24.04: its system Python is externally managed (PEP 668).
RUN pip3 install --no-cache-dir --break-system-packages pyjwt
COPY --chown=odoo odoo.conf /etc/odoo/odoo.conf
USER odoo
