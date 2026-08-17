# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import os

from . import test_config_utils
from . import test_controllers
from . import test_file_utils
from . import test_jwt_utils
from . import test_models
from . import test_url_utils
from . import test_validation_utils

# Only runs with a real Document Server. Delete this block and the file to remove it.
if os.environ.get("ONLYOFFICE_TEST_LIVE_DOCSERVER"):
    from . import test_document_server
