# Copyright (C) 2026 Data Dance s.r.o.
# License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

import io
import logging
from collections import OrderedDict
from urllib.parse import quote

from PIL import Image

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, RedirectWarning

from odoo.addons.onlyoffice_odoo.controllers.controllers import onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils, url_utils

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    report_type = fields.Selection(
        selection_add=[("onlyoffice-pdf", "ONLYOFFICE PDF")],
        ondelete={"onlyoffice-pdf": "set default"},
    )

    onlyoffice_template_id = fields.Many2one("onlyoffice.odoo.templates")

    def get_paperformat(self):
        # force the right format (euro/A4) when sending letters, only if we are not using the l10n_DE layout
        res = super().get_paperformat()
        if self.env.context.get("snailmail_layout") and res != self.env.ref("l10n_de.paperformat_euro_din", False):
            paperformat_id = self.env.ref("base.paperformat_euro")
            return paperformat_id
        else:
            return res

    @api.onchange("onlyoffice_template_id")
    def onchange_onlyoffice_template_id(self):
        if self.report_type in ["onlyoffice-pdf"]:
            self.model = self.onlyoffice_template_id.template_model_model
            self.report_name = self.onlyoffice_template_id.name
        else:
            self.model = False
            self.report_name = False

    """
        This is inspired by _render_qweb_pdf_prepare_streams from odoo/addnos/base/model/ir_actions_report.py
    """

    def _render_onlyoffice_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        if not data:
            data = {}
        data.setdefault("report_type", "onlyoffice-pdf")

        # access the report details with sudo() but evaluation context as current user
        report_sudo = self._get_report(report_ref)
        has_duplicated_ids = res_ids and len(res_ids) != len(set(res_ids))

        collected_streams = OrderedDict()

        # Fetch the existing attachments from the database for later use.
        # Reload the stream from the attachment in case of 'attachment_use'.
        if res_ids:
            records = self.env[report_sudo.model].browse(res_ids)
            for record in records:
                res_id = record.id
                if res_id in collected_streams:
                    continue

                stream = None
                attachment = None
                if (
                    not has_duplicated_ids
                    and report_sudo.attachment
                    and not self._context.get("report_pdf_no_attachment")
                ):
                    attachment = report_sudo.retrieve_attachment(record)

                    # Extract the stream from the attachment.
                    if attachment and report_sudo.attachment_use:
                        stream = io.BytesIO(attachment.raw)

                        # Ensure the stream can be saved in Image.
                        if attachment.mimetype.startswith("image"):
                            img = Image.open(stream)
                            new_stream = io.BytesIO()
                            img.convert("RGB").save(new_stream, format="pdf")
                            stream.close()
                            stream = new_stream

                collected_streams[res_id] = {
                    "stream": stream,
                    "attachment": attachment,
                }

        # Call 'onlyoffice' to generate the missing streams.
        res_ids_wo_stream = [res_id for res_id, stream_data in collected_streams.items() if not stream_data["stream"]]
        all_res_ids_wo_stream = res_ids if has_duplicated_ids else res_ids_wo_stream
        is_onlyoffice_needed = not res_ids or res_ids_wo_stream

        if is_onlyoffice_needed:
            internal_jwt_secret = config_utils.get_internal_jwt_secret(self.env)
            oo_security_token = jwt_utils.encode_payload(self.env, {"id": self.env.user.id}, internal_jwt_secret)

            for res_id in all_res_ids_wo_stream:
                try:
                    templates = self.fill_template(oo_security_token, [res_id], self.onlyoffice_template_id)
                    url = next(iter(templates.values()))
                    response = onlyoffice_request(url=quote(url, safe="/:?=&"), method="get")
                    if response.status_code == 200:
                        collected_streams[res_id]["stream"] = io.BytesIO(response.content)
                except Exception as e:
                    _logger.warning(e)

            # # Printing a PDF report without any records. The content could be returned directly.
            # if has_duplicated_ids or not res_ids:
            #     return {
            #         False: {
            #             'stream': pdf_content_stream,
            #             'attachment': None,
            #         }
            #     }

            # collected_streams[False] = {'stream': pdf_content_stream, 'attachment': None}

        return collected_streams

    def _pre_render_onlyoffice_pdf(self, report_ref, res_ids=None, data=None):
        if not data:
            data = {}
        if isinstance(res_ids, int):
            res_ids = [res_ids]
        data.setdefault("report_type", "onlyoffice-pdf")

        self = self.with_context(webp_as_jpg=True)
        return self._render_onlyoffice_pdf_prepare_streams(report_ref, data, res_ids=res_ids), "onlyoffice-pdf"

    def _render_onlyoffice_pdf(self, report_ref, res_ids=None, data=None):
        if not data:
            data = {}
        if isinstance(res_ids, int):
            res_ids = [res_ids]
        data.setdefault("report_type", "onlyoffice-pdf")

        collected_streams, report_type = self._pre_render_onlyoffice_pdf(report_ref, res_ids=res_ids, data=data)
        if report_type != "onlyoffice-pdf":
            return collected_streams, report_type

        has_duplicated_ids = res_ids and len(res_ids) != len(set(res_ids))

        # access the report details with sudo() but keep evaluation context as current user
        report_sudo = self._get_report(report_ref)

        # Generate the ir.attachment if needed.
        if not has_duplicated_ids and report_sudo.attachment and not self._context.get("report_pdf_no_attachment"):
            attachment_vals_list = self._prepare_pdf_report_attachment_vals_list(report_sudo, collected_streams)
            if attachment_vals_list:
                for vals in attachment_vals_list:
                    if "name" in vals and isinstance(vals["name"], set | list | tuple):
                        vals["name"] = ", ".join(str(n) for n in vals["name"]) if vals["name"] else ""

                attachment_names = ", ".join(str(x["name"]) for x in attachment_vals_list)
                try:
                    self.env["ir.attachment"].create(attachment_vals_list)
                except AccessError:
                    _logger.info(
                        "Cannot save PDF report %r attachments for user %r",
                        attachment_names,
                        self.env.user.display_name,
                    )
                else:
                    _logger.info("The PDF documents %r are now saved in the database", attachment_names)

        def custom_handle_merge_pdfs_error(error, error_stream):
            error_record_ids.append(stream_to_ids[error_stream])

        stream_to_ids = {v["stream"]: k for k, v in collected_streams.items() if v["stream"]}
        # Merge all streams together for a single record.
        streams_to_merge = list(stream_to_ids.keys())
        error_record_ids = []

        if len(streams_to_merge) == 1:
            pdf_content = streams_to_merge[0].getvalue()
        else:
            with self._merge_pdfs(streams_to_merge, custom_handle_merge_pdfs_error) as pdf_merged_stream:
                pdf_content = pdf_merged_stream.getvalue()

        if error_record_ids:
            action = {
                "type": "ir.actions.act_window",
                "name": _("Problematic record(s)"),
                "res_model": report_sudo.model,
                "domain": [("id", "in", error_record_ids)],
                "views": [(False, "list"), (False, "form")],
            }
            num_errors = len(error_record_ids)
            if num_errors == 1:
                action.update(
                    {
                        "views": [(False, "form")],
                        "res_id": error_record_ids[0],
                    }
                )
            raise RedirectWarning(
                message=_(
                    "Odoo is unable to merge the generated PDFs because of %(num_errors)s corrupted file(s)",
                    num_errors=num_errors,
                ),
                action=action,
                button_text=_("View Problematic Record(s)"),
            )

        for stream in streams_to_merge:
            stream.close()

        if res_ids:
            _logger.info(
                "The PDF report has been generated for model: %s, records %s.", report_sudo.model, str(res_ids)
            )

        return pdf_content, "onlyoffice-pdf"

    def fill_template(self, oo_security_token, record_ids, template_id):
        _logger.info("fill_template - template: %s, records: %s", template_id, record_ids)
        docserver_url = config_utils.get_doc_server_public_url(self.env)
        docserver_url = url_utils.replace_public_url_to_internal(self.env, docserver_url)
        docbuilder_url = f"{docserver_url}docbuilder"
        jwt_header = config_utils.get_jwt_header(self.env)
        jwt_secret = config_utils.get_jwt_secret(self.env)
        odoo_url = config_utils.get_base_or_odoo_url(self.env)

        docbuilder_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        docbuilder_callback_url = f"{odoo_url}onlyoffice/template/callback/docbuilder/fill_template?oo_security_token={oo_security_token}&record_ids={','.join([str(record) for record in record_ids])}&template_id={template_id.id}"  # noqa: E501
        docbuilder_payload = {"async": False, "url": docbuilder_callback_url}

        _logger.info("fill_template - docserver_url: %s", docserver_url)
        _logger.info("fill_template - jwt_enabled: %s", bool(jwt_secret))

        if jwt_secret:
            docbuilder_payload["token"] = jwt_utils.encode_payload(self.env, docbuilder_payload, jwt_secret)
            docbuilder_headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(
                self.env, {"payload": docbuilder_payload}, jwt_secret
            )

        try:
            if jwt_secret:
                docbuilder_response = onlyoffice_request(
                    url=docbuilder_url,
                    method="post",
                    opts={
                        "json": docbuilder_payload,
                        "headers": docbuilder_headers,
                    },
                )
            else:
                docbuilder_response = onlyoffice_request(
                    url=docbuilder_url,
                    method="post",
                    opts={
                        "json": docbuilder_payload,
                    },
                )
            docbuilder_json = docbuilder_response.json()
            if docbuilder_json.get("error"):
                e = self.get_docbuilder_error(docbuilder_json.get("error"))
                _logger.warning("fill_template - docbuilder error: %s", e)
                raise Exception(e)

            urls = docbuilder_json.get("urls")
            _logger.info("fill_template - success, got %s URLs", len(urls) if urls else 0)
            return urls
        except Exception as e:
            _logger.warning("fill_template - error: %s", str(e))
            raise

    def get_docbuilder_error(self, error_code):
        docbuilder_messages = {
            -1: "Unknown error.",
            -2: "Generation timeout error.",
            -3: "Document generation error.",
            -4: "Error while downloading the document file to be generated.",
            -6: "Error while accessing the document generation result database.",
            -8: "Invalid token.",
        }
        return docbuilder_messages.get(error_code, "Error code not recognized.")
