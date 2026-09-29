---
name: superset-local-runtime-testing
description: Set up an isolated Superset runtime and verify Explore dataset editor payloads and permissions.
---

# Local Superset editor runtime testing

## Runtime setup

- Use Python 3.11+; an existing editable venv may be at `~/venv311`.
- Use a dedicated temporary `SUPERSET_CONFIG_PATH`, with a non-production
  `SECRET_KEY`, an isolated SQLite `SQLALCHEMY_DATABASE_URI`, and
  `TALISMAN_ENABLED = False` for localhost HTTP.
- For a local SQLite analytics source, set `PREVENT_UNSAFE_DB_CONNECTIONS = False`
  only in this isolated test config. Do not carry this override into production.
- Set `FLASK_APP=superset`; run `superset db upgrade`, `superset fab create-admin`,
  `superset init`, then `superset run -p 8088`.
- `CACHE_CONFIG` and `DATA_CACHE_CONFIG` can use SimpleCache for isolated tests.
- Initialize `create_app()` before importing model modules in fixture scripts;
  importing them earlier can fail with "App not initialized yet".

## Frontend prerequisites

- Inspect `.nvmrc` and `package.json` engines. Source `~/.nvm/nvm.sh` or add the
  existing NVM Node bin directory to PATH. This checkout needs Node 24 and npm 11.
- Older npm can report lockfile inconsistencies that disappear with the required
  npm version. Try the declared version before altering the lockfile.
- `npm ci` requires both `registry.npmjs.org` and `cdn.sheetjs.com` for the
  lockfile's SheetJS tarball; inspect resolved hosts when diagnosing blocked
  downloads. GitHub tarball dependencies redirect to `codeload.github.com`,
  which needs its own allowlist entry.
- For manual testing with an existing browser, skip unrelated binary downloads:
  `CYPRESS_INSTALL_BINARY=0 PUPPETEER_SKIP_DOWNLOAD=true PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm ci`.
- Frontend assets are not guaranteed to exist in `superset/static/assets`.
  Do not substitute another release's assets when validating the current branch.
- Use `npm run dev-server` (port 9000, backend proxy to 8088). Await compilation
  before opening browser tests.

## Editor fixtures and assertions

- Create two Alpha users: one dataset editor, one non-editor. Alpha supplies data
  access without Admin's unconditional edit-menu bypass.
- Dataset editors are **Subject IDs**, not User IDs. Obtain the user Subject via
  `superset.subjects.utils.get_or_create_user_subject`.
- Assign editors via Admin PUT `/api/v1/dataset/<id>` with `{"editors":[subject_id]}`.
- Explore endpoint:
  `/api/v1/explore/?datasource_id=<id>&datasource_type=table`.
  Assert `result.dataset.editors` matches dataset-detail `result.editors`, including
  numeric `id` and `type`, and string `label`.
- UI route: `/explore/?datasource_type=table&datasource_id=<id>`; left dataset
  ellipsis -> Edit dataset. Check enabled/openable for editor and disabled for
  non-editor.
- As Admin, save without edits and inspect the actual PUT and subsequent GET.
  A successful API-only roundtrip does not prove the UI Save or menu behavior.
- For shell API tests, use documented JWT login and CSRF acquisition in a separate
  requests session; never extract browser session cookies.

## Devin Secrets Needed

None for an isolated local instance with disposable test accounts. Existing
deployment credentials must be obtained through the normal secret mechanism.
