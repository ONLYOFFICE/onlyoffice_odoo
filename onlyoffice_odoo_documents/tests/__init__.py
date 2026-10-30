# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).
# The Document Server is mocked here; editing, conversion and docbuilder rebuilds against a real one are covered by the
# Playwright tests (e2e/tests/documents.spec.ts): in an HttpCase the docbuilder callback into Odoo would wait for the
# test cursor held by the request and deadlock.

from . import test_controllers
from . import test_models
from . import test_share
from . import test_spreadsheet_docbuilder
from . import test_spreadsheet_formulas
from . import test_spreadsheet_routes
