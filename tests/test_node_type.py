"""node_type (YAML frontmatter) and Child-creation contract.

node_type describes what a note *is*; a Parent/Child relation label describes how
it *connects*. The two are stored and processed independently.
"""
from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


def load_app(tmp: str):
    app_dir = Path(tmp) / "app"
    app_dir.mkdir()
    shutil.copy2(APP, app_dir / "app.py")
    spec = importlib.util.spec_from_file_location("networknotes_node_type_test", app_dir / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ensure_vault()
    return module


class NodeTypeFrontmatterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.m = load_app(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # --- reading -----------------------------------------------------------
    def test_absent_node_type_reads_as_unspecified(self):
        legacy = "---\ncreator::alice\ncreated: 2026-01-01T00:00:00+09:00\nupdated: 2026-01-01T00:00:00+09:00\n---\n\n# Old note\n"
        self.assertEqual(self.m.node_type_of(legacy), "")

    def test_known_node_type_round_trips(self):
        for nt in ("論点", "見解", "支持", "反対", "補足", "まとめ", "カテゴリー"):
            text = f"---\ncreator::alice\ncreated: x\nupdated: x\nnode_type: {nt}\n---\n\n# T\n"
            self.assertEqual(self.m.node_type_of(text), nt)

    def test_unknown_node_type_is_dropped_not_rejected(self):
        text = "---\ncreator::alice\ncreated: x\nupdated: x\nnode_type: 宇宙\n---\n\n# T\n"
        self.assertEqual(self.m.node_type_of(text), "")

    # --- writing ---------------------------------------------------------
    def test_new_note_markdown_embeds_node_type_and_keeps_core_metadata(self):
        text = self.m.new_note_markdown("alice__20260101000000.md", "見解ノート", "見解")
        self.assertIn("node_type: 見解", text)
        self.assertIn("creator::alice", text)
        self.assertRegex(text, r"(?m)^created: .+$")
        self.assertRegex(text, r"(?m)^updated: .+$")
        self.assertEqual(self.m.node_type_of(text), "見解")

    def test_new_note_markdown_omits_line_when_unspecified(self):
        for value in ("", "指定なし", "宇宙"):
            text = self.m.new_note_markdown("alice__20260101000000.md", "T", value)
            self.assertNotIn("node_type", text)

    def test_set_node_type_add_replace_remove_preserves_core_metadata(self):
        base = "---\ncreator::alice\ncreated: C\nupdated: U\n---\n\n# T\n\nbody\n"
        added = self.m.set_node_type_frontmatter(base, "見解")
        self.assertEqual(self.m.node_type_of(added), "見解")
        replaced = self.m.set_node_type_frontmatter(added, "論点")
        self.assertEqual(self.m.node_type_of(replaced), "論点")
        removed = self.m.set_node_type_frontmatter(replaced, "指定なし")
        self.assertEqual(self.m.node_type_of(removed), "")
        for out in (added, replaced, removed):
            self.assertIn("creator::alice", out)
            self.assertIn("created: C", out)
            self.assertIn("updated: U", out)
            self.assertIn("body", out)
            self.assertIn("# T", out)

    def test_write_file_preserves_node_type_through_metadata_pipeline(self):
        name = "alice__20260101010101.md"
        content = self.m.new_note_markdown(name, "見解ノート", "見解")
        self.m.write_file(name, content)
        saved = self.m.read_file(name)
        self.assertEqual(self.m.node_type_of(saved), "見解")
        self.assertIn("creator::alice", saved)

    # --- independence from relation labels -------------------------------
    def test_node_type_is_independent_from_parent_relation(self):
        # Own kind = 見解, but the edge up to A is a カテゴリー relation.
        text = self.m.add_link_to_relation_side(
            self.m.new_note_markdown("alice__20260101020202.md", "案", "見解"),
            "カテゴリー", "グラフ機能", "alice__A.md", "parent",
        )
        self.assertEqual(self.m.node_type_of(text), "見解")
        edges = self.m.parse_outgoing(text)
        self.assertEqual([(r, t) for r, _l, t in edges], [("カテゴリー", "alice__A.md")])

    def test_free_form_relation_with_node_type(self):
        text = self.m.add_link_to_relation_side(
            self.m.new_note_markdown("alice__20260101030303.md", "案", "論点"),
            "分割", "元ノート", "alice__A.md", "parent",
        )
        self.assertEqual(self.m.node_type_of(text), "論点")
        self.assertIn("分割::[元ノート](alice__A.md)", text)

    # --- relation relabel -------------------------------------------------
    def test_relabel_exact_edge_changes_only_the_matching_edge(self):
        text = self.m.new_note_markdown("alice__20260101040404.md", "案", "見解")
        text = self.m.add_link_to_relation_side(text, "関連", "A", "alice__A.md", "parent")
        text = self.m.add_link_to_relation_side(text, "関連", "B", "alice__B.md", "parent")
        out = self.m.relabel_exact_edge(text, "関連", "alice__A.md", "支持")
        edges = {(r, t) for r, _l, t in self.m.parse_outgoing(out)}
        self.assertIn(("支持", "alice__A.md"), edges)
        self.assertIn(("関連", "alice__B.md"), edges)
        # node_type is untouched by an edge relabel
        self.assertEqual(self.m.node_type_of(out), "見解")

    def test_relabel_exact_edge_no_match_returns_input(self):
        text = self.m.add_link_to_relation_side(
            self.m.new_note_markdown("alice__20260101050505.md", "案", ""),
            "関連", "A", "alice__A.md", "parent",
        )
        self.assertEqual(self.m.relabel_exact_edge(text, "分割", "alice__A.md", "支持"), text)


class NodeTypeSpaContractTests(unittest.TestCase):
    def test_spa_exposes_node_type_selector_and_relation_list(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn('id="newNodeType"', src)
        self.assertIn("const NEW_NOTE_RELATIONS=", src)
        self.assertIn('"node_type": node_type_of(content)', src)
        self.assertIn("new_note_markdown(filename, title, node_type)", src)
        # unspecified node_type reads as "ノード", never inferred from relations
        self.assertIn("function nodeTypeLabel(v){return String(v||'')||'ノード'}", src)
        # keyboard-first edge editing endpoints
        self.assertIn('u.path == "/api/edge-relabel"', src)
        self.assertIn('u.path == "/api/node-type"', src)
        self.assertIn("function relabelSelectedEdges(direction,relation)", src)


if __name__ == "__main__":
    unittest.main()
