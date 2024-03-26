# -*- coding: utf-8 -*-

#
# (c) Copyright Ascensio System SIA 2023
#

from odoo import http, SUPERUSER_ID
from odoo.http import request
from odoo.tools.translate import _

from odoo.addons.onlyoffice_odoo.utils import file_utils
from odoo.addons.onlyoffice_odoo.utils import jwt_utils
from odoo.addons.onlyoffice_odoo.utils import config_utils

import base64
import requests
import json
import datetime
from urllib.request import urlopen

class OnlyofficeTemplate_Connector(http.Controller):
    @http.route("/onlyoffice/template/file/create", auth="user", methods=["POST"], type="json")
    def template_create(self):
        file_data = file_utils.get_default_file_template(request.env.user.lang, "docx")
        mimetype = file_utils.get_mime_by_ext("docx")

        attachment = request.env['onlyoffice.template'].create({
            "name": "new_template.docxf",
            "file": base64.encodebytes(file_data),
            "mimetype": mimetype
        })
        
        return {
            "file_id": attachment.attachment_id.id
        }
    
    @http.route("/onlyoffice/upload_file_from_url", auth="user", methods=["POST"], type="json")
    def post_file_create(self, url, title):
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            if response.status_code != 200:
                raise Exception("HTTP error", response.status_code)
            if 'Content-Length' not in response.headers:
                raise Exception("Empty file")
            if not response.headers['Content-Type']:
                raise Exception("Unknown content type")

            filename = title
            data = urlopen(url).read()


            attachment = request.env['onlyoffice.template'].create({
                "name": filename,
                "file": base64.encodebytes(data),
                "mimetype": response.headers['Content-Type'],
            })
            
            return {'ids': attachment.id}

        except Exception as e:
            raise Exception("error", str(e))
    
    @http.route("/onlyoffice/template/fill", auth="user", methods=["POST"], type="json")
    def fill_template(self, template_id, record_id, model_name):
        jwt_secret="secret"
        jwt_header="Authorization"

        template_attachment_id = http.request.env["onlyoffice.template"].browse(template_id).attachment_id.id

        oo_security_token = jwt_utils.encode_payload(request.env, { "id": request.env.user.id }, config_utils.get_internal_jwt_secret(request.env))

        data_url = "http://192.168.0.100:8069/onlyoffice/callback/template/fill"
        data_url_with_params = f"{data_url}?template_attachment_id={template_attachment_id}&model_name={model_name}&record_id={record_id}&oo_security_token={oo_security_token}"
        data = {
            "async": False,
            "url": data_url_with_params
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if bool(jwt_secret):
            payload = {"payload": data}
            header_token = jwt_utils.encode_payload(request.env, payload, jwt_secret)
            headers[jwt_header] = "Bearer " + header_token
            token = jwt_utils.encode_payload(request.env, data, jwt_secret)
            data["token"] = token

        request_url = "http://documentserver/docbuilder"
        response = requests.post(request_url, data=json.dumps(data), headers = headers)
        
        response_json = json.loads(response.text)

        urls = response_json.get('urls')
        if urls:
            first_url = next(iter(urls.values()), None)
            if first_url:
                return {'href': first_url}

        error_code = response_json.get('error')
        if error_code:
            error_messages = {
                -1: "Unknown error.",
                -2: "Generation timeout error.",
                -3: "Document generation error.",
                -4: "Error while downloading the document file to be generated.",
                -6: "Error while accessing the document generation result database.",
                -8: "Invalid token."
            }
            return {'error': error_messages.get(error_code, "Error code not recognized.")}

        return {'error': "Unknown error"}
    
    @http.route("/onlyoffice/callback/template/fill", auth="public")
    def template_callback(self, template_attachment_id, model_name, record_id, oo_security_token=None):
        record_id = int(record_id)
        record = http.request.env[model_name].with_user(SUPERUSER_ID).browse(record_id)
        record_values = record.read(fields=None)[0]

        non_array_items = []
        array_items = []
        markup_items = []

        for key, value in record_values.items():
            field_dict = {f"{model_name}_{key}": None}
            
            if hasattr(value, '__html__'):
                field_dict[f"{model_name}_{key}"] = str(value)
                markup_items.append(field_dict)
            elif isinstance(value, list) and value and http.request.env[model_name]._fields[key].type in ['one2many', 'many2many']:
                related_model = http.request.env[model_name]._fields[key].comodel_name
                related_records = http.request.env[related_model].with_user(SUPERUSER_ID).browse(value)
                related_values = related_records.read(fields=None)
                field_dict[f"{model_name}_{key}"] = related_values
                array_items.append(field_dict)
            else:
                if isinstance(value, tuple) and len(value) == 2:
                    field_dict[f"{model_name}_{key}"] = value[1]
                elif isinstance(value, datetime.datetime):
                    field_dict[f"{model_name}_{key}"] = value.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(value, datetime.date):
                    field_dict[f"{model_name}_{key}"] = value.strftime('%Y-%m-%d')
                else:
                    field_dict[f"{model_name}_{key}"] = value
                non_array_items.append(field_dict)

        url = "http://192.168.0.100:8069/onlyoffice/template/download/" + template_attachment_id
        url_with_params = f"{url}?oo_security_token={oo_security_token}"

        non_array_items_dict = {key: value for d in non_array_items for key, value in d.items()}
        def python_to_js(value):
            if isinstance(value, bool):
                return str(value).lower()
            elif value is None:
                return 'null'
            elif isinstance(value, (int, float)):
                return f'{value}'
            return value

        formatted_non_array_items = {k: python_to_js(v) for k, v in non_array_items_dict.items()}
        json_non_array_items = json.dumps(formatted_non_array_items, indent=4)
        json_non_array_items = json_non_array_items.replace('true', 'true').replace('false', 'false').replace('null', 'null')


        file_content = f"""
        builder.OpenFile("{url_with_params}");
        var oDocument = Api.GetDocument();

        var data = {json_non_array_items};

        var aForms = oDocument.GetAllForms();
        aForms.forEach(form => {{
            if (form.GetFormType() == "textForm") form.SetText(data[form.GetFormKey()]);
            if (form.GetFormType() == "checkBoxForm") {{
                var value = data[form.GetFormKey()];
                if (value) {{
                    try {{
                        var parsedValue = JSON.parse(value);
                        form.SetChecked(parsedValue);
                    }} catch (_e) {{
                        form.SetChecked(value);
                    }}
                }}
            }}
        }});

        Api.Save();
        builder.SaveFile("docxf", "output.docx");
        builder.CloseFile();
        """

        headers = {
            'Content-Disposition': 'attachment; filename="fillform.docbuilder"',
            'Content-Type': 'text/plain',
        }
        return request.make_response(file_content, headers)
    
    @http.route("/onlyoffice/template/download/<int:template_attachment_id>", auth="public")
    def download_docxf(self, template_attachment_id, oo_security_token=None):
        attachment = request.env['ir.attachment'].sudo().browse(template_attachment_id)
        
        if attachment:
            file_content = base64.b64decode(attachment.datas)
            headers = {
                'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'Content-Disposition': 'attachment; filename="form.docxf"',
            }
            return request.make_response(file_content, headers)
        else:
            return request.not_found()