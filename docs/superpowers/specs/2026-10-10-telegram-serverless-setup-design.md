# Telegram Serverless Bot (Homatask_bot) Setup & Deployment Specification

## 1. Goal
Scaffold the `Homatask_bot` Telegram Serverless project inside `Homatask_bot/`, authenticate with the provided CLI token (`app8872536870:...`), configure security (.gitignore), verify local execution with dry-run tests, and push the initial deployment directly to Telegram's Serverless cloud infrastructure.

## 2. Background & Architecture
Telegram Serverless provides a native V8 isolate execution environment on Telegram's infrastructure for bots and Mini Apps.
Key components:
- `tgcloud/handlers/`: Update handlers (e.g., `message.js`).
- `tgcloud/lib/`: Shared helper functions and business logic.
- `tgcloud/schema.js`: SQLite table definitions via `sdk/db`.
- `tgcloud.jsonc`: Serverless project configuration.
- `.tgcloud/`: Local CLI state and authentication token (strictly git-ignored).

## 3. Directory Layout
```
homa-task/
├── Homatask_bot/
│   ├── tgcloud/
│   │   ├── handlers/
│   │   │   └── message.js
│   │   ├── lib/
│   │   └── schema.js
│   ├── docs/
│   │   └── tgcloud-sdk.md
│   ├── .tgcloud/          # git-ignored credentials
│   ├── AGENTS.md
│   ├── package.json
│   └── tgcloud.jsonc
└── .gitignore             # updated to ignore Homatask_bot/.tgcloud/
```

## 4. Execution Steps
1. **Scaffold Project**:
   Run `npm create @tgcloud/bot Homatask_bot` in the root workspace.
2. **Security & Gitignore**:
   Ensure `.tgcloud/` is excluded from git in both root `.gitignore` and `Homatask_bot/.gitignore`.
3. **Authentication**:
   Configure Telegram Serverless CLI credentials using `npx tgcloud login` or setting `.tgcloud/credentials.json` with the token `app8872536870:-ewz9sGL9UPiuaJT1U6AkZ5E6-pqGhyDgFlxwbIEDz8`.
4. **Local Verification**:
   Execute `npx tgcloud status` and dry-run `handlers/message` with a test payload.
5. **Deployment (`push`)**:
   Deploy the live code to Telegram Serverless cloud using `npx tgcloud push`.
6. **Final Status Check**:
   Confirm synchronization and live status via `npx tgcloud status`.

## 5. Security & Safety Constraints
- Never commit the CLI token or `.tgcloud/` contents.
- Strict ban on hardcoded local network URLs (complying with Rule Pillar 4).
