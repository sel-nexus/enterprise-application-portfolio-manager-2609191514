# Enterprise Application Portfolio Manager

The application manages portfolios, applications, reviews, dependencies, reports and administration.

## Local setup

Run MongoDB locally or supply an authenticated MongoDB deployment. Copy `backend/.env.example` to `backend/.env`. Generate a unique high-entropy `JWT_SECRET` (for example with `python -c "import secrets; print(secrets.token_urlsafe(48))"`), and set `BOOTSTRAP_EMAIL`, `BOOTSTRAP_NAME` and a unique `BOOTSTRAP_PASSWORD` of 12–72 bytes. The example values are deliberately rejected. Deliver the temporary password out of band. On first login it must be replaced. Bootstrap inserts only if that email does not exist; changing environment variables later does not reset the account. Remove bootstrap variables after provisioning.

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

In a second terminal, `cd frontend && npm install && npm run dev`. The Vite proxy forwards `/api` to port 8000. Or run `docker compose up --build` from the root after configuring `backend/.env` and open `http://localhost:8080`. Compose's MongoDB is for local development only; production requires authenticated MongoDB and HTTPS termination at a trusted reverse proxy. Never expose the development MongoDB to an untrusted network.

The fictional estate is seeded idempotently at startup by default; set `SEED_ON_STARTUP=false` for a real deployment. Role defaults and the review interval are always initialized without overwriting edits. Fictional people have unusable password hashes and cannot sign in; only the environment-provisioned bootstrap administrator or users created with an administrator-supplied temporary password can authenticate. Deliver temporary credentials out of band. Seeding is intended for a fresh demonstration database; it does not overwrite existing records.

## Tests

The API tests use a uniquely named, disposable MongoDB database on `MONGODB_TEST_URI` (default `mongodb://127.0.0.1:27017`); they delete only that database. Run `cd backend && PYTHONPATH=. python -m pytest -q tests/test_accounts.py`. Component tests: `cd frontend && npm test`; build: `npm run build`. The Playwright spec requires running frontend, API and an isolated MongoDB with a fresh bootstrap account, plus `E2E_EMAIL`, `E2E_TEMP_PASSWORD`, and `E2E_NEW_PASSWORD` in its environment; run `node node_modules/@playwright/test/cli.js test` from frontend. It changes the account password and should not be used against real accounts.

Sessions expire after eight hours, are revocable on sign-out, and are rotated when a password changes. First-use tokens expire after 15 minutes and only permit password replacement. Role and portfolio helpers in `app/core/security.py` and `AccountService.authorize` are intended for subsequent feature routes; future routes must invoke them, including on exports. Stored role permissions only restrict the shipped role ceiling. Portfolio IDs are displayed until the portfolio slice supplies names. Multi-record audit writes are not transactional with account writes on standalone MongoDB. API and browser should be served over HTTPS in production.
