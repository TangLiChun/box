# Python File Analysis and Management System

A premium web application for managing files, with personal authentication, direct downloading, and file analysis capabilities. Built with Python (Flask) and dynamic HTML/CSS (Glassmorphism dark theme).

## Features

*   **Secure Authentication**: Personal login to protect your files (`/login`).
*   **File Management**: Upload, list, and delete files with ease. Runtime files are stored under `instance/` by default.
*   **Direct Link Downloads**: Download your files directly.
*   **File Analysis**: Get detailed insights into file sizes, MIME types, creation dates, and hex headers.
*   **Premium UI**: Stunning, modern, responsive glassmorphism dark theme. Micro-animations included!

## Setup Instructions

1.  Ensure you have Python 3.8+ installed.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the application:
    ```bash
    python app.py
    ```
4.  Access the web interface at `http://localhost:5000`.

## Container / Remote Access

The app now listens on `0.0.0.0` by default, so it can be reached from outside the container if the port is published.

Example:

```bash
pip install -r requirements.txt && python app.py
```

Optional environment variables:

```bash
HOST=0.0.0.0 PORT=5000 FLASK_DEBUG=1 SECRET_KEY=your-long-random-secret INITIAL_ADMIN_PASSWORD=choose-a-strong-password python app.py
```

> ⚠️ If `SECRET_KEY` is not fixed (for example, changes between restarts), existing login sessions/cookies will become invalid after restart.
>
> ⚠️ If `INITIAL_ADMIN_PASSWORD` is not provided on first start, the app will generate a one-time random admin password and print it to the server log.

## ONLYOFFICE Notes

- Configure the Document Server URL in the admin panel before using online editing.
- If your ONLYOFFICE deployment has JWT enabled, also fill in the `ONLYOFFICE JWT 密钥` field in the admin panel with the same shared secret.
- The app will then sign editor config requests and verify signed callback payloads with that secret.

## Incremental Upgrade

- The admin panel now includes `检查更新` and `执行升级` buttons for Git-based deployments.
- The upgrade flow runs a guarded `git pull --ff-only` and then installs dependencies from `requirements.txt`.
- If the deployment directory is not a Git repository, or the worktree has uncommitted local changes, the upgrade action will stay disabled.

## Initial Admin Account

*   **Username**: `admin`
*   **Password**: Set via `INITIAL_ADMIN_PASSWORD` on first start, or read the one-time generated password from the server log.

## Runtime Data

Runtime data is stored under `instance/` by default:

*   `instance/users.db`
*   `instance/uploads/`
*   `instance/notes/`
*   `instance/trash/`

If you already have legacy runtime data in the project root, the app keeps using it so existing deployments continue to work without a forced migration.

## Author
Built enthusiastically for a futuristic web experience.
