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
- default runtime path config is now centralized through a helper that builds the default app config before overrides are applied
- compatibility path globals are now synchronized from `app.config` instead of being assigned piecemeal inside `create_app()`
- key wrappers like `get_db()` and file/trash path helpers now prefer the active app config when an app context exists
- they still fall back to module globals for compatibility
- `init_db(target_app=None)` now accepts an explicit app, and `create_app()` initializes the DB via `init_db(app)` instead of relying only on the module-global app

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
- direct test dependence on `app_module.DATABASE` / `UPLOAD_FOLDER` / `NOTES_FOLDER` / `TRASH_FOLDER` and `app_module.g` was removed
- the redundant `app_module.app = self.app` assignment in test setup was removed because `create_app()` already updates the compatibility app reference
- some compatibility bookkeeping still remains in teardown for restoring `app_module.app`

Redundant setup code was already reduced once:
- repeated config backup/restore fields were removed
- repeated path reassignment in test setup was reduced
- repeated direct DB access in tests was partially normalized behind a local helper

Remaining test cleanup work:
- gradually stop patching/importing through `app.py` where module-level imports would be clearer
- decide how much longer `app_module.app` restoration should remain in test teardown versus moving tests to purely instance-local access

## Current Architectural Status

The project is no longer a true single-file app.

It is now roughly:
- `app.py`: entrypoint + compatibility layer + app factory
- `nexfile/*`: feature modules and service modules
- `main_bp`: thin route registration

## Git / Repo Status

- the local directory is now initialized as a Git repository
- GitHub remote is configured for `git@github.com:TangLiChun/box.git`
- SSH auth was set up using `~/.ssh/id_ed25519_github` with an entry in `~/.ssh/config`
- local work was merged with the existing remote `main` history using a merge commit
- current remote-tracking `main` includes the pushed merge commit `deac619`
- `.gitignore` now excludes `users.db` so runtime DB state is not committed by default

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

4. Split the large security/integration test file
   `test_security_and_trash.py` is still carrying multiple concerns and would benefit from a shared factory-first base plus smaller focused test modules.

## Things To Be Careful About

- Existing tests patch top-level names in `app.py`; do not remove those casually yet.
- Template endpoint names now depend on `main.*`.
- `admin_required` redirects must continue targeting `main.login`.
- ONLYOFFICE helpers are intentionally still re-exported through `app.py` for compatibility.
- `create_app()` currently exists, and key wrappers now prefer active app config, but module-level compatibility globals still exist. Do not remove them until tests are further migrated.
- The remote GitHub repo already had prior history and branches; future pushes should be normal now that this local repo tracks `origin/main`.
