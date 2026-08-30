# NetworkNotes engineering instructions

## Repository / deployment layout

This repository is the **application directory only**.

Production layout:

- `/opt/network-notes-sns/app` — this Git repository and application code.
- `/opt/network-notes-sns/data` — persistent user data. It is NOT part of the repository.

Never move, delete, reset, overwrite, recreate, or commit persistent data as part of an application update.
The application must continue to derive its persistent directory as the sibling `data/` directory of the repo.

Persistent data includes at least:
- `network_notes.db`, `network_notes.db-wal`, `network_notes.db-shm`
- `vault/`
- `media/`
- `local_config.json`
- `backups/` and sync-conflict backups

## Critical product behavior

- Local mode requires no local account and must be usable completely offline immediately after startup.
- Request Web login/registration only when the user explicitly chooses Web sharing or Web synchronization.
- Local-only notes must not be uploaded implicitly.
- Unsynchronized Local edits must never be silently overwritten by Web synchronization.
- Sync conflicts must preserve both versions and must not silently discard content.
- `Ctrl+E` entering Source/Vim mode must start in NORMAL mode.
- Japanese IME composition must not be interrupted by autosave, rerender, relation synchronization, or mode changes.
- Saving must prevent stale/older saves from overwriting newer content.
- Avoid editor DOM replacement/rerender while the user is composing or actively editing unless explicitly required.
- Parent/child/relation synchronization must not rewrite user text unexpectedly.
- Existing public URLs and stored note formats should remain backward compatible unless a migration is explicitly requested.

## Change discipline

Before modifying behavior:
1. Identify the reproducer/root cause.
2. Add or update a regression test when practical.
3. Make the smallest coherent fix.
4. Run the test suite and Python syntax compilation.
5. Report tests run and any tests that could not be run.

Avoid large unrelated refactors in the same change as a bug fix.
If splitting the large `app.py`, do it incrementally and preserve behavior with tests first.

## Required checks

At minimum run:

```bash
python3 -m py_compile app.py
python3 -m unittest discover -s tests -v
```

For editor/input changes, also inspect/test:
- normal/insert transitions
- Ctrl+E
- Japanese IME composition events
- rapid consecutive saves
- switching views while a save is in flight

For sync changes, test:
- Web -> Local
- Local -> Web explicit sharing
- Web-only edit
- Local-only edit
- simultaneous conflicting edit
- local-only notes remaining local

## Security / secrets

Do not commit passwords, session cookies, sync tokens, private keys, production databases, user vault content, or production config.
Do not weaken authentication or authorization merely to make a test pass.
