# Project Memory

## Current State

The project has been refactored from a single large `app.py` into a modular Flask structure.

`app.py` is now primarily responsible for:
- app factory creation via `create_app(config_overrides=None)`
- compatibility exports for legacy tests/imports
- wiring shared helpers/services into the app
- registering the main Blueprint

The app still preserves:
- `app = create_app()` for compatibility
- existing route paths
- many top-level helper names in `app.py` so older tests can still import/patch them

## Major Modules Added

- `nexfile/core.py`
  Contains stable utility helpers such as runtime path resolution, secure filenames, note input normalization, unique naming, dirty path parsing, and other pure helpers.

- `nexfile/services.py`
  Contains DB/settings/trash metadata services and file/trash item operations.

- `nexfile/update.py`
  Contains Git incremental update logic.

- `nexfile/onlyoffice.py`
  Contains ONLYOFFICE editor/callback route logic.

- `nexfile/onlyoffice_tokens.py`
  Contains ONLYOFFICE token/JWT helper logic.

- `nexfile/auth.py`
- `nexfile/admin.py`
- `nexfile/files.py`
- `nexfile/notes.py`
- `nexfile/share.py`
- `nexfile/trash.py`
- `nexfile/game.py`
- `nexfile/preview.py`

- `nexfile/blueprints_main.py`
  Contains the main Flask Blueprint (`main_bp`) and the thin routing layer.

## Blueprint Migration

Routes are now registered through the `main` Blueprint.

Important endpoint naming change:
- template/module `url_for(...)` calls were updated from bare names like `index`, `notes`, `view_note` to `main.index`, `main.notes`, `main.view_note`, etc.

Static asset endpoints remain standard Flask `static`.

## App Factory Status

`create_app(config_overrides=None)` now exists in `app.py`.

Current behavior:
- `app = create_app()` is still created at import time for compatibility
- `create_app({...})` can override:
  - `UPLOAD_FOLDER`
  - `NOTES_FOLDER`
  - `TRASH_FOLDER`
  - `DATABASE`
  - `TESTING`
- key wrappers like `get_db()` and file/trash path helpers now prefer the active app config when an app context exists
- they still fall back to module globals for compatibility

This means the factory path is partially normalized, but not all compatibility globals have been removed yet.

## Runtime / Security Changes Already Completed

- Runtime data defaults to `instance/`-style paths, with legacy path compatibility preserved.
- `.gitignore` was added for runtime data and cache artifacts.
- default weak admin password was removed
- initial admin password now comes from `INITIAL_ADMIN_PASSWORD` or a one-time generated password
- default debug mode is now off unless `FLASK_DEBUG=1`
- admin dashboard shows an initialization-password warning until the admin changes their own password

## Testing / Validation Reality

Static syntax validation was run multiple times using `ast.parse` and passed for the changed modules.

Important limitation:
- full runtime tests were not executed in this environment because required runtime packages like `flask`/`pytest` were not available here

## Test Migration Status

`test_security_and_trash.py` has started moving to factory-first setup.

Current test behavior:
- tests now create an isolated app instance with `app_module.create_app({...})`
- test client is built from that isolated app
- many `app_context()` usages were switched to `self.app.app_context()`
- some compatibility bookkeeping remains in test setup/teardown for `app_module.app` and a few top-level globals

Redundant setup code was already reduced once:
- repeated config backup/restore fields were removed
- repeated path reassignment in test setup was reduced

Remaining test cleanup work:
- reduce direct reliance on `app_module.DATABASE` / `UPLOAD_FOLDER` / `NOTES_FOLDER` / `TRASH_FOLDER`
- gradually stop patching/importing through `app.py` where module-level imports would be clearer

## Current Architectural Status

The project is no longer a true single-file app.

It is now roughly:
- `app.py`: entrypoint + compatibility layer + app factory
- `nexfile/*`: feature modules and service modules
- `main_bp`: thin route registration

## Recommended Next Steps

### High Priority

1. Continue app factory cleanup
   Move remaining helper behavior away from global module state and prefer app/config-driven access.

2. Improve tests around `create_app()`
   Add factory-based tests that create isolated test apps using `create_app({...})`.

3. Reduce compatibility layer in `app.py`
   Once tests are migrated, gradually remove redundant top-level wrapper exports.

### Medium Priority

1. Split `main_bp` into multiple Blueprints
   Suggested future blueprints:
   - `auth_bp`
   - `files_bp`
   - `notes_bp`
   - `admin_bp`
   - `share_bp`
   - `onlyoffice_bp`

2. Add formal config module
   Move configuration constants and defaults into `nexfile/config.py`.

3. Improve dependency injection
   Current `configure_main_blueprint(...)` dependency dictionary works, but is transitional.
   Future cleanup should move toward `create_app()` + `current_app`/extensions/service container patterns.

## Things To Be Careful About

- Existing tests patch top-level names in `app.py`; do not remove those casually yet.
- Template endpoint names now depend on `main.*`.
- `admin_required` redirects must continue targeting `main.login`.
- ONLYOFFICE helpers are intentionally still re-exported through `app.py` for compatibility.
- `create_app()` currently exists, and key wrappers now prefer active app config, but module-level compatibility globals still exist. Do not remove them until tests are further migrated.
