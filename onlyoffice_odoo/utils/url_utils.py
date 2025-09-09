import logging

from odoo.addons.onlyoffice_odoo.utils import config_utils

_logger = logging.getLogger(__name__)


def replace_public_url_to_internal(env, url):
    public_url = config_utils.get_doc_server_public_url(env)
    inner_url = config_utils.get_doc_server_inner_url(env)
    if inner_url and inner_url != public_url:
        _logger.info("Replace public url %s to internal url %s", public_url, inner_url)
        url = url.replace(public_url, inner_url)
    return url
