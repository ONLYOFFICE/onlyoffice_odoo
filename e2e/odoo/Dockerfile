# Copyright (C) 2026 Ascensio System SIA
# Odoo 20 with the Python dependency of the ONLYOFFICE modules.
FROM odoo:20.0
USER root
# The image is Ubuntu 24.04: its system Python is externally managed (PEP 668).
RUN pip3 install --no-cache-dir --break-system-packages pyjwt
USER odoo
