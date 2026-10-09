# API Client

A lightweight, fast desktop REST client for backend developers, focused on Spring Boot projects.
Think Postman or Thunder Client with only the features you use every day, and with your requests
stored **inside your repository** so the whole team shares them through Git.

![API Client, dark theme](docs/screenshot-dark.png)

## Features

- **Projects bound to your backend repo.** Everything lives in `<your-backend>/api-client/` as readable JSON.
- **Collections and requests.** Create, rename, duplicate, move and delete them from the sidebar or context menus.
- **All HTTP methods:** GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS.
- **Query params and path variables** (`/api/productos/{id}`), both in editable tables. The final URL is previewed live.
- **Headers** with autocomplete for common names and values.
- **Auth:** None, Bearer Token and Basic Auth. The design allows adding OAuth2 later.
- **JSON body editor** with syntax highlighting, line numbers, auto-indent, Format (Ctrl+Shift+F) and inline validation
  (`Invalid JSON — line 5`) that also marks the bad line. `{{variables}}` inside JSON are supported.
- **Environments and variables:** `{{base_url}}`, `{{token}}`… with per-environment values. Undefined variables are
  underlined in red in the URL, and hovering one shows its value. The `{}` button next to the environment selector
  (Ctrl+Shift+E) opens a floating window to search, add, rename and delete variables and environments; every edit is
  saved right away.
- **Secrets** in a git-ignored `.secrets.json`, masked in logs, history and cURL exports.
- **Response viewer:** colored status, time and size, pretty-printed JSON, headers, raw view, find (Ctrl+F),
  word wrap, copy and save to file.
- **Non-blocking requests** on a thread pool. **Send** turns into **Cancel** while a request is running.
- **Autosave** with a 700 ms debounce. There is no Ctrl+S habit to keep.
- **Tabs** for open requests. They are restored, along with the environment, splitter sizes and collapsed
  collections, when you reopen the project.
- **History** of sent requests (SQLite) that you can filter and clear.
- **Command palette** (Ctrl+K) to jump to any request or action.
- **Command line** for every feature (`api-client run`, `api-client request add`…), see below.
- **Copy as cURL**, which warns you and masks secrets when the request carries credentials.
- **Import from OpenAPI 3** (**New › Import OpenAPI…**): load the spec from `{{base_url}}/v3/api-docs` (springdoc) or
  a JSON file, preview it, and get one collection per controller with path variables, query params, auth and a sample
  JSON body built from the schema. Importing again only adds endpoints that are new (same method and path are left
  untouched).
- **Dark theme** by default, plus Light and System.
- **English and Spanish interface**: follows the system language by default, and you can change it in
  Settings → Appearance.
- **Readable errors** for connection refused, timeouts, DNS, SSL, invalid URLs, missing variables and corrupt
  files. A broken JSON file is skipped and **never overwritten**.

## Requirements

- Python **3.12+**
- Linux, Windows or macOS with a desktop session

Dependencies: `PySide6` (UI) and `httpx` (HTTP). Nothing else at runtime.

## Quick install (Linux)

```bash
git clone https://github.com/ezerutp/api-client.git
cd api-client
./install.sh
```

The script:

1. Runs `git pull` to get the latest version. It skips the pull if you have local changes.
2. Finds Python 3.12+ and creates or updates `.venv` with the dependencies.
3. Installs the `api-client` command in `~/.local/bin`, the icon, and an **API Client** entry in your
   applications menu.

Run `./install.sh` again at any time to update. `./install.sh --uninstall` removes the launcher; your
projects and settings are kept. The script never uses sudo or writes outside your home folder.

## Quick install (Windows)

