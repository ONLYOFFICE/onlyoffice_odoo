# Copyright (C) 2026 Ascensio System SIA
# Printing through a real Document Server is covered by the Playwright tests (e2e/tests/templates.spec.ts): in an
# HttpCase the docbuilder callback into Odoo waits for the test cursor held by the print request and deadlocks.

from . import test_controllers
from . import test_fill_template
from . import test_models
