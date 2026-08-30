# NetworkNotes

NetworkNotes is a local-first Markdown/network SNS application.

## Directory model

The Git repository is the application directory:

```text
/opt/network-notes-sns/
├── app/                  # this Git repository
│   ├── app.py
│   ├── static/
│   ├── downloads/
│   ├── tests/
│   └── tools/
└── data/                 # persistent data; never committed
    ├── network_notes.db
    ├── vault/
    ├── media/
    ├── local_config.json
    └── backups/
```

`app.py` resolves `data/` as the sibling directory of `app/`, so updating the Git repository does not replace user data.

## Run

Web/server mode:

```bash
python3 app.py --host 127.0.0.1 --port 8765
```

Local/offline mode:

```bash
python3 app.py --local --host 127.0.0.1 --port 8765
```

## Tests

```bash
python3 -m py_compile app.py
python3 -m unittest discover -s tests -v
```

## Codex

Read `AGENTS.md` before making changes. The file contains architectural invariants, editor/IME requirements, sync safety rules, and mandatory checks.

## Raspberry Pi updates from Git

Once the repository is cloned at `/opt/network-notes-sns/app`, updates can be applied with the included `tools/updateFromGit` helper. It performs a fast-forward-only pull, compiles `app.py`, restarts `network-notes.service`, and rolls back the application commit if validation/restart fails.

The sibling `/opt/network-notes-sns/data` directory is not touched by Git operations.