Download `api-client-setup.exe` from the [latest release](https://github.com/ezerutp/api-client/releases)
and run it. The installer:

1. Installs API Client to `%LocalAppData%\Programs\API Client` (no administrator rights needed).
2. Adds that folder to your user `PATH`, so `api-client` works from any terminal.
3. Creates a **Desktop** shortcut and a Start Menu entry.

Uninstall from **Settings → Apps**, like any other Windows program; it also removes the `PATH` entry.
Your projects and settings are kept (they live in your backend repos and `%APPDATA%\api-client`).

To build the installer yourself from this repository:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

This requires Python 3.12+ and [Inno Setup 6](https://jrsoftware.org/isdl.php) (`winget install
JRSoftware.InnoSetup`) on `PATH`. It produces `dist_installer\api-client-setup.exe`. See
`packaging/windows/` for the PyInstaller icon step and the Inno Setup script.

## Manual installation and running

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

You can also pass a backend folder to open it directly:

```bash
python main.py ~/projects/backend-tienda
```

### Try it without a Spring Boot app

The repository includes an example project and a tiny mock backend (standard library only):

```bash
python tools/mock_server.py            # http://localhost:8080
python main.py examples/backend-tienda # in another terminal
```

Open **Productos › Crear producto**, press **Ctrl+Enter**, and you get `201 Created` with the new product.
The mock also serves an OpenAPI spec at `/v3/api-docs`, so **New › Import OpenAPI…** works against it too.

## How `api-client/` works

When you open a backend folder, the app looks for `api-client/project.json` inside it. If the file doesn't
exist, it offers to create it.

```
backend-tienda/
├── src/
├── pom.xml
└── api-client/
    ├── project.json      ← name, base URL, environments, variables (committed)
    ├── productos.json    ← one file per collection (committed)
    ├── usuarios.json
    ├── auth.json
    ├── .secrets.json     ← tokens, passwords (NOT committed)
    └── .gitignore        ← contains ".secrets.json"
```

**project.json**

```json
{
  "schema_version": 1,
  "name": "Backend Tienda",
  "base_url": "http://localhost:8080",
  "active_environment": "local",
  "variables": { "product_id": "1" },
  "environments": {
    "local":       { "base_url": "http://localhost:8080" },
    "development": { "base_url": "https://dev.api.midominio.com" },
    "production":  { "base_url": "https://api.midominio.com" }
  },
  "collections": ["productos", "usuarios", "auth"]
}
```

`active_environment` is only the default for someone opening the project for the first time. The environment
you pick is remembered on your machine, so switching environments never changes a committed file.

**A collection file** (`productos.json`)

```json
{
  "id": "productos",
  "name": "Productos",
  "base_path": "/api/productos",
  "requests": [
    {
      "id": "create-product",
      "name": "Crear producto",
      "method": "POST",
      "url": "{{base_url}}/api/productos",
      "params": [],
      "path_params": [],
      "headers": [{ "enabled": true, "key": "Accept", "value": "application/json" }],
      "auth": { "type": "bearer", "token": "{{token}}" },
      "body": { "type": "json", "content": "{\n  \"nombre\": \"Monitor\",\n  \"precio\": 800\n}" },
      "created_at": "2026-09-25T10:00:00Z",
      "updated_at": "2026-09-25T10:00:00Z"
    }
  ]
}
```

`base_path` mirrors the controller's `@RequestMapping`. New requests in the collection start with
`{{base_url}}` followed by that path. Files are written atomically (temp file, then rename), with 2-space
indentation, so diffs stay small and reviewable.

### Variables

Write `{{name}}` anywhere: URL, params, path variable values, headers, auth fields or body. The app resolves
them just before sending. Sources, where later ones win:

1. `base_url` from `project.json`
2. Global variables (`variables` in `project.json`)
3. Global secrets (`.secrets.json`)
4. Variables of the active environment
5. Secrets of the active environment

Variables may reference other variables. Circular references and undefined variables are reported clearly
before any request is sent. Substitution is plain text replacement: nothing is ever evaluated.

### Secrets

Keep tokens, passwords and API keys in `.secrets.json`:

```json
{
  "api_key": "global secret, available in every environment",
  "local":      { "token": "abc123" },
  "production": { "token": "xyz789", "password": "..." }
}
```

You can also manage them from the **Environment variables** window (Ctrl+Shift+E): turn on the **Secret** switch
next to a variable to store its value in `.secrets.json` instead of `project.json`. The file is listed in `api-client/.gitignore`, which is created
automatically. Secret values are masked in log files, history entries, the URL preview and cURL exports
(unless you explicitly choose to include them).

## Command line

Everything the app does is also available from the terminal, so you can script it or use it on a server or in
CI (Qt is not loaded). `api-client` with no arguments, or with a folder, still opens the desktop app; with a
command it runs the CLI:

```bash
api-client project init ~/backend-tienda --name Tienda --base-url http://localhost:8080
cd ~/backend-tienda                      # the project is found from this folder or any subfolder (or pass -C DIR)

api-client collection add Productos --base-path /api/productos
api-client request add productos "Crear producto" -X POST --bearer '{{token}}' -d @producto.json
api-client request add productos "Ver" --url '{{base_url}}/api/productos/{id}' -P id=1
api-client var set token --secret        # prompts without echo; also: var set token VALUE / '-' for stdin
api-client env add staging --base-url https://staging.example.com
api-client run productos/Ver -e staging  # body to stdout, status line to stderr
api-client run "Crear producto" -i --fail
api-client curl Ver                      # secrets masked unless --show-secrets
api-client import openapi                # {{base_url}}/v3/api-docs by default; also a URL or a JSON file
api-client import curl productos < request.sh
```

| Command | Actions |
|---|---|
| `project` | `init`, `show`, `set --name/--base-url` |
| `collection` (`col`) | `ls`, `add`, `rename`, `duplicate`, `move up/down`, `rm` |
| `request` (`req`) | `ls`, `show`, `add`, `edit`, `rename`, `duplicate`, `move`, `rm` |
| `run` (`send`) | send a request (`-e ENV`, `-i`, `--raw`, `-o FILE`, `--fail`, `--timeout`, `-k`) |
| `curl` | print a request as a cURL command |
| `env` | `ls`, `add`, `rename`, `duplicate`, `rm`, `use` (default environment) |
| `var` | `ls`, `set [--secret] [-e ENV]`, `rm` |
| `import` | `openapi [--only COLLECTION] [--dry-run]`, `curl` |
| `history` | `ls`, `clear` |
| `settings` | `ls`, `set KEY VALUE` (e.g. `network.timeout_seconds 60`) |

Requests are selected by id, `collection/name` or a name that is unique in the project. Collections are
selected by id or name. Listing commands accept `--json`, and destructive ones ask for confirmation (or `--yes`).
Run `api-client <command> -h` for every option. History and settings are shared with the desktop app.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+Enter | Send the request (works from any field) |
| Ctrl+N | New request |
| Ctrl+Shift+N | New collection |
| Ctrl+L | Select the URL |
| Ctrl+W | Close the tab (the request is kept) |
| Ctrl+Shift+F | Format the JSON body |
| Ctrl+K / Ctrl+Shift+P | Command palette |
| Ctrl+E | Switch environment |
| Ctrl+Shift+E | Environment variables window |
| Ctrl+P | Search the sidebar |
| Ctrl+F | Find in the response |
| Ctrl+D | Duplicate the request |
| Ctrl+S | Save now (autosave already does it) |
| Ctrl+H | History |
| Ctrl+Tab / Ctrl+Shift+Tab | Next / previous tab |
| Ctrl+O / Ctrl+Shift+O | Open / create a project |
| Ctrl+, | Settings |
| F2 / Delete (sidebar) | Rename / delete the selected item |

## Project structure

```
api_client/
├── main.py                      entry point (desktop app, or the CLI when given a command)
├── app/
│   ├── cli.py                   command line interface (Qt-free)
│   ├── bootstrap.py             QApplication, logging, database, theme
│   ├── models/                  dataclasses: Project, Environment, Collection, ApiRequest,
│   │                            RequestHeader/Parameter/PathParameter, Authentication, ApiResponse,
│   │                            HistoryEntry, AppSettings
│   ├── storage/                 atomic JSON files, SQLite (with migrations), user data paths
│   ├── repositories/            project, collections, secrets, settings, recent projects, history, UI state
│   ├── services/
│   │   ├── variable_service.py  {{variable}} resolution and precedence
│   │   ├── request_builder.py   URL, path/query params, headers, auth, body → PreparedRequest
│   │   ├── http_client_service.py  httpx execution, timing, size, cancellation
│   │   ├── auth_strategies.py   one strategy per auth type (extension point for OAuth2)
│   │   ├── project_service.py   operations on an open api-client/ folder
│   │   ├── json_service.py      validation/formatting that tolerates {{variables}}
│   │   ├── curl_service.py      "Copy as cURL" and cURL import
│   │   └── openapi_service.py   OpenAPI 3 spec → collections and requests
│   ├── network/                 QRunnable worker, exception → readable error mapping
│   ├── importers/               interfaces for future importers/exporters
│   ├── themes/                  palettes (theme.py), QSS template (style.qss), theme manager
│   ├── utils/                   logging with secret redaction, formatting, slugs
│   └── ui/
│       ├── main_window.py       wires widgets and services together
│       ├── widgets/             sidebar, tabs, request editor, URL field, code editor, key/value
│       │                        tables, auth/body editors, response viewer, home screen, toasts
│       └── dialogs/             create project, new request, collections, environment variables,
│                                settings, history, command palette, confirmations
├── tests/                       pytest suite (core logic and an end-to-end UI smoke test)
├── tools/mock_server.py         in-memory backend for trying the app
└── examples/backend-tienda/     sample api-client/ folder
```

Layering rules: `models` have no dependencies. `services` and `repositories` don't import Qt. Widgets never
read or write files; they emit signals that `MainWindow` turns into `ProjectService` calls.

App-wide data (recent projects, settings, history, window and tab state) lives in a SQLite database in your
user data folder: `~/.local/share/api-client/` on Linux, `%APPDATA%\api-client\` on Windows. It is never
stored inside a repository. Set `API_CLIENT_DATA_DIR` to use another location.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers variable resolution, URL building, query and path params, auth, JSON body handling, cURL
masking, collection read/write, corrupt files, secrets separation, real HTTP calls against a local server,
and an end-to-end flow through the main window: create a project, send a request, autosave, restart and
check that everything is restored.

## Building an executable

The code is ready for PyInstaller (resources are resolved through `sys._MEIPASS`):

```bash
pip install -r requirements-dev.txt
pyinstaller api_client.spec
# → dist/api-client/api-client   (Windows: dist\api-client\api-client.exe)
```

## Roadmap

The architecture already has extension points for:

- **Import endpoints from Spring Boot:** scan `@RestController`, `@RequestMapping`, `@GetMapping`,
  `@PostMapping`… and generate collections (`app/importers/base.py`, `CollectionImporter`).
- Postman import and collection export (`CollectionImporter` / `CollectionExporter`).
- OAuth2 and API-key auth (`app/services/auth_strategies.py`, `register_strategy`).
- Proxy and client certificates (`NetworkSettings`).

## Screenshots

| Home | Light theme |
|---|---|
| ![Home](docs/screenshot-home.png) | ![Light](docs/screenshot-light.png) |
