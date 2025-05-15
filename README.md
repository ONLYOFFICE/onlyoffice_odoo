# ONLYOFFICE app for Odoo

This app allows users to edit and collaborate on office documents within [Odoo](https://www.odoo.com/) Documents using ONLYOFFICE Docs packaged as Document Server - [Community or Enterprise Edition](#onlyoffice-docs-editions).

## Features

The app allows to:

* Edit text documents, spreadsheets, and presentations.
* Co-edit documents in real time using two co-editing modes (Fast and Strict), Track Changes, comments, and built-in chat.

Supported formats:

* For editing: DOCX, XLSX, PPTX, PDF.
* For viewing: DJVU, DOC, DOCM, DOCXF, DOT, DOTM, DOTX, EPUB, FB2, FODT, HTML, MHT, ODT, OFORM, OTT, OXPS, RTF, TXT, XPS, XML, CSV, FODS, ODS, OTS, XLS, XLSB, XLSM, XLT, XLTM, XLTX, FODP, ODP, OTP, POT, POTM, POTX, PPS, PPSM, PPSX, PPT, PPTM.

## Installing ONLYOFFICE Docs

You will need an instance of ONLYOFFICE Docs (Document Server) that is resolvable and connectable both from Odoo and any end-clients. ONLYOFFICE Document Server must also be able to POST to Odoo directly.

You can install free Community version of ONLYOFFICE Docs or scalable Enterprise Edition.

To install free Community version, use [Docker](https://github.com/onlyoffice/Docker-DocumentServer) (recommended) or follow [these instructions](https://helpcenter.onlyoffice.com/installation/docs-community-install-ubuntu.aspx) for Debian, Ubuntu, or derivatives.  

To install Enterprise Edition, follow instructions [here](https://helpcenter.onlyoffice.com/installation/docs-enterprise-index.aspx).

Community Edition vs Enterprise Edition comparison can be found [here](#onlyoffice-docs-editions).

## Installing ONLYOFFICE app for Odoo

**Installation from the admin panel**

* [Log into](https://www.odoo.com/web/login) your exisiting Odoo account or [sign up](https://www.odoo.com/web/signup) for a new account.
* Go to the Odoo administration panel and click ‘Apps’ on the top menu bar.
* Search for ONLYOFFICE in the Apps catalog. 
* Click the 'Install' button.

**Manual installation**

Navigate to the [Odoo Apps catalog](https://apps.odoo.com/apps) and select the Odoo version you have installed. Search for ONLYOFFICE and download it. You can also download the latest app version from the official [GitHub repo](https://github.com/ONLYOFFICE/onlyoffice-odoo/releases).

Put ONLYOFFICE app into `/path/to/odoo/addons`. Make sure the ONLYOFFICE folder is named as `onlyoffice_odoo`.

Alternatively, you can add the following lines in the `/path/to/odoo/config/odoo.conf` file specifying your path to the folder with apps/addons:

```
[options]
addons_path = /mnt/extra-addons
```

Then, install the package:
`pip install pyjwt`

Once ready, switch your Odoo to the developer mode and click **Apps -> Update Apps List** OR just restart your Odoo instance.

**Please note (refers to the ONLYOFFICE Templates app)**: ONLYOFFICE demo templates will only be added to the Odoo modules that are already installed. That's why we strongly recommend installing ONLYOFFICE Templates after installing other Odoo modules such as CRM, Sales, Calendar, etc.
 
## Configuring ONLYOFFICE app for Odoo

To configure the app, go to `Settings`. Find `ONLYOFFICE` on the left sidebar and press it. Specify the URL of the installed ONLYOFFICE Document Server.

Starting from version 7.2, JWT is enabled by default and the secret key is generated automatically to restrict the access to ONLYOFFICE Docs and for security reasons and data integrity. 
You can specify your own **Secret key** on the Odoo configuration page. 
In the ONLYOFFICE Docs [config file](https://api.onlyoffice.com/editors/signature/), specify the same secret key and enable the validation.

## ONLYOFFICE Docs editions

ONLYOFFICE offers different versions of its online document editors that can be deployed on your own servers.

**ONLYOFFICE Docs** packaged as Document Server:

* Community Edition (`onlyoffice-documentserver` package)
* Enterprise Edition (`onlyoffice-documentserver-ie` package)

The table below will help you make the right choice.

| Pricing and licensing | Community Edition | Enterprise Edition |
| ------------- | ------------- | ------------- |
| | [Get it now](https://www.onlyoffice.com/download-docs.aspx#docs-community)  | [Start Free Trial](https://www.onlyoffice.com/download-docs.aspx#docs-enterprise)  |
| Cost  | FREE  | [Go to the pricing page](https://www.onlyoffice.com/docs-enterprise-prices.aspx)  |
| Simultaneous connections | up to 20 maximum  | As in chosen pricing plan |
| Number of users | up to 20 recommended | As in chosen pricing plan |
| License | GNU AGPL v.3 | Proprietary |
| **Support** | **Community Edition** | **Enterprise Edition** |
| Documentation | [Help Center](https://helpcenter.onlyoffice.com/installation/docs-community-index.aspx) | [Help Center](https://helpcenter.onlyoffice.com/installation/docs-enterprise-index.aspx) |
| Standard support | [GitHub](https://github.com/ONLYOFFICE/DocumentServer/issues) or paid | One year support included |
| Premium support | [Contact us](mailto:sales@onlyoffice.com) | [Contact us](mailto:sales@onlyoffice.com) |
| **Services** | **Community Edition** | **Enterprise Edition** |
| Conversion Service                | + | + |
| Document Builder Service          | + | + |
| **Interface** | **Community Edition** | **Enterprise Edition** |
| Tabbed interface                       | + | + |
| Dark theme                             | + | + |
| 125%, 150%, 175%, 200% scaling         | + | + |
| White Label                            | - | - |
| Integrated test example (node.js)      | + | + |
| Mobile web editors                     | - | +* |
| **Plugins & Macros** | **Community Edition** | **Enterprise Edition** |
| Plugins                           | + | + |
| Macros                            | + | + |
| **Collaborative capabilities** | **Community Edition** | **Enterprise Edition** |
| Two co-editing modes              | + | + |
| Comments                          | + | + |
| Built-in chat                     | + | + |
| Review and tracking changes       | + | + |
| Display modes of tracking changes | + | + |
| Version history                   | + | + |
| **Document Editor features** | **Community Edition** | **Enterprise Edition** |
| Font and paragraph formatting   | + | + |
| Object insertion                | + | + |
| Adding Content control          | + | + | 
| Editing Content control         | + | + | 
| Layout tools                    | + | + |
| Table of contents               | + | + |
| Navigation panel                | + | + |
| Mail Merge                      | + | + |
| Comparing Documents             | + | + |
| **Spreadsheet Editor features** | **Community Edition** | **Enterprise Edition** |
| Font and paragraph formatting   | + | + |
| Object insertion                | + | + |
| Functions, formulas, equations  | + | + |
| Table templates                 | + | + |
| Pivot tables                    | + | + |
| Data validation           | + | + |
| Conditional formatting          | + | + |
| Sparklines                   | + | + |
| Sheet Views                     | + | + |
| **Presentation Editor features** | **Community Edition** | **Enterprise Edition** |
| Font and paragraph formatting   | + | + |
| Object insertion                | + | + |
| Transitions                     | + | + |
| Animations                      | + | + |
| Presenter mode                  | + | + |
| Notes                           | + | + |
| **Form creator features** | **Community Edition** | **Enterprise Edition** |
| Adding form fields           | + | + |
| Form preview                    | + | + |
| Saving as PDF                   | + | + |
| **Working with PDF**      | **Community Edition** | **Enterprise Edition** |
| Text annotations (highlight, underline, cross out) | + | + |
| Comments                        | + | + |
| Freehand drawings               | + | + |
| Form filling                    | + | + |
| | [Get it now](https://www.onlyoffice.com/download-docs.aspx#docs-community)  | [Start Free Trial](https://www.onlyoffice.com/download-docs.aspx#docs-enterprise)  |

\* If supported by DMS.

In case of technical problems, the best way to get help is to submit your issues [here](https://github.com/ONLYOFFICE/onlyoffice-odoo/issues). Alternatively, you can contact ONLYOFFICE team on [forum.onlyoffice.com](https://forum.onlyoffice.com/).
