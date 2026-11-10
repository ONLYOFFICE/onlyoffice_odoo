# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.onlyoffice_odoo.utils import config_utils, validation_utils


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doc_server_public_url = fields.Char("Document Server Public URL")
    doc_server_odoo_url = fields.Char("Odoo URL")
    doc_server_inner_url = fields.Char("Document Server Inner URL")
    doc_server_jwt_secret = fields.Char("Document Server JWT Secret")
    doc_server_jwt_header = fields.Char("Document Server JWT Header")
    doc_server_demo = fields.Boolean("Connect to demo ONLYOFFICE Docs server")
    doc_server_disable_certificate = fields.Boolean("Disable certificate verification")
    same_tab = fields.Boolean("Open file in the same tab")

    internal_jwt_secret = fields.Char("Internal JWT Secret")

    @api.onchange("doc_server_public_url")
    def _onchange_doc_server_public_url(self):
        if self.doc_server_public_url and not validation_utils.valid_url(self.doc_server_public_url):
            return {"warning": {"title": "Warning", "message": "Incorrect Document Server URL"}}

    def _normalize_addresses(self):
        """The addresses and the header as entered: spaces around them removed, a blank one empty.

        An inner address equal to the public address being saved adds nothing and is not stored (it follows the
        public one). Any other inner address shown is kept as it is: the public address may be one only browsers
        reach, the server requests going on to the inner one.
        """
        for field in ("doc_server_public_url", "doc_server_inner_url", "doc_server_odoo_url", "doc_server_jwt_header"):
            self[field] = (self[field] or "").strip() or False
        public_url = config_utils.fix_url(self.doc_server_public_url or "http://documentserver/")
        if self.doc_server_inner_url and config_utils.fix_url(self.doc_server_inner_url) == public_url:
            self.doc_server_inner_url = False

    def _check_addresses(self, current):
        """A changed address that cannot be saved is an error, not left out in silence.

        ``current`` are the stored addresses: one left as it is was saved before (the Odoo address can come from
        web.base.url) and does not stop saving the other settings. The Document Server addresses are not checked
        when the demo server is used: they are not saved then.
        """
        checks = [
            (_("Server address for internal requests from ONLYOFFICE Docs"), self.doc_server_odoo_url, current[2])
        ]
        if not self.doc_server_demo:
            checks += [
                (_("ONLYOFFICE Docs address"), self.doc_server_public_url, current[0]),
                (
                    _("ONLYOFFICE Docs address for internal requests from the server"),
                    self.doc_server_inner_url,
                    current[1],
                ),
            ]
        for label, url, stored in checks:
            if url and config_utils.fix_url(url) != stored and not validation_utils.valid_url(url):
                raise ValidationError(_("Incorrect address in %(setting)s: %(url)s", setting=label, url=url))

    def _forget_demo_values(self):
        """Leaving the demo: the address, secret and header of the demo server shown in the form are not the user's.

        An address left empty or as the demo one (any spelling of its host) is not kept. Returns whether a server of
        one's own was entered (a public address; an inner one alone is an error: the editor loads from the public
        one). Without one, the secret and header get the defaults too, as the demo is turned off. With one, the
        public secret and the header of the demo server left in the form are not kept either: a server with the
        default header would have its file downloads refused, and the check does not see it (its file needs no token).
        """
        demo_host = urlparse(config_utils.DEMO_PUBLIC_URL).hostname

        def own(url):
            return bool(url) and urlparse(config_utils.fix_url(url)).hostname != demo_host

        own_public, own_inner = own(self.doc_server_public_url), own(self.doc_server_inner_url)
        if not own_public:
            self.doc_server_public_url = False
        if not own_inner:
            self.doc_server_inner_url = False
        if own_inner and not own_public:
            raise ValidationError(_("Enter the ONLYOFFICE Docs address: the editor is loaded from it."))
        if not own_public or self.doc_server_jwt_secret == config_utils.DEMO_JWT_SECRET:
            self.doc_server_jwt_secret = False
        if not own_public or self.doc_server_jwt_header == config_utils.DEMO_JWT_HEADER:
            self.doc_server_jwt_header = "Authorization"
        return own_public

    def save_config_values(self):
        # The demo goes first: turning it off resets the address, the secret and the header, which the values
        # entered with it then replace. With the demo on, those of the demo server stay.
        config_utils.set_demo(self.env, self.doc_server_demo)
        if not self.doc_server_demo:
            config_utils.set_doc_server_public_url(self.env, self.doc_server_public_url)
            config_utils.set_doc_server_inner_url(self.env, self.doc_server_inner_url)
            config_utils.set_jwt_secret(self.env, self.doc_server_jwt_secret)
            config_utils.set_jwt_header(self.env, self.doc_server_jwt_header)
        # A changed invalid address was an error; an empty one goes back to web.base.url; one left as it is is saved
        # again only when valid.
        if not self.doc_server_odoo_url or validation_utils.valid_url(self.doc_server_odoo_url):
            config_utils.set_doc_server_odoo_url(self.env, self.doc_server_odoo_url)
        config_utils.set_certificate_verify_disabled(self.env, self.doc_server_disable_certificate)
        config_utils.set_same_tab(self.env, self.same_tab)

    def set_values(self):
        res = super().set_values()

        current_demo_state = config_utils.get_demo(self.env)
        current_public_url = config_utils.get_doc_server_public_url(self.env)
        current_odoo_url = config_utils.get_base_or_odoo_url(self.env)
        current_inner_url = config_utils.get_doc_server_inner_url(self.env)
        current_jwt_secret = config_utils.get_jwt_secret(self.env)
        current_jwt_header = config_utils.get_jwt_header(self.env)
        current_disable_certificate = config_utils.get_certificate_verify_disabled(self.env)

        current_same_tab = config_utils.get_same_tab(self.env)

        settings_changed = (
            self.doc_server_public_url != current_public_url
            or self.doc_server_odoo_url != current_odoo_url
            or self.doc_server_inner_url != current_inner_url
            or self.doc_server_jwt_secret != current_jwt_secret
            or self.doc_server_jwt_header != current_jwt_header
            or self.doc_server_demo != current_demo_state
            or self.doc_server_disable_certificate != current_disable_certificate
            or self.same_tab != current_same_tab
        )

        if settings_changed:
            self._normalize_addresses()
            self._check_addresses((current_public_url, current_inner_url, current_odoo_url))
            leaving_demo = current_demo_state and not self.doc_server_demo
            own_server = self._forget_demo_values() if leaving_demo else True
            # The server that will be used is checked: the one entered, not the demo server. Leaving the demo
            # without a server of one's own saves the defaults, unchecked, as before.
            if not self.doc_server_demo and own_server:
                validation_utils.settings_validation(self)
            self.save_config_values()

        return res

    def get_values(self):
        res = super().get_values()

        doc_server_public_url = config_utils.get_doc_server_public_url(self.env)
        doc_server_odoo_url = config_utils.get_base_or_odoo_url(self.env)
        doc_server_inner_url = config_utils.get_doc_server_inner_url(self.env)
        doc_server_jwt_secret = config_utils.get_jwt_secret(self.env)
        doc_server_jwt_header = config_utils.get_jwt_header(self.env)
        doc_server_demo = config_utils.get_demo(self.env)
        doc_server_disable_certificate = config_utils.get_certificate_verify_disabled(self.env)
        same_tab = config_utils.get_same_tab(self.env)

        res.update(
            doc_server_public_url=doc_server_public_url,
            doc_server_odoo_url=doc_server_odoo_url,
            doc_server_inner_url=doc_server_inner_url,
            doc_server_jwt_secret=doc_server_jwt_secret,
            doc_server_jwt_header=doc_server_jwt_header,
            doc_server_demo=doc_server_demo,
            doc_server_disable_certificate=doc_server_disable_certificate,
            same_tab=same_tab,
        )

        return res
