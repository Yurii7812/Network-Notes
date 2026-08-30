from pathlib import Path
import py_compile
import re
import unittest
import zipfile
import importlib.util
import io
import shutil
import tempfile
import os
import time
from datetime import datetime

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

    def test_mobile_note_list_can_be_opened_and_closes_after_selection(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn('id="mobileNodesBtn" class="mobileOnly" type="button" aria-controls="sidebar" aria-expanded="false"', src)
        self.assertIn("@media(max-width:700px){#mobileNodesBtn{display:inline-flex}body.mobileSidebarOpen #sidebar{display:block!important}", src)
        self.assertIn("$('mobileNodesBtn').onclick=()=>setMobileSidebar(!document.body.classList.contains('mobileSidebarOpen'))", src)
        self.assertIn("$('mobileOverlay').onclick=()=>setMobileSidebar(false)", src)
        self.assertIn("await refreshFiles();setMobileSidebar(false);queueTopicWidgets()", src)
        self.assertNotIn("$('mobileNodesBtn').onclick=()=>{}", src)

    def test_mobile_note_content_uses_the_full_viewport_width(self):
        src = APP.read_text(encoding="utf-8")
        mobile_rules = src.split("@media (max-width:700px){", 1)[1].split("/* v54 interaction cleanup */", 1)[0]
        self.assertIn("#layout{display:block!important;width:100%;", mobile_rules)
        self.assertIn("#editorPane{width:100%;max-width:100%;height:100%}", mobile_rules)
        self.assertIn("#organizeWrap,#organizeView{width:100%;max-width:100%}", mobile_rules)
        self.assertNotIn("grid-template-columns:minmax(0,1fr)", mobile_rules)

    def test_source_editor_uses_official_codemirror_vim_keymap(self):
        src = APP.read_text(encoding="utf-8")
        # Modal editing is the vendored official addon, not a hand-rolled layer.
        self.assertIn('<script src="/static/vim.js"></script>', src)
        self.assertIn('"vim.js": "application/javascript; charset=utf-8",', src)
        self.assertIn("keyMap:'vim',", src)
        # The hand-rolled key handler and its parallel mode state are gone.
        self.assertNotIn("function handleVimKey(", src)
        self.assertNotIn("let vimInputMode=", src)
        self.assertNotIn("function setVimInputMode(", src)
        self.assertNotIn("function vimVisualMotion(", src)
        self.assertNotIn("addEventListener('beforeinput'", src)
        for f in ("static/vim.js", "static/dialog.js", "static/searchcursor.js"):
            self.assertTrue((ROOT / f).is_file(), f)

    def test_ctrl_e_opens_source_in_insert_mode(self):
        src = APP.read_text(encoding="utf-8")
        # Entering Source drops into INSERT via the addon's own state machine.
        self.assertIn("const enterInsert=next==='source'&&opts.keepNormal!==true;", src)
        self.assertIn("function sourceEnterInsert(){", src)
        self.assertIn("CodeMirror.Vim.handleKey(editor,'i')", src)
        self.assertIn("if(enterInsert)sourceEnterInsert();", src)
        self.assertIn("try{await flushAutosave(true)}catch(_){}", src)

    def test_note_operations_are_leader_vim_commands(self):
        src = APP.read_text(encoding="utf-8")
        # Project note-ops hang off the `\` leader so vim's own n/m/e/y/d/c are
        # untouched. <Space> can't be the leader: the addon resolves its
        # built-in <Space> before any multi-key sequence starting with it.
        self.assertIn("function registerVimLeaderCommands(){", src)
        self.assertIn("Vim.mapCommand('\\\\'+key,'action',action,{},{context:'normal'})", src)
        self.assertIn("map('n','nnNewNode');", src)
        self.assertIn("Vim.defineAction(name,defs[name])", src)

    def test_cursor_follow_scroll_is_delegated_to_codemirror(self):
        src = APP.read_text(encoding="utf-8")
        # No custom multi-frame scroll loop; CodeMirror's scrollIntoView only.
        self.assertNotIn("function vimEnsureCursorVisible(", src)
        self.assertNotIn("vimScrollRaf", src)
        self.assertIn("cm.scrollIntoView(cm.getCursor(),80)", src)

    def test_ime_composition_tracking_has_a_dropped_compositionend_failsafe(self):
        src = APP.read_text(encoding="utf-8")
        # Chromium drops compositionend on blur / pane hide; a watchdog and a
        # blur handler clear the flag so autosave/marking never freeze.
        self.assertIn("function forceEndImeComposition(cm){", src)
        self.assertIn("const imeCompositionWatchdog=new WeakMap();", src)
        self.assertIn("input.addEventListener('compositionupdate',()=>bumpImeWatchdog(cm));", src)
        self.assertIn("input.addEventListener('blur',()=>{setTimeout(()=>forceEndImeComposition(cm),0)});", src)
        self.assertIn("if(next!=='source')setTimeout(()=>forceEndImeComposition(editor),0);", src)

    def test_local_mode_uses_an_implicit_offline_workspace(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn("if LOCAL_MODE:\n            return local_workspace_user(session_user)", src)
        self.assertIn("Localはログインなしで完全に使えます", src)
        self.assertIn("$('uploadToggleWrap').style.display='none'", src)

    def test_network_transfers_are_explicit_full_replacements(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn('ネットからダウンロード', src)
        self.assertIn('ネットへアップロード', src)
        self.assertIn('include_all=True', src)
        self.assertIn('"mode":"replace"', src)
        self.assertIn('previous |= set(user_files(uid))', src)
        self.assertIn('for name in user_files(uid):', src)
        self.assertIn('if media_folder.exists(): shutil.rmtree(media_folder)', src)
        self.assertIn("# Network transfer is always an explicit user action.", src)
        self.assertNotIn("NetworkNotes Local auto-upload:", src)

    def test_local_web_logout_forgets_only_connection_credentials(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn('id="disconnectWebBtn"', src)
        self.assertIn('if u.path == "/api/local-disconnect":', src)
        self.assertIn('cfg.update({"token":"","remote_username":"","remote_user_id":0,', src)

    def test_v86_distributions_are_built_from_the_current_offline_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            app_dir.mkdir()
            shutil.copy2(APP, app_dir / "app.py")
            shutil.copytree(ROOT / "static", app_dir / "static")
            spec = importlib.util.spec_from_file_location("networknotes_distribution_test", app_dir / "app.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.LOCAL_MODE = True
            module.init_db()
            handler = object.__new__(module.Handler)
            handler.cookie_token = lambda: None
            local_user = handler.current_user()
            self.assertEqual(local_user["username"], "local")
            self.assertTrue((Path(tmp) / "data" / "vault" / "local__Index.md").is_file())
            expected = APP.read_bytes()
            for platform in ("Linux", "macOS", "Windows", "Portable"):
                with self.subTest(platform=platform):
                    raw = module.build_local_distribution(platform)
                    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
                        root = "NetworkNotes-Local-v86/"
                        self.assertEqual(bundle.read(root + "app/app.py"), expected)
                        self.assertEqual(bundle.read(root + ".networknotes-local"), b"NetworkNotes Local package\n")
                        launcher = bundle.read(root + ("Start-NetworkNotes.bat" if platform == "Windows" else "Start-NetworkNotes.sh"))
                        self.assertIn(b"--local", launcher)
                        data_files = [name for name in bundle.namelist() if name.startswith(root + "data/") and name != root + "data/"]
                        self.assertEqual(data_files, [])

    def test_v86_archives_are_not_committed_binary_files(self):
        self.assertEqual(list((ROOT / "downloads").glob("NetworkNotes-Local-v86-*.zip")), [])
        src = APP.read_text(encoding="utf-8")
        self.assertIn("return self.file_response(build_local_distribution(platform),name", src)

    def test_packaged_app_is_local_even_when_launcher_is_bypassed(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn('LOCAL_PACKAGE_MARKER = ROOT_DIR / ".networknotes-local"', src)
        self.assertIn("LOCAL_MODE = bool(args.local or LOCAL_PACKAGE_MARKER.is_file())", src)
        self.assertIn("function isGuest(){return !runtimeLocalMode&&!profile?.id}", src)
        self.assertNotIn("if(profile?.local_mode)showAuth(e.message)", src)

    def test_timezone_aware_markdown_and_browser_display_contract(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn('datetime.now().astimezone().isoformat(timespec="seconds")', src)
        self.assertIn("function formatLocalDateTime(value)", src)
        self.assertIn("new Intl.DateTimeFormat(undefined", src)
        self.assertIn("formatLocalDateTime(p.created_at)", src)
        self.assertNotIn("Asia/Tokyo", src)
        self.assertNotIn("+09:00", src)

    def test_data_directory_remains_outside_repository(self):
        self.test_app_uses_sibling_data_directory()
        self.test_data_is_gitignored()


class MarkdownTimezoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        app_dir = Path(cls.tmp.name) / "app"
        app_dir.mkdir()
        shutil.copy2(APP, app_dir / "app.py")
        spec = importlib.util.spec_from_file_location("networknotes_timezone_test", app_dir / "app.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.module.ensure_vault()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.old_tz = os.environ.get("TZ")

    def tearDown(self):
        if self.old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self.old_tz
        if hasattr(time, "tzset"):
            time.tzset()

    def set_timezone(self, value):
        os.environ["TZ"] = value
        if hasattr(time, "tzset"):
            time.tzset()

    def test_new_yaml_timestamps_include_environment_offset(self):
        self.set_timezone("EST5EDT,M3.2.0,M11.1.0")
        text = self.module.new_note_markdown("alice__20260830120000.md", "Offset")
        created = self.module.yaml_created_value(text)
        self.assertRegex(created, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        self.assertEqual(datetime.fromisoformat(created).utcoffset(), datetime.now().astimezone().utcoffset())
        updated = re.search(r"(?im)^\s*updated\s*:\s*(.+?)\s*$", text)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.group(1), created)

    def test_created_is_preserved_and_updated_is_refreshed(self):
        name = "alice__20260830120001.md"
        original_created = "2026-08-31T02:22:53+09:00"
        stale_updated = "2026-08-31T02:30:00+09:00"
        content = f"---\ncreator::alice\ncreated: {original_created}\nupdated: {stale_updated}\n---\n\n# Note\n"
        self.set_timezone("EST5EDT,M3.2.0,M11.1.0")
        self.module.write_file(name, content)
        saved = self.module.read_file(name)
        self.assertEqual(self.module.yaml_created_value(saved), original_created)
        updated = re.search(r"(?im)^\s*updated\s*:\s*(.+?)\s*$", saved)
        self.assertIsNotNone(updated)
        self.assertNotEqual(updated.group(1), stale_updated)
        self.assertRegex(updated.group(1), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

    def test_different_offsets_compare_by_absolute_instant(self):
        earlier = "2026-08-31T02:22:53+09:00"
        later = "2026-08-30T14:30:00-04:00"
        same_as_earlier = "2026-08-30T17:22:53+00:00"
        self.assertLess(self.module.datetime_sort_key(earlier), self.module.datetime_sort_key(later))
        self.assertEqual(self.module.datetime_sort_key(earlier), self.module.datetime_sort_key(same_as_earlier))

    def test_legacy_datetime_remains_readable_and_unchanged(self):
        legacy = "2026-08-30 17:22:53"
        content = f"---\ncreated: {legacy}\n---\n\n# Legacy\n"
        self.assertEqual(self.module.yaml_created_value(content), legacy)
        self.assertIsNone(self.module.parse_note_datetime(legacy).tzinfo)
        normalized = self.module.ensure_created_frontmatter("legacy.md", content)
        self.assertIn(f"created: {legacy}", normalized)



if __name__ == "__main__":
    unittest.main()
