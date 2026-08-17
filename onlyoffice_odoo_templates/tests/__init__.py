# Copyright (C) 2026 Ascensio System SIA
import os

from . import test_controllers
from . import test_models

# Only runs with a real Document Server. Delete this block and the file to remove it.
if os.environ.get("ONLYOFFICE_TEST_LIVE_DOCSERVER"):
    from . import test_document_server
