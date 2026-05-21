# ONLYOFFICE app for Odoo

This app allows users to edit and collaborate on office documents within [Odoo](https://www.odoo.com/) using [ONLYOFFICE Docs](https://www.onlyoffice.com/docs).

## Features ✨

- **Edit and view text documents, spreadsheets, presentations, and PDFs attached or uploaded to Odoo Community.**

<p align="center">
  <a href="https://www.onlyoffice.com/office-for-odoo">
    <img width="800" src="https://static-site.onlyoffice.com/public/images/templates/office-for-odoo/community/community-1@2x.png" alt="ONLYOFFICE for Odoo">
  </a>
</p>

- **Create, edit, and co-author office files in the Odoo Enterprise Documents.**

<p align="center">
  <a href="https://www.onlyoffice.com/office-for-odoo">
    <img width="800" src="https://static-site.onlyoffice.com/public/images/templates/office-for-odoo/enterprise/enterprise-1@2x.png" alt="ONLYOFFICE for Odoo">
  </a>
</p>

- **Work with fillable form templates in Odoo.**

<p align="center">
  <a href="https://www.onlyoffice.com/office-for-odoo">
    <img width="800" src="https://static-site.onlyoffice.com/public/images/templates/office-for-odoo/fillable-form/fillable-form-2@2x.png" alt="ONLYOFFICE for Odoo">
  </a>
</p>

### Supported formats

**For viewing:**
* **WORD**: DOC, DOCM, DOCX, DOT, DOTM, DOTX, EPUB, FB2, FODT, HTM, HTML, HWP, HWPX, MD, MHT, MHTML, ODT, OTT, PAGES, RTF, STW, SXW, TXT, WPS, WPT, XML
* **CELL**: CSV, ET, ETT, FODS, NUMBERS, ODS, OTS, SXC, XLS, XLSM, XLSX, XLT, XLTM, XLTX
* **SLIDE**: DPS, DPT, FODP, KEY, ODG, ODP, OTP, POT, POTM, POTX, PPS, PPSM, PPSX, PPT, PPTM, PPTX, SXI
* **PDF**: DJVU, DOCXF, OFORM, OXPS, PDF, XPS
* **DIAGRAM**: VSDM, VSDX, VSSM, VSSX, VSTM, VSTX

**For editing:**

* **WORD**: DOCM, DOCX, DOTM, DOTX
* **CELL**: XLSB, XLSM, XLSX, XLTM, XLTX
* **SLIDE**: POTM, POTX, PPSM, PPSX, PPTM, PPTX
* **PDF**: PDF

## Installing ONLYOFFICE Docs

To use the integration, you need a running instance of ONLYOFFICE Docs (Document Server) that is resolvable and connectable both from Odoo and clients browsers. ONLYOFFICE Document Server must also be able to POST to Odoo directly.

### 🖥️ Self-hosted

**Community Edition (Free)** - install via [Docker](https://github.com/onlyoffice/Docker-DocumentServer) (recommended) or follow [manual installation instructions](https://helpcenter.onlyoffice.com/installation/docs-community-install-ubuntu.aspx) for Debian/Ubuntu.

**Enterprise Edition** - scalable and professionally supported. [Installation Guide →](https://helpcenter.onlyoffice.com/docs/installation/enterprise)

Community Edition vs Enterprise Edition comparison can be found [here](#onlyoffice-docs-editions).

### ☁️ Cloud

If you prefer not to host and maintain your own server, use **ONLYOFFICE Docs Cloud**, which requires no installation or configuration.

👉 [Get started here](https://www.onlyoffice.com/docs-registration)

## Installing ONLYOFFICE app for Odoo

**Installation from the admin panel**

* [Log into](https://www.odoo.com/web/login) your exisiting Odoo account or [sign up](https://www.odoo.com/web/signup) for a new account.
* Go to the Odoo administration panel and click **Apps** on the top menu bar.
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

To configure the app, go to `Settings`. Find `ONLYOFFICE` on the left sidebar and press it. Specify the URL of the installed ONLYOFFICE Docs.

Configuration settings include JWT, enabled by default to protect the editors from unauthorized access. If setting a custom **Secret key**, ensure it matches the one in the ONLYOFFICE Docs [config file](https://api.onlyoffice.com/docs/docs-api/additional-api/signature/) for proper validation.

## ONLYOFFICE Docs editions

ONLYOFFICE offers different versions of its online document editors that can be deployed on your own servers.

* Community Edition 🆓 (`onlyoffice-documentserver` package)
* Enterprise Edition 🏢 (`onlyoffice-documentserver-ee` package)

The table below will help you to make the right choice.

| Pricing and licensing | Community Edition | Enterprise Edition |
| ------------- | ------------- | ------------- |
| | [Get it now](https://www.onlyoffice.com/download-community?utm_source=github&utm_medium=cpc&utm_campaign=GitHubOdoo#docs-community)  | [Start Free Trial](https://www.onlyoffice.com/download?utm_source=github&utm_medium=cpc&utm_campaign=GitHubOdoo#docs-enterprise)  |
| Cost  | FREE  | [Go to the pricing page](https://www.onlyoffice.com/docs-enterprise-prices?utm_source=github&utm_medium=cpc&utm_campaign=GitHubOdoo)  |
| Number of users | up to 20 recommended | As in chosen pricing plan |
| License | GNU AGPL v.3 | Proprietary |
| **Support** | **Community Edition** | **Enterprise Edition** |
| Documentation | [Help Center](https://helpcenter.onlyoffice.com/docs/installation/community) | [Help Center](https://helpcenter.onlyoffice.com/docs/installation/enterprise) |
| Standard support | [GitHub](https://github.com/ONLYOFFICE/DocumentServer/issues) or [Community](https://community.onlyoffice.com/) | 1 or 3 years support included |
| Premium support | [Contact us](mailto:sales@onlyoffice.com) | [Contact us](mailto:sales@onlyoffice.com) |
| **Services** | **Community Edition** | **Enterprise Edition** |
| Conversion Service                | + | + |
| Live Viewer                       | + | + |
| Document Builder Service          | - | - |
| Automation API                    | - | - |
| **Interface** | **Community Edition** | **Enterprise Edition** |
| Tabbed interface                  | + | + |
| Dark theme                        | + | + |
| 125%, 150%, 175%, 200% scaling    | + | + |
| White Label                       | - | - |
| Integrated test example (node.js) | + | + |
| Admin Panel                       | - | + |
| Mobile web editors                | - | +* |
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
| Comparing documents             | + | + |
| Multipage View                  | + | + |
| **Spreadsheet Editor features** | **Community Edition** | **Enterprise Edition** |
| Font and paragraph formatting   | + | + |
| Object insertion                | + | + |
| Functions, formulas, equations  | + | + |
| Table templates                 | + | + |
| Pivot tables                    | + | + |
| Data validation                 | + | + |
| Conditional formatting          | + | + |
| Sparklines                      | + | + |
| Sheet Views                     | + | + |
| Solver                          | + | + |
| **Presentation Editor features** | **Community Edition** | **Enterprise Edition** |
| Font and paragraph formatting   | + | + |
| Object insertion                | + | + |
| Transitions                     | + | + |
| Animations                      | + | + |
| Presenter mode                  | + | + |
| Notes                           | + | + |
| Slide Master                    | + | + |
| **Form creator features** | **Community Edition** | **Enterprise Edition** |
| Adding form fields              | + | + |
| Form preview                    | + | + |
| Saving as PDF                   | + | + |
| Role-matching colors for fields | + | + |
| **PDF Editor features**      | **Community Edition** | **Enterprise Edition** |
| Text editing and co-editing                                | + | + |
| Work with pages (adding, deleting, rotating)               | + | + |
| Inserting objects (shapes, images, hyperlinks, etc.)       | + | + |
| Text annotations (highlight, underline, cross out, stamps) | + | + |
| Redact                          | + | + |
| Comments                        | + | + |
| Freehand drawings               | + | + |
| Form filling                    | + | + |
| | [Get it now](https://www.onlyoffice.com/download-community?utm_source=github&utm_medium=cpc&utm_campaign=GitHubOdoo#docs-community)  | [Start Free Trial](https://www.onlyoffice.com/download?utm_source=github&utm_medium=cpc&utm_campaign=GitHubOdoo#docs-enterprise)  |

\* If supported by DMS.

## Need help? User Feedback and Support 💡

* **🐞 Found a bug?** Please report it by creating an [issue](https://github.com/ONLYOFFICE/onlyoffice-odoo/issues).
* **❓ Have a question?** Ask our community and developers on the [ONLYOFFICE Forum](https://community.onlyoffice.com).
* **👨‍💻 Need help for developers?** Check our [API documentation](https://api.onlyoffice.com).
