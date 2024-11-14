# Setting up a development environment

```bash
npm install
python3 -m venv .venv
For Windows: .venv\Scripts\activate.bat
For Unix: source ./.venv/bin/activate
pip install -v -e .[dev]
pre-commit install
```

# Pre-commit

This project uses pre-commit for all style checking. Run:

```bash
pre-commit run -a
```

to check all files.

# Visual Studio Code Extensions

- [ESLint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint)
- [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
- [Pylint](https://marketplace.visualstudio.com/items?itemName=ms-python.pylint)
- [Prettier](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode)
