from odoo.addons.onlyoffice_odoo.utils import config_utils


def replace_public_url_to_internal(env, url):
    public_url = config_utils.get_doc_server_public_url(env)
    inner_url = config_utils.get_doc_server_inner_url(env)
    if inner_url: # add demo mode check
        url = url.replace(public_url, inner_url)
    return url