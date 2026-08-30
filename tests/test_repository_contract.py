from pathlib import Path
import py_compile
import unittest
import zipfile
import importlib.util
import io
import shutil
import tempfile

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
        self.assertIn("#layout{grid-template-columns:minmax(0,1fr);", mobile_rules)

    def test_ctrl_e_opens_source_in_insert_mode(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn("next==='source'?{enterInsert:true,...opts}:opts", src)
        self.assertIn("if(enterInsert){", src)
        self.assertIn("vimInputMode='insert';vimPendingCommand=''", src)
        self.assertNotIn("toggleViewMode({forceNormal:true})", src)

    def test_normal_tab_link_navigation_keeps_cursor_visible(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn("if(key==='Tab'){vimPendingCommand='';vimJumpLink", src)
        self.assertNotIn("In INSERT, Tab follows", src)
        self.assertIn("if(e.key==='Tab'&&tableCellMove", src)
        self.assertIn("cm.scrollTo(null,target)", src)
        self.assertIn("ensure();\n  // Collapsed link marks", src)
        self.assertIn("vimScrollRaf=requestAnimationFrame(ensure)", src)

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



if __name__ == "__main__":
    unittest.main()
