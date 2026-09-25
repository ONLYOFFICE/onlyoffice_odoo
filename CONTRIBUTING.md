# Setting up a development environment

```bash
npm install
python -m venv .venv
For Windows: .venv\Scripts\activate.bat
For Unix: source ./.venv/bin/activate
pip install -v -e .[dev]
pre-commit install
```

This installs all development dependencies:

- **coverage** — test coverage reporting
- **pylint + pylint-odoo** — Odoo-specific linting
- **ruff** — fast Python linter & formatter
- **pyjwt** — JWT library (runtime dependency)
- **pre-commit** — git hooks framework

# Pre-commit

This project uses pre-commit for all style checking. Run:

```bash
pre-commit run -a
```

to check all files (ruff, pylint, prettier, eslint, OCA checks).

## Running tests with coverage

```bash
# Run tests + coverage via pre-commit (manual stage):
pre-commit run odoo-tests-coverage --hook-stage manual
```

### Running tests via Docker

If Odoo runs in a Docker container, use:

```bash
docker exec <container_name> odoo -d <db> --test-enable --stop-after-init \
  -i onlyoffice_odoo --log-level=test \
  --db_host=db --db_port=5432 --db_user=odoo --db_password=odoo
```

# Visual Studio Code Extensions

- [ESLint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint)
- [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
- [Pylint](https://marketplace.visualstudio.com/items?itemName=ms-python.pylint)
- [Prettier](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode)

## End-to-end tests (Playwright)

Browser tests against a live ONLYOFFICE Docs live in `e2e/` and run in CI on every push and pull request
(`.github/workflows/e2e.yml`, PostgreSQL and the Document Server as job services). They connect the Document Server
through Settings, post docx/xlsx/pptx files to a Discuss channel, edit them in the editor and check that the files are
saved back, and print, preview, create and export ONLYOFFICE templates. Locally the stack (Odoo 17, PostgreSQL, Document
Server) is started with Docker Compose; see `e2e/README.md` for details and the environment variables.

```bash
cd e2e
npm run setup   # once
npm run e2e     # stack up, tests, stack down
```
