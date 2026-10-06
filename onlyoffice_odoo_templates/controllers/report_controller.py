# Copyright (C) 2026 Data Dance s.r.o.
# License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

import json
import logging

from werkzeug.urls import url_decode

from odoo.http import request, route
from odoo.http.dispatcher import serialize_exception as _serialize_exception
from odoo.http.stream import content_disposition
from odoo.tools import html_escape
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.web.controllers.report import ReportController

_logger = logging.getLogger(__name__)


class ReportController(ReportController):  # noqa: pylint shadowing is Odoo's controller-override idiom
    @route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        if converter == "onlyoffice-pdf":
            report = request.env["ir.actions.report"]._get_report_from_name(reportname)
            context = dict(request.env.context)
            if docids:
                docids = [int(i) for i in docids.split(",")]
            try:
                if data.get("options"):
                    data.update(json.loads(data.pop("options")))
                if data.get("context"):
                    data["context"] = json.loads(data["context"])
                    context.update(data["context"])
            except (ValueError, TypeError) as e:
                return request.make_response(
                    html_escape(json.dumps({"code": 400, "message": f"Invalid report payload: {e}"})),
                    status=400,
                )
            pdf = report.with_context(**context)._render_onlyoffice_pdf(reportname, docids, data=data)[0]
            pdfhttpheaders = [
                (
                    "Content-Type",
                    "application/pdf",
                ),
                ("Content-Length", len(pdf)),
            ]
            return request.make_response(pdf, headers=pdfhttpheaders)
        return super().report_routes(reportname, docids, converter, **data)

    @route()
    def report_download(self, data, context=None, token=None, readonly=True):
        try:
            requestcontent = json.loads(data)
        except ValueError as e:
            return request.make_response(
                html_escape(json.dumps({"code": 400, "message": f"Invalid download payload: {e}"})),
                status=400,
            )
        url, report_type = requestcontent[0], requestcontent[1]
        if report_type == "onlyoffice-pdf":
            reportname = None
            try:
                reportname = url.split("/report/onlyoffice-pdf/")[1].split("?")[0]
                docids = None
                if "/" in reportname:
                    reportname, docids = reportname.split("/")
                if docids:
                    # Generic report:
                    response = self.report_routes(
                        reportname, docids=docids, converter="onlyoffice-pdf", context=context
                    )
                else:
                    # Particular report:
                    data = dict(url_decode(url.split("?")[1]).items())  # decoding the args represented in JSON
                    if "context" in data:
                        context, data_context = (
                            json.loads(context or "{}"),
                            json.loads(data.pop("context")),
                        )
                        context = json.dumps({**context, **data_context})
                    response = self.report_routes(reportname, converter="onlyoffice-pdf", context=context, **data)

                report = request.env["ir.actions.report"]._get_report_from_name(reportname)
                filename = f"{report.name}.pdf"

                if docids:
                    ids = [int(x) for x in docids.split(",")]
                    obj = request.env[report.model].browse(ids)
                    if report.print_report_name and not len(obj) > 1:
                        report_name = safe_eval(report.print_report_name, {"object": obj, "time": time})
                        filename = f"{report_name}.pdf"
                if not response.headers.get("Content-Disposition"):
                    response.headers.add("Content-Disposition", content_disposition(filename))
                return response
            except Exception as e:
                _logger.exception("Error while generating report %s", reportname or report_type)
                se = _serialize_exception(e)
                error = {"code": 200, "message": "Odoo Server Error", "data": se}
                return request.make_response(html_escape(json.dumps(error)))
        else:
            return super().report_download(data, context, token=token, readonly=readonly)
