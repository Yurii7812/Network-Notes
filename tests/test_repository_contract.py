from pathlib import Path
import py_compile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


class RepositoryContractTests(unittest.TestCase):
    def test_app_compiles(self):
        py_compile.compile(str(APP), doraise=True)

    def test_app_uses_sibling_data_directory(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn("APP_DIR = Path(__file__).resolve().parent", src)
        self.assertIn("ROOT_DIR = APP_DIR.parent", src)
        self.assertIn('DATA_DIR = ROOT_DIR / "data"', src)
        self.assertIn('DB_FILE = DATA_DIR / "network_notes.db"', src)
        self.assertIn('VAULT = DATA_DIR / "vault"', src)
        self.assertIn('MEDIA_DIR = DATA_DIR / "media"', src)
        self.assertIn('LOCAL_CONFIG_FILE = DATA_DIR / "local_config.json"', src)

    def test_data_is_gitignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for required in ("../data/", "*.db", "*.db-wal", "*.db-shm", "local_config.json", "backups/"):
            self.assertIn(required, ignore)

    def test_codex_instructions_exist(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Local mode requires no local account", text)
        self.assertIn("Ctrl+E", text)
        self.assertIn("Japanese IME", text)
        self.assertIn("Unsynchronized Local edits", text)

    def test_operation_status_is_visible_and_accessible(self):
        """Save/errors must not disappear into the intentionally compact header."""
        src = APP.read_text(encoding="utf-8")
        self.assertIn('id="status" role="status" aria-live="polite"', src)
        self.assertIn("#headerRight #status.visible", src)
        self.assertNotIn("#headerRight #status{display:none}", src)
        self.assertIn("kind==='error'?6000:2200", src)

    def test_save_errors_use_the_persistent_error_status(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn("status('保存エラー: '+(e?.message||''),{kind:'error'})", src)


if __name__ == "__main__":
    unittest.main()
