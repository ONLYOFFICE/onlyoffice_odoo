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
