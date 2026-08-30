#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import os
import hashlib
import hmac
import json
import mimetypes
import re
import secrets
import shutil
import shlex
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
import zipfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
VAULT = DATA_DIR / "vault"
INDEX_FILE = "Index.md"
RATING_FILE = VAULT / ".topic_ratings.json"
PROFILE_FILE = VAULT / ".profile.json"  # legacy single-user profile
DIRECTION_MIGRATION_MARKER = VAULT / ".direction_v41_migrated"
DB_FILE = DATA_DIR / "network_notes.db"
MEDIA_DIR = DATA_DIR / "media"
AVATAR_DIR = MEDIA_DIR / "avatars"
DOWNLOADS_DIR = APP_DIR / "downloads"
LOCAL_CONFIG_FILE = DATA_DIR / "local_config.json"
LOCAL_PACKAGE_MARKER = ROOT_DIR / ".networknotes-local"
LOCAL_MODE = False
LOCAL_RELEASE_VERSION = 86
LOCAL_RELEASE_PLATFORMS = ("Windows", "macOS", "Linux", "Portable")
PUBLIC_SERVER_DEFAULT = "https://network-notes.duckdns.org"
REPORT_HIDE_THRESHOLD = 5
MAX_NOTES_PER_USER = 1000
MAX_NOTE_BYTES = 100 * 1024
MAX_NOTE_STORAGE_BYTES = 5 * 1024 * 1024
MAX_MEDIA_STORAGE_BYTES = 100 * 1024 * 1024
MAX_RELATIONS_PER_USER = 5000
MAX_NOTE_CREATES_PER_MINUTE = 10
MAX_NOTE_CREATES_PER_DAY = 100
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 300 * 1024
SESSION_COOKIE = "network_notes_session"
EDGE_START = "<!-- edges:auto:start -->"
EDGE_END = "<!-- edges:auto:end -->"
EDGE_BLOCK_RE = re.compile(
    rf"\n?{re.escape(EDGE_START)}.*?{re.escape(EDGE_END)}\n?",
    re.DOTALL,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_LABEL_FIXED = "label-fixed"
LINK_LINE_RE = re.compile(r'^\s*(?:[-*+]\s+)?\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+"(label-fixed)")?\)\s*$')
RELATION_LINK_LINE_RE = re.compile(r'^\s*([^:\n][^:\n]{0,79}?)::\s*\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+"(label-fixed)")?\)\s*$')
MARKDOWN_LINK_RE = re.compile(r'\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+"(label-fixed)")?\)')
DIRECTION_DIVIDER_RE = re.compile(r'^\s*---\s*$')

HTML = r'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Network Notes</title>
<link rel="stylesheet" href="/static/codemirror.css" />
<style>
:root{
  color-scheme:light;
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --border:#d9d9d9;
  --soft:#f3f3f3;
  --muted:#666666;
  --accent:#000000;
  --link:#2589d8;
}
*{box-sizing:border-box}
body{margin:0;height:100vh;overflow:hidden;background:#fff;color:#000}
header{height:48px;display:flex;align-items:center;gap:4px;padding:6px 8px;border-bottom:1px solid var(--border);background:#fff;min-width:0;position:relative;z-index:3000;overflow:visible}
#trailBar{display:none!important}
#trailLabel{font-size:11px;font-weight:750;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);flex:0 0 auto}
#trail{display:flex;align-items:center;gap:5px;min-width:0;overflow-x:auto;scrollbar-width:thin;white-space:nowrap;flex:1}
#trailReset{flex:0 0 auto;padding:4px 8px;font-size:11px}
.trailItem{border:0;background:transparent;padding:4px 6px;border-radius:6px;color:inherit;cursor:pointer;font-size:12px;max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.trailItem:hover{background:var(--soft)}.trailItem.current{font-weight:750;background:#e5e5e5}.trailArrow{font-size:11px;color:var(--muted);flex:0 0 auto}
header strong{margin-right:6px;font-size:13px;white-space:nowrap;flex:0 0 auto}
.profileBtn{padding:5px 8px;border:0;background:transparent;font-size:12px;font-weight:700;border-radius:6px}.profileBtn:hover{background:#e5e5e5}
button,input,select{font:inherit}
button{padding:7px 11px;border-radius:8px;border:1px solid #cfcfcf;background:#fff;color:#000;cursor:pointer;white-space:nowrap}
button:hover{background:#f3f3f3}
#layout{display:grid;grid-template-columns:minmax(520px,1fr) 360px;height:calc(100vh - 48px);position:relative;z-index:1}
#sidebar{display:none!important;border-right:1px solid var(--border);overflow:auto;padding:10px;background:#fff}
.sidebarHead{display:flex;align-items:center;gap:5px;margin:4px 0 8px;flex-wrap:wrap}.sidebarHead .group{margin:0;flex:1}.nodeSort{width:auto;max-width:104px;padding:4px 6px;border:1px solid var(--border);border-radius:7px;background:#fff;color:#000;font-size:10px}.sidebarAction{padding:4px 7px;font-size:10px}.sidebarAction.danger{border-color:#b91c1c}.sidebarAction.danger:disabled{opacity:.38;cursor:default}.fileSelectRow{display:flex;align-items:center;gap:6px;margin:2px 0}.fileSelectRow .file{margin:0;flex:1;min-width:0}.fileSelectCheck{width:16px;height:16px;accent-color:#000;flex:0 0 auto}.fileSelectCheck:disabled{opacity:.25}
#graphPane{border-left:1px solid var(--border);display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden;background:#fff;position:relative;z-index:1}
#graphControls{padding:10px 12px;border-bottom:1px solid var(--border);display:grid;gap:8px;position:relative;z-index:2}
#graphControls.collapsed .graphControl{display:none}
#graphControls.collapsed{padding-bottom:8px}
.graphControlsToggle{padding:4px 7px;font-size:10px;line-height:1.1}
.graphTitleRow{display:flex;align-items:center;gap:8px}.graphTitleRow strong{margin-right:auto;font-size:13px}
.graphControl{display:grid;grid-template-columns:76px 1fr 34px;gap:7px;align-items:center;font-size:11px;color:var(--muted)}
.graphControl input[type=range]{width:100%;height:18px;padding:0;accent-color:#000;background:transparent;cursor:pointer}
.graphControl input[type=range]::-webkit-slider-runnable-track{background:#cfcfcf;height:7px;border-radius:999px}.graphControl input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:17px;height:17px;margin-top:-5px;background:#000;border:2px solid #000;border-radius:50%}.graphControl input[type=range]::-moz-range-track{background:#cfcfcf;height:7px;border-radius:999px}.graphControl input[type=range]::-moz-range-progress{background:#000;height:7px;border-radius:999px}.graphControl input[type=range]::-moz-range-thumb{width:17px;height:17px;background:#000;border:2px solid #000;border-radius:50%}.graphValue{text-align:right;color:CanvasText;font-variant-numeric:tabular-nums}
#graphWrap{flex:1;min-height:0;position:relative;background:#fff}
#localGraph{display:block;width:100%;height:100%;min-height:240px;touch-action:none;user-select:none}.graphEdge{stroke:#a3a3a3;stroke-width:1.4;opacity:.82}.graphEdge.primary{stroke:#737373;stroke-width:2.25;opacity:1}.graphNode{cursor:pointer}.graphNode circle{fill:#000;stroke:#000;stroke-width:1.2}.graphNode.support circle{fill:#16a34a;stroke:#16a34a}.graphNode.oppose circle{fill:#dc2626;stroke:#dc2626}.graphNode.question circle{fill:#2563eb;stroke:#2563eb}.graphNode.answer circle{fill:#2563eb;stroke:#2563eb}.graphNode.derive circle{fill:#d97706;stroke:#d97706}.graphNode.related circle{fill:#737373;stroke:#737373}.graphNode.topic circle{fill:#7c3aed;stroke:#7c3aed}.graphNode.note circle{fill:#111827;stroke:#111827}.graphNode.summary circle{fill:#0891b2;stroke:#0891b2}.graphNode.current circle{fill:#000;stroke:#000;stroke-width:2.5}.graphNode text{fill:#000;pointer-events:none}.graphEdgeLabel{fill:#333;pointer-events:none;font-weight:700;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}.graphHint{position:absolute;left:10px;bottom:8px;font-size:10px;color:var(--muted);pointer-events:none}
#editorPane{display:flex;flex-direction:column;min-width:0;min-height:0;background:#fff}
#docBar{display:flex;align-items:center;gap:4px;padding:0;min-width:0;flex:1 1 560px;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;white-space:nowrap}#docBar::-webkit-scrollbar{display:none}#docBar button{padding:5px 7px;font-size:10.5px;line-height:1.1;flex:0 0 auto;white-space:nowrap}
#fileTitle{display:none!important}
.modeBtn.active{font-weight:700;border-color:#8f8f8f;background:#e5e5e5}
.topicRating{display:flex;align-items:center;gap:6px;margin-right:6px}
.topicRating .topicUse{font-size:12px;color:var(--muted);margin-right:2px}
.topicVote{padding:5px 8px;font-size:12px}
.topicVote.active{font-weight:750;border-color:#8f8f8f;background:#e5e5e5}
.topicEdgeRating{display:flex;align-items:center;gap:6px;padding:2px 0 7px 1.2em;font-size:12px;color:var(--muted)}
.topicEdgeRating button{padding:3px 7px;font-size:11px}
.topicEdgeRating .useCount{margin-right:2px}
#editWrap,#sourceWrap,#organizeWrap{flex:1;min-height:0;overflow:hidden}
#editWrap,#sourceWrap{display:none}
#organizeWrap{display:block;overflow:auto}
#organizeView{max-width:900px;margin:0 auto;padding:34px 52px 110px}
#editStructured{max-width:900px;margin:0 auto;padding:34px 52px 110px}
#editParentEdges,#editChildEdges{min-width:0}
#editBodyShell{margin:2px 0 8px}
#editBodyLabel{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:750;margin:4px 0 2px}
#bodySource,#source{display:none}
#bodyEditorWrap{overflow:visible!important}
#bodyEditorWrap .CodeMirror{height:auto!important;min-height:0!important;overflow:visible!important}
#bodyEditorWrap .CodeMirror-scroll{height:auto!important;min-height:0!important;max-height:none!important;overflow:visible!important;padding:10px 0 24px}
#bodyEditorWrap .CodeMirror-sizer{min-height:0!important;min-width:0!important;border-right:0!important}
#bodyEditorWrap .CodeMirror-vscrollbar,#bodyEditorWrap .CodeMirror-hscrollbar,#bodyEditorWrap .CodeMirror-scrollbar-filler,#bodyEditorWrap .CodeMirror-gutter-filler{display:none!important;width:0!important;height:0!important}
#bodyEditorWrap .CodeMirror-lines{max-width:none;margin:0;padding:0}
#sourceWrap .CodeMirror{height:100%}
#sourceWrap .CodeMirror-scroll{padding:28px 42px 100px}
#sourceWrap .CodeMirror-lines{max-width:900px;margin:0 auto;padding:0}
.CodeMirror{height:100%;background:#fff;color:#000;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:16px;line-height:1.72}
.CodeMirror-scroll{padding:28px 42px 100px}
.CodeMirror-lines{max-width:900px;margin:0 auto;padding:0}
.CodeMirror-cursor{border-left:2px solid #000!important}
.CodeMirror-selected{background:#d9d9d9!important}
.CodeMirror-activeline-background{background:transparent!important}
.cm-header{font-weight:750;color:CanvasText!important}
.cm-header-1{font-size:1.75em;line-height:1.25}
.cm-header-2{font-size:1.38em;line-height:1.35}
.cm-header-3{font-size:1.18em;line-height:1.4}
/* The leading Network Notes metadata block uses --- delimiters. Markdown's
   Setext-heading parser can otherwise style the line immediately before the
   closing --- as a huge H2. Keep metadata visually plain in Source view. */
.nnFrontmatterLine .cm-header,.nnFrontmatterLine .cm-header-1,.nnFrontmatterLine .cm-header-2,.nnFrontmatterLine .cm-header-3,.nnFrontmatterLine .cm-header-4,.nnFrontmatterLine .cm-header-5,.nnFrontmatterLine .cm-header-6{font-size:inherit!important;line-height:inherit!important;font-weight:400!important}
.cm-formatting-header{color:var(--muted)!important;font-weight:500}
.cm-link{color:var(--link)!important}
.cm-live-link{color:var(--link)!important;text-decoration:none;cursor:pointer}
.cm-url{color:var(--muted)!important}
.cm-strong{font-weight:750}.cm-em{font-style:italic}.cm-comment,.cm-quote{color:var(--muted)!important}
.file{display:block;width:100%;text-align:left;margin:2px 0;white-space:normal;overflow:visible;text-overflow:clip;line-height:1.25;max-height:2.7em;overflow:hidden;word-break:break-word;padding:6px 8px}
.file.active{font-weight:700;background:#e5e5e5;border-color:#bdbdbd}
.group{margin:14px 0 6px;font-size:12px;font-weight:700;opacity:.65;text-transform:uppercase;letter-spacing:.04em}
.edge{display:block;width:100%;text-align:left;border:0;background:transparent;color:inherit;padding:6px 4px;cursor:pointer;border-radius:6px}
.edge:hover{background:var(--soft)}
.relation{font-size:12px;opacity:.65}.hint{font-size:12px;line-height:1.5;opacity:.68;margin-top:14px}
.previewSection{margin:.18em 0 .72em}.previewSection h1,.previewSection h2,.previewSection h3{margin:.46em 0 .2em}.previewSection h1{font-size:2em;border-bottom:1px solid var(--border);padding-bottom:.18em}.previewSection h2{font-size:1.55em;border-bottom:1px solid var(--border);padding-bottom:.14em}.previewSection h3{font-size:1.25em}.previewLine{line-height:1.68;margin:.24em 0}.previewLink{display:flex;gap:7px;align-items:center;padding:4px 6px;margin:1px 0;border-radius:6px;background:#fff;min-height:30px}.previewLink:hover{background:#f3f3f3}.previewLink a{flex:1;min-width:0;color:var(--link);text-decoration:none;white-space:normal;overflow:visible;text-overflow:clip;line-height:1.28;word-break:break-word}.keyboardSelected{background:#e5e5e5!important;outline:2px solid #000;outline-offset:2px;border-radius:4px}.keyboardSectionSelected>.sectionHead{background:#f1f1f1;outline:2px solid #000;outline-offset:3px;border-radius:5px}.metrics{font-size:10px;color:var(--muted);white-space:nowrap}.sectionHead{display:flex;align-items:center;gap:7px}.sectionHead .heading{flex:1}.sectionSort{width:auto;min-width:108px;padding:3px 5px;border-radius:6px;border:1px solid var(--border);background:Field;color:FieldText;font-size:10px;margin-bottom:0}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--soft);border-radius:4px;padding:.08em .3em}
.relationChoices{display:flex;flex-wrap:wrap;gap:7px;max-width:520px}.relationChoice{padding:7px 11px;border-radius:999px;background:#fff;color:#000}.relationChoice.selected{background:#e5e5e5;border-color:#8f8f8f;font-weight:700}.relationChoice.pageItem::after{content:' · このページ';font-size:10px;opacity:.55;font-weight:400}
dialog{border:1px solid color-mix(in srgb,CanvasText 25%,transparent);border-radius:12px;padding:18px;min-width:360px;background:Canvas;color:CanvasText}dialog form{display:grid;gap:12px}label{display:grid;gap:5px;font-size:13px}input,textarea{padding:8px 9px;border-radius:7px;border:1px solid color-mix(in srgb,CanvasText 24%,transparent);background:Field;color:FieldText}.profileBio{min-height:92px;resize:vertical;font:inherit}.profileHint{font-size:11px;color:var(--muted)}.actions{display:flex;justify-content:flex-end;gap:8px;margin-top:6px}#status{font-size:12px;opacity:.72;min-width:120px;text-align:right}

.authGate{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;background:#fff}.authGate.hidden{display:none}.authCard{width:min(420px,calc(100vw - 32px));border:1px solid var(--border);border-radius:14px;padding:28px;background:#fff}.authCard h1{margin:0 0 8px;font-size:26px}.authCard p{margin:0 0 22px;color:var(--muted);font-size:13px}.authActions{display:flex;gap:8px;margin-top:6px}.authActions button{flex:1}.authError{min-height:20px;margin-top:10px;color:#b91c1c;font-size:12px}
.topNav{display:flex;gap:2px;min-width:0;flex:0 1 auto;overflow-x:auto;scrollbar-width:none}.topNav::-webkit-scrollbar{display:none}.topNav button{border:0;padding:5px 7px;background:transparent;font-size:11px;line-height:1.15;white-space:nowrap;flex:0 0 auto}.topNav button:hover,.topNav button.active{background:#e5e5e5}.profileBtn{display:flex;align-items:center;gap:5px;padding:4px 6px;font-size:11px;flex:0 0 auto}.avatar{width:28px;height:28px;border-radius:50%;object-fit:cover;background:#000;color:#fff;display:inline-grid;place-items:center;font-size:12px;font-weight:750;flex:0 0 auto}.avatar.small{width:22px;height:22px;font-size:10px}.avatar.large{width:72px;height:72px;font-size:24px}.avatarPreview{display:flex;align-items:center;gap:12px}.avatarPreview input{max-width:240px}
#authorBar{display:flex;align-items:center;gap:9px;padding:8px 14px;border-bottom:1px solid var(--border);min-height:48px;background:#fff}.authorText{display:flex;flex-direction:column;min-width:0}.authorName{font-weight:700;font-size:13px}.authorHandle{font-size:11px;color:var(--muted)}.authorMeta{margin-left:auto;display:flex;align-items:center;gap:7px;font-size:11px;color:var(--muted)}
.previewAuthor{display:flex;align-items:center;gap:5px;min-width:100px;max-width:160px;font-size:11px;color:#444}.previewAuthorName{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.inlineImage{display:block;max-width:min(100%,720px);max-height:560px;object-fit:contain;margin:10px 0;border-radius:8px;border:1px solid var(--border)}
#socialView{display:none;height:calc(100vh - 52px);overflow:auto;background:#fff}.socialInner{max-width:980px;margin:0 auto;padding:28px 26px 100px}.socialHeader{display:flex;align-items:center;gap:10px;margin-bottom:20px}.socialHeader h2{margin:0 auto 0 0}.feedList{display:grid;gap:12px}.feedCard{border:1px solid var(--border);border-radius:12px;padding:16px;background:#fff}.feedCard:hover{border-color:#aaa}.feedAuthor{display:flex;align-items:center;gap:8px;margin-bottom:10px}.feedAuthorText{min-width:0}.feedAuthorName{font-size:12px;font-weight:700}.feedAuthorHandle,.feedTime{font-size:11px;color:var(--muted)}.feedTitle{font-size:18px;font-weight:750;margin:5px 0 8px;cursor:pointer}.feedExcerpt{font-size:13px;line-height:1.6;color:#333;margin-bottom:12px}.feedActions{display:flex;align-items:center;gap:8px}.feedActions button{font-size:11px;padding:5px 8px}.socialGrid{display:grid;grid-template-columns:280px 1fr;gap:18px}.panel{border:1px solid var(--border);border-radius:12px;background:#fff;overflow:hidden}.panelHead{padding:12px 14px;border-bottom:1px solid var(--border);font-weight:750}.panelBody{padding:12px}.listItem{display:block;width:100%;text-align:left;border:0;border-radius:7px;padding:9px;background:#fff}.listItem:hover,.listItem.active{background:#e5e5e5}.communityCard{border:1px solid var(--border);border-radius:12px;padding:15px;margin-bottom:10px}.communityCard h3{margin:0 0 6px}.communityMeta{font-size:11px;color:var(--muted);margin:6px 0 10px}.chatBox{height:360px;overflow:auto;border:1px solid var(--border);border-radius:9px;padding:10px;background:#fafafa}.chatMsg{display:flex;gap:8px;margin:9px 0}.chatBubble{background:#fff;border:1px solid var(--border);border-radius:9px;padding:7px 9px;max-width:75%}.chatName{font-size:10px;font-weight:700;margin-bottom:2px}.chatTime{font-size:9px;color:var(--muted);margin-top:3px}.chatComposer{display:flex;gap:7px;margin-top:8px}.chatComposer input{flex:1}.emptyState{padding:32px;text-align:center;color:var(--muted);font-size:13px}.editorContextMenu{position:fixed;z-index:1600;display:none;min-width:132px;padding:5px;background:#fff;border:1px solid var(--border);border-radius:9px;box-shadow:0 8px 24px rgba(0,0,0,.12)}.editorContextMenu.open{display:block}.editorContextMenu button{display:block;width:100%;text-align:left;border:0;padding:7px 9px}.linkifySelected{padding:8px 10px;border:1px solid var(--border);border-radius:8px;background:#f7f7f7;font-size:12px;max-width:440px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.linkifyTarget{min-height:220px;width:100%}

.edgeZone{margin:0 0 10px;padding:0;background:#fff}.edgeZone.incoming{margin-top:8px}.edgeZoneHeader{display:flex;align-items:center;justify-content:flex-end;gap:5px;min-height:26px;margin:0 0 2px;padding:0}.edgeZoneTitle{margin-right:auto;font-size:12px;font-weight:750;line-height:1.2}.edgeZoneHeader button{padding:3px 7px;font-size:10px;line-height:1.2;white-space:nowrap}.edgeDeleteBtn{border-color:#b91c1c}.edgeDeleteBtn:disabled{opacity:.4}.edgeEmpty{font-size:11px;color:var(--muted);padding:4px 2px}.edgeGroup{margin:3px 0 8px}.edgeGroup>.sectionHead{align-items:center}.edgeGroup .heading h2{font-size:1.2em;border-bottom:1px solid var(--border);margin:.28em 0 .12em;padding-bottom:.1em}.edgeSelect{width:17px;height:17px;flex:0 0 auto;margin:0 2px 0 0;accent-color:#000}.previewLink.edgeEditing{background:#fafafa}.previewLink.edgeNotEditable{opacity:.72}.organizeBody{padding:0 0 4px}.organizeBodyTitle{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:750;margin:3px 0 5px}.edgeDirectionGap{height:5px}\n.edgeDirectionDivider{border:0;border-top:2px solid #000;margin:30px 0 18px}.edgeDialogSearchRow{display:grid;grid-template-columns:1fr;gap:8px}.edgeTargetList{min-height:220px;width:100%}.edgePaste{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}.searchShell{display:grid;gap:12px}.searchBar{display:grid;grid-template-columns:minmax(220px,1fr) 130px minmax(160px,220px);gap:8px;align-items:center}.searchBar input,.searchBar select{width:100%}.searchSyntax{font-size:11px;color:var(--muted);line-height:1.55;border:1px solid var(--border);border-radius:9px;padding:9px 11px;background:#fafafa}.searchResults{display:grid;gap:8px}.searchResult{border:1px solid var(--border);border-radius:10px;padding:13px 14px;background:#fff;cursor:pointer}.searchResult:hover{background:#f7f7f7}.searchResultHead{display:flex;align-items:center;gap:8px}.searchResultTitle{font-weight:750;font-size:15px;color:var(--link)}.searchResultAuthor{font-size:11px;color:var(--muted)}.searchResultSnippet{font-size:12px;line-height:1.6;color:#333;margin-top:7px;white-space:pre-wrap}.searchResultMeta{font-size:10px;color:var(--muted);margin-top:7px}.searchCount{font-size:11px;color:var(--muted);margin-left:auto}.searchEmpty{padding:40px 10px;text-align:center;color:var(--muted);font-size:13px}.savedSearchBar{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.savedSearchBar select{min-width:180px}.savedSearchBar button{font-size:11px}.searchHelp{font-size:11px;color:var(--muted);line-height:1.55;border:1px solid var(--border);border-radius:9px;padding:9px 11px;background:#fafafa}.quotaInputs{display:grid;grid-template-columns:repeat(2,minmax(110px,1fr));gap:5px}.quotaInputs label{font-size:9px;color:var(--muted)}.quotaInputs input{width:100%;padding:4px 5px;font-size:10px}.syncConnected{padding:8px 10px;border:1px solid var(--border);border-radius:8px;background:#fafafa;font-size:12px}.syncConnected strong{font-weight:800}

.socialTabs{display:flex;gap:5px;overflow-x:auto;margin:12px 0 16px;scrollbar-width:none}.socialTabs button{font-size:12px;padding:6px 10px;flex:0 0 auto}.socialTabs button.active{background:#e5e5e5;font-weight:750}.expandBtn{margin-left:auto}.socialInner.fullscreen{position:fixed;inset:0;z-index:1400;max-width:none;background:#fff;padding:18px 22px 80px;overflow:auto}.profilePage{display:grid;gap:16px}.profileHero{display:flex;align-items:flex-start;gap:14px;border-bottom:1px solid var(--border);padding-bottom:16px}.profileHeroText{min-width:0;flex:1}.profileHeroName{font-size:22px;font-weight:800}.profileHeroHandle{color:var(--muted);font-size:12px}.profileHeroBio{margin-top:9px;white-space:pre-wrap;line-height:1.6}.profileActions{display:flex;gap:7px;flex-wrap:wrap}.dmContact{display:flex!important;align-items:center;gap:8px}.dmContactText{min-width:0;display:flex;flex-direction:column}.dmContactName{font-weight:700}.dmContactMeta{font-size:10px;color:var(--muted)}mark.searchHit{background:#fff3a3;color:#000;padding:0 .08em;border-radius:2px}.searchContext{font-size:11px;color:var(--muted)}.registerPasswordBox{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}.communityContent{min-height:300px}.mobileOnly{display:none}.mobileOverlay{display:none}.moveMulti{min-height:170px}.passwordWarn{border:1px solid #111;border-radius:9px;padding:10px 12px;background:#fafafa;font-size:12px;line-height:1.55}
@media(max-width:980px){#layout{grid-template-columns:1fr}#graphPane{display:none}.CodeMirror-scroll{padding:24px 24px 90px}#organizeView{padding:28px 30px 90px}.topNav{overflow-x:auto}.socialGrid{grid-template-columns:1fr}}@media(max-width:700px){body{overflow:hidden}header{height:48px;padding:5px 6px;gap:3px}header strong{display:none}.mobileOnly{display:inline-flex}.topNav{order:3;width:100%;margin:0;position:fixed;left:0;right:0;bottom:0;z-index:1300;background:#fff;border-top:1px solid var(--border);padding:4px 5px;justify-content:space-around}.topNav button{font-size:10px;padding:7px 7px}.profileBtn{margin-left:0;padding:4px 5px}.profileBtn .avatar{width:24px;height:24px}#logoutBtn{font-size:9px!important;padding:4px 5px!important}#profileHandle{display:none}#status{display:none}#docBar{flex:1 1 auto;order:1;min-width:0}#docBar button{font-size:10px;padding:5px 6px}#layout{grid-template-columns:1fr;height:calc(100vh - 48px);padding-bottom:48px}#sidebar{display:none;position:fixed;left:0;top:48px;bottom:48px;width:min(82vw,320px);z-index:1350;border-right:1px solid #111;box-shadow:8px 0 26px rgba(0,0,0,.12)}body.mobileSidebarOpen #sidebar{display:block}body.mobileSidebarOpen .mobileOverlay{display:block;position:fixed;inset:48px 0 48px;z-index:1340;background:rgba(0,0,0,.18)}#editorPane{min-width:0}.CodeMirror-scroll{padding:18px 14px 86px}.CodeMirror{font-size:15px}#organizeView{padding:14px 12px 76px}#editStructured{padding:10px 12px 76px}#bodyEditorWrap .CodeMirror-scroll{padding:8px 0 18px}.searchBar{grid-template-columns:1fr}.edgeZone{padding:0}.searchShell{gap:9px}#docBar{padding:5px 6px}#docBar button{font-size:10px;padding:5px 6px}#fileTitle{display:none}#authorBar{padding:7px 9px}.socialInner{padding:16px 12px 78px}.socialHeader{margin-bottom:12px}.socialHeader h2{font-size:18px}.feedCard{padding:12px}.feedTitle{font-size:16px}.profileHero{gap:10px}.profileHeroName{font-size:19px}.chatBox{height:52vh}.chatBubble{max-width:86%}dialog{min-width:0;width:calc(100vw - 22px);max-width:calc(100vw - 22px);padding:14px}.actions{flex-wrap:wrap}.actions button{flex:1 1 auto}.sectionSort{min-width:105px}.previewLink{gap:5px;padding:4px 4px}.previewAuthor{min-width:76px;max-width:110px}.graphHint{display:none}}


/* v53 desktop reference layout: one top row + three fixed work columns */
:root{
  --nn-left:clamp(250px,18.5vw,300px);
  --nn-right:clamp(390px,29.5vw,480px);
  --nn-header-h:58px;
}
header{
  height:var(--nn-header-h);
  display:grid;
  grid-template-columns:150px minmax(0,1fr) var(--nn-right);
  align-items:stretch;
  gap:0;
  padding:0;
  border-bottom:1px solid var(--border);
  background:#fff;
  min-width:0;
}
#headerBrand,#headerCenter,#headerRight{min-width:0;display:flex;align-items:center;background:#fff}
#headerBrand{padding:0 12px;border-right:1px solid var(--border);gap:8px}
#headerBrand strong{font-size:13px;margin:0;white-space:nowrap}
#headerCenter{padding:0 8px;gap:8px;overflow:hidden}
#headerRight{padding:0 8px;border-left:1px solid var(--border);gap:4px;overflow:hidden}
#authorBar{
  display:flex;align-items:center;gap:7px;flex:0 0 auto;
  max-width:190px;min-width:125px;padding:0;border:0;min-height:0;background:transparent;
}
#authorBar .authorText{min-width:0}
#authorBar .authorName,#authorBar .authorHandle{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#authorBar .authorName{font-size:11.5px}
#authorBar .authorHandle{font-size:9.5px}
#authorBar .avatar{width:30px;height:30px}
#authorBar .authorMeta{margin-left:0;flex:0 0 auto}
#authorBar .authorMeta button{padding:4px 6px;font-size:10px}
#docBar{flex:1 1 auto;min-width:0;padding:0;gap:4px;overflow-x:auto;white-space:nowrap}
#docBar button{font-size:10.5px;padding:5px 7px}
#headerRight .topNav{flex:1 1 auto;min-width:0;overflow-x:auto;justify-content:flex-start}
#headerRight .topNav button{font-size:10.5px;padding:5px 6px}
#headerRight #status{
  display:block;position:fixed;left:50%;bottom:18px;z-index:5000;
  min-width:0;max-width:min(520px,calc(100vw - 24px));padding:8px 12px;
  border:1px solid #bdbdbd;border-radius:999px;background:#fff;color:#111;
  box-shadow:0 5px 20px rgba(0,0,0,.16);font-size:12px;font-weight:650;
  text-align:center;opacity:0;pointer-events:none;transform:translate(-50%,8px);
  transition:opacity .16s ease,transform .16s ease;
}
#headerRight #status.visible{opacity:1;transform:translate(-50%,0)}
#headerRight #status.error{border-color:#b91c1c;color:#991b1b;background:#fff7f7}
@media(max-width:700px){#headerRight #status{bottom:60px}}
#headerRight .profileBtn{flex:0 0 auto;padding:3px 5px;max-width:94px}
#headerRight #profileHandle{max-width:48px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#headerRight #logoutBtn{flex:0 0 auto;padding:4px 6px!important;font-size:10px!important}
#layout{
  display:grid;
  grid-template-columns:minmax(0,1fr) var(--nn-right);
  height:calc(100vh - var(--nn-header-h));
  min-height:0;
}
#sidebar{padding:10px 12px}
#editorPane{min-width:0;min-height:0}
#graphPane{min-width:0;min-height:0}
#organizeView,#editStructured{max-width:900px;width:100%;margin:0 auto}
#socialView{height:calc(100vh - var(--nn-header-h))}
#trailBar{display:none!important}

@media (max-width:1180px) and (min-width:981px){
  :root{--nn-left:220px;--nn-right:350px}
  #authorBar{max-width:150px;min-width:105px}
  #authorBar .authorMeta{display:none}
  #docBar button{font-size:10px;padding:5px 6px}
  #headerRight .profileBtn #profileHandle{display:none}
}
@media (max-width:980px) and (min-width:701px){
  :root{--nn-header-h:58px;--nn-left:190px}
  header{grid-template-columns:var(--nn-left) minmax(0,1fr)}
  #headerRight{grid-column:2;border-left:0;position:absolute;right:6px;top:0;height:var(--nn-header-h);max-width:46%;background:#fff}
  #headerCenter{padding-right:47%}
  #authorBar{max-width:145px;min-width:100px}
  #authorBar .authorMeta{display:none}
  #layout{grid-template-columns:1fr;height:calc(100vh - var(--nn-header-h))}
}
@media (max-width:700px){
  :root{--nn-header-h:48px}
  header{height:var(--nn-header-h);display:flex;padding:5px 6px;gap:4px}
  #headerBrand{display:flex;border:0;padding:0;flex:0 0 auto}
  #headerBrand strong{display:none}
  #headerCenter{display:flex;flex:1 1 auto;padding:0;gap:4px;overflow:hidden}
  #headerRight{display:flex;border:0;padding:0;flex:0 0 auto;overflow:visible}
  #authorBar{display:none!important}
  #docBar{padding:0;flex:1 1 auto;order:initial}
  #headerRight .topNav{position:fixed;left:0;right:0;bottom:0;z-index:1300;width:100%;max-width:none;background:#fff;border-top:1px solid var(--border);padding:4px 5px;justify-content:space-around}
  #headerRight .profileBtn{padding:4px 5px;max-width:none}
  #headerRight #profileHandle{display:none}
  #headerRight #logoutBtn{font-size:9px!important;padding:4px 5px!important}
  /* Do not leave mobile sizing to the desktop grid. Some Android browsers keep
     its hidden graph track in the intrinsic grid calculation and collapse the
     editor track to roughly its padding width. A normal block gives the note a
     definite viewport width; the mobile sidebar is fixed-position separately. */
  #layout{display:block!important;width:100%;height:calc(100vh - var(--nn-header-h));padding-bottom:48px}
  #editorPane{width:100%;max-width:100%;height:100%}
  #organizeWrap,#organizeView{width:100%;max-width:100%}
  #sidebar{top:var(--nn-header-h)}
  body.mobileSidebarOpen .mobileOverlay{inset:var(--nn-header-h) 0 48px}
  #socialView{height:calc(100vh - var(--nn-header-h));padding-bottom:48px}
}


/* v54 interaction cleanup */
.viewModeToggle{font-size:10.5px;padding:5px 9px;border:1px solid var(--border);border-radius:8px;background:#fff;color:#111;white-space:nowrap;flex:0 0 auto;min-width:72px}
.edgeOtherToggle{display:inline-flex!important;grid-template-columns:none!important;align-items:center;gap:4px;font-size:9.5px;color:var(--muted);white-space:nowrap;margin:0 2px 0 0}.edgeOtherToggle input{width:14px;height:14px;margin:0;accent-color:#000}.edgeOtherDivider{font-size:9px;color:var(--muted);border-top:1px solid #ddd;margin:4px 0 2px;padding:4px 4px 0}.edgeNewBox{border-top:1px solid var(--border);padding-top:9px;display:grid;gap:7px}.edgeNewBox button{justify-self:start}.graphNode.other circle{fill:#a21caf;stroke:#a21caf}
@media(max-width:700px){.viewModeToggle{font-size:10px;padding:5px 7px}.edgeOtherToggle{font-size:9px}}

/* v60 editing / Vim / neutral graph */
#bodyEditorWrap .CodeMirror{line-height:1.46}
#bodyEditorWrap .CodeMirror pre.CodeMirror-line,#bodyEditorWrap .CodeMirror pre.CodeMirror-line-like{margin:0;padding-top:0;padding-bottom:0}
.vimIndicator{padding:4px 7px!important;font-size:9.5px!important;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:.03em;min-width:78px;text-align:center}
.vimIndicator.normal{background:#111;color:#fff;border-color:#111}.vimIndicator.insert{background:#fff;color:#111}.vimIndicator.visual{background:#1d4ed8;color:#fff;border-color:#1d4ed8}
.graphNode circle,.graphNode.support circle,.graphNode.oppose circle,.graphNode.question circle,.graphNode.answer circle,.graphNode.derive circle,.graphNode.related circle,.graphNode.topic circle,.graphNode.note circle,.graphNode.summary circle,.graphNode.other circle,.graphNode.current circle{fill:#000!important;stroke:#000!important}

/* v63 Edit/Organize layout parity.
   Parent, body and Child use the same outer spacing.  The Edit body remains
   editable, but it participates in normal document flow and never overlays
   the Child zone. */
#organizeView,#editStructured{max-width:900px;width:100%;margin:0 auto;padding:34px 52px 110px}
#editBodyShell{margin:0;padding:0 0 4px;overflow:visible}
#editBodyLabel{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:750;margin:3px 0 5px}
#bodyEditorWrap{display:block;position:relative;overflow:hidden!important;min-height:1.68em}
#bodyEditorWrap .CodeMirror{height:auto!important;min-height:1.68em!important;overflow:hidden!important;line-height:1.68}
#bodyEditorWrap .CodeMirror-scroll{height:auto!important;min-height:1.68em!important;max-height:none!important;overflow:hidden!important;padding:0!important}
#bodyEditorWrap .CodeMirror-lines{max-width:none;margin:0;padding:0!important}
#bodyEditorWrap .CodeMirror-sizer{min-height:1.68em!important;min-width:0!important;padding-bottom:0!important;border-right:0!important}
#bodyEditorWrap .CodeMirror-vscrollbar,#bodyEditorWrap .CodeMirror-hscrollbar,#bodyEditorWrap .CodeMirror-scrollbar-filler,#bodyEditorWrap .CodeMirror-gutter-filler{display:none!important;width:0!important;height:0!important}
/* Organize inserts a 5px direction gap before the incoming edge zone. */
#editChildEdges{display:block;position:relative;clear:both;padding-top:5px;overflow:visible}
@media(max-width:980px){#organizeView,#editStructured{padding:28px 30px 90px}}
@media(max-width:700px){#organizeView,#editStructured{padding:14px 12px 76px}}


/* v68 local-first / moderation */
/* v71: exact chronological Vim Backspace history; keeps v70 source-only editing. */
.uploadToggle{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;white-space:nowrap;padding:4px 6px;border:1px solid var(--border);border-radius:7px}.uploadToggle input{margin:0}.edgePrivacyBtn{padding:3px 6px!important;font-size:11px!important;line-height:1!important}.edgePrivacyBtn.private{background:#111;color:#fff;border-color:#111}.dataGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.dataCard{border:1px solid var(--border);border-radius:11px;padding:14px;background:#fff}.dataCard h3{margin:0 0 9px;font-size:15px}.dataCard p{font-size:12px;line-height:1.55;color:#444}.exportList{max-height:260px;overflow:auto;border:1px solid var(--border);border-radius:9px;padding:7px;background:#fff}.exportItem{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;align-items:center;padding:6px 4px;border-bottom:1px solid #eee;font-size:12px}.exportItem:last-child{border-bottom:0}.exportItem small{color:var(--muted);white-space:nowrap}.exportSectionTitle{font-size:12px;font-weight:750;margin:8px 0 5px}.dataCard .actions{justify-content:flex-start}.quotaRow{display:grid;grid-template-columns:95px 1fr auto;gap:8px;align-items:center;font-size:11px;margin:7px 0}.quotaBar{height:7px;background:#e5e5e5;border-radius:999px;overflow:hidden}.quotaBar>i{display:block;height:100%;background:#111}.syncForm{display:grid;gap:9px}.syncForm input{width:100%}.tokenBox{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;word-break:break-all;padding:9px;background:#f6f6f6;border:1px solid var(--border);border-radius:8px}.adminTable{width:100%;border-collapse:collapse;font-size:11px}.adminTable th,.adminTable td{text-align:left;border-bottom:1px solid var(--border);padding:7px 6px;vertical-align:top}.adminTable .actions{justify-content:flex-start;gap:4px}.adminTable button{padding:4px 7px;font-size:10px}.statusSuspended{font-weight:700;color:#991b1b}.roleBadge{display:inline-block;padding:2px 6px;border-radius:999px;background:#eee;font-size:9px;font-weight:700;text-transform:uppercase}.reportCard{border:1px solid var(--border);border-radius:9px;padding:10px;margin:7px 0;font-size:11px}.reportReason{white-space:pre-wrap;margin:6px 0}.localHint{font-size:10px;color:var(--muted)}
.guestWriteBtn{font-weight:750;white-space:nowrap}.guestBadge{font-size:10px;color:var(--muted)}
/* v80 Source/box relationship projection: collaborative Parent/Child edges are visible in Source as auto-synced read-only metadata. */
.nnAutoEdgeLine{background:#f7f7f7;color:#666}
.nnAutoEdgeLine .cm-comment{color:#777}
/* v79 Local/Web sync download, real community Index notes, Index child-only layout, community admin */
.organizeBody{padding:0!important}.organizeBody>.previewSection:first-child{margin-top:0}.organizeBody>.previewSection:first-child h1{margin-top:0;margin-bottom:.08em}.organizeBody>.previewSection:first-child .previewLine:first-of-type{margin-top:0}.previewSection{margin:.08em 0 .52em}.previewSection h1,.previewSection h2,.previewSection h3{margin:.30em 0 .12em}.previewLine{margin:.10em 0;line-height:1.62}.communityAdminForm{display:grid;gap:9px}.communityAdminForm input,.communityAdminForm textarea{width:100%}.communityMemberRow{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px}.communityMemberMeta{color:var(--muted);font-size:10px}.communityAdminActions{display:flex;gap:6px;flex-wrap:wrap}.localSyncPrimary{border:2px solid #111;border-radius:10px;padding:12px;background:#fafafa}.localSyncPrimary h3{margin:0 0 7px}.localSyncSecondary{margin-top:10px;border-top:1px solid var(--border);padding-top:9px}.localSyncSecondary summary{cursor:pointer;font-size:11px;color:var(--muted)}
/* v78 relation organization, collaborative Parent edges, bounded edge previews, Vim edge workflow, global quotas */
.edgeGroupItems{display:grid;gap:1px}
.edgeGroupMore{display:flex;justify-content:flex-start;margin:2px 0 5px}.edgeGroupMore button{padding:3px 7px;font-size:10px}
.edgeZone.outgoing.edgeZoneBounded{position:relative;max-height:320px;overflow:hidden}
.edgeZone.outgoing.edgeZoneBounded:after{content:"";position:absolute;left:0;right:0;bottom:0;height:42px;background:linear-gradient(transparent,#fff);pointer-events:none}
.edgeZoneExpandAll{padding:3px 7px!important;font-size:10px!important}
.edgeOwnerBadge{font-size:9px;color:var(--muted);border:1px solid var(--border);border-radius:999px;padding:1px 5px;white-space:nowrap}
.organizeEdgesGrid{display:grid;gap:9px}.organizeEdgesGrid .row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}.organizeEdgesGrid select,.organizeEdgesGrid input{width:100%}.organizeEdgeMode{display:flex;gap:8px;flex-wrap:wrap}.organizeEdgeMode label{display:flex;grid-template-columns:auto 1fr;align-items:center;gap:5px;border:1px solid var(--border);border-radius:8px;padding:6px 8px}
.globalQuotaBox{border:2px solid #111;border-radius:10px;padding:11px;margin-bottom:12px;background:#fafafa}.globalQuotaBox h3{margin:0 0 7px}.globalQuotaActions{display:flex;gap:7px;align-items:end;flex-wrap:wrap}.globalQuotaActions label{font-size:10px;color:var(--muted);display:grid;gap:3px}.globalQuotaActions input{width:120px}
/* v77 navigation, graph controls, IME-safe Vim, search, quotas, and Local sync */
.mainTopNav{display:flex;align-items:center;gap:3px;overflow-x:auto;scrollbar-width:none;max-width:min(52vw,640px)}.mainTopNav::-webkit-scrollbar{display:none}.mainTopNav button{border:0;background:transparent;border-radius:8px;padding:7px 9px;font-size:11px;white-space:nowrap}.mainTopNav button:hover,.mainTopNav button.active{background:#e7e7e7;font-weight:700}.sectionHead{display:flex;align-items:center;gap:8px;margin-bottom:10px}.sectionHead h3{margin:0;margin-right:auto;font-size:15px}.sectionMore{border:0;background:transparent;padding:4px 5px;color:#276fbe;font-size:11px}.sectionMore:hover{text-decoration:underline;background:transparent}.profileSection.navigable{cursor:pointer;transition:background .12s ease}.profileSection.navigable:hover{background:#fafafa}.profileSection.navigable:focus-visible{outline:2px solid #111;outline-offset:2px}.profileIndexBody.preview{max-height:230px;overflow:hidden;position:relative}.profileIndexBody.preview:after{content:"";position:absolute;left:0;right:0;bottom:0;height:48px;pointer-events:none;background:linear-gradient(transparent,#fff)}.profileSection.navigable:hover .profileIndexBody.preview:after{background:linear-gradient(transparent,#fafafa)}.profileSection .sectionFeed.previewFeed .feedCard:nth-child(n+4){display:none}.socialBackBtn{margin-right:4px}.homeSections{display:grid;gap:18px}.profileIndexMissing{color:var(--muted);font-size:12px;padding:4px 0}.profileSection[data-open-section]{cursor:pointer}
@media(max-width:900px){.mainTopNav{max-width:46vw}}
@media(max-width:700px){.mainTopNav{position:fixed;left:0;right:0;bottom:0;z-index:1300;max-width:none;width:100%;background:#fff;border-top:1px solid var(--border);padding:4px 5px;justify-content:space-around}.mainTopNav button{font-size:9.5px;padding:7px 5px}.profileIndexBody.preview{max-height:190px}}

/* v77 dropdown navigation + profile home */
.mainNavWrap{position:relative;flex:0 0 auto;z-index:4100}.mainNavBtn{min-width:96px;border:1px solid var(--border);border-radius:9px;background:#fff;color:#111;padding:6px 9px;font-size:11px;font-weight:700;text-align:left}.mainNavMenu{position:absolute;right:0;top:calc(100% + 5px);z-index:4200;min-width:170px;padding:5px;background:#fff;border:1px solid var(--border);border-radius:10px;box-shadow:0 10px 28px rgba(0,0,0,.13)}.mainNavMenu[hidden]{display:none}.mainNavMenu button{display:block;width:100%;text-align:left;border:0;background:#fff;padding:8px 10px;border-radius:7px;font-size:12px}.mainNavMenu button:hover,.mainNavMenu button.active{background:#eee}.mainNavMenu button[hidden]{display:none}.indexChildPreview{margin-top:10px;padding-top:9px;border-top:1px solid var(--border)}.indexChildTitle{font-size:11px;font-weight:800;margin-bottom:5px}.indexChildList{display:grid;gap:3px}.indexChildItem{display:flex;align-items:center;gap:7px;width:100%;border:0;background:transparent;padding:5px 4px;text-align:left;border-radius:6px;color:var(--link);font-size:12px}.indexChildItem:hover{background:#f3f3f3}.indexChildRelation{color:var(--muted);font-size:10px;min-width:54px}.indexChildMore{font-size:10px;color:var(--muted);padding:4px}.cm-ime-normal-fix{outline:none}
@media(max-width:700px){.mainNavBtn{min-width:82px;font-size:10px;padding:5px 7px}.mainNavMenu{right:0;min-width:155px}}
/* v74 navigation, profile/community sections, Markdown tasks/tables */
.navMenu{position:relative;flex:0 0 auto}.navMenuBtn{font-size:10.5px;padding:5px 8px}#headerRight #topNav.navMenuPanel{position:absolute;left:auto;right:0;top:calc(100% + 6px);bottom:auto;z-index:1800;display:grid;min-width:150px;width:auto;max-width:none;overflow:visible;padding:5px;background:#fff;border:1px solid var(--border);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.14)}.navMenuPanel[hidden]{display:none}.navMenuPanel button{border:0;border-radius:7px;text-align:left;background:#fff;font-size:11px;padding:7px 9px}.navMenuPanel button:hover,.navMenuPanel button.active{background:#e5e5e5}
#mobileNodesBtn{display:none}.profileSections{display:grid;gap:18px}.profileSection{border:1px solid var(--border);border-radius:12px;padding:14px;background:#fff}.profileSection>h3{margin:0 0 10px;font-size:15px}.profileQuickSearch{display:flex;gap:8px}.profileQuickSearch input{flex:1}.profileQuickSearch button{flex:0 0 auto}.profileIndexBody{font-size:13px}.sectionFeed{display:grid;gap:9px}.sectionFeed .feedCard{padding:12px}.communityIndexActions{display:flex;gap:7px;justify-content:flex-end;margin-bottom:8px}
.taskItem{display:flex;align-items:flex-start;gap:8px;line-height:1.55;margin:.28em 0}.taskItem input{width:17px;height:17px;margin-top:.18em;accent-color:#000;flex:0 0 auto}.taskItem.done .taskText{text-decoration:line-through;color:var(--muted)}.taskItem input:disabled{opacity:.65}.mdTableWrap{overflow-x:auto;margin:10px 0}.mdTable{border-collapse:collapse;width:max-content;min-width:min(100%,560px);font-size:13px}.mdTable th,.mdTable td{border:1px solid var(--border);padding:7px 9px;text-align:left;vertical-align:top}.mdTable th{background:#f6f6f6;font-weight:750}.mdTable code{white-space:nowrap}
#organizeWrap{scroll-behavior:smooth}.CodeMirror-scroll{scroll-behavior:smooth}
@media(max-width:700px){#mobileNodesBtn{display:inline-flex}body.mobileSidebarOpen #sidebar{display:block!important}#headerRight #topNav.navMenuPanel{position:fixed;left:auto;right:8px;top:52px;bottom:auto;width:170px;padding:5px;justify-content:stretch}.profileQuickSearch{display:grid}}
#headerRight{overflow:visible!important;position:relative;z-index:4000}
</style>
</head>
<body>
<div id="authGate" class="authGate hidden"><form id="authForm" class="authCard"><h1>Network Notes</h1><p id="authPrompt">この操作にはログインまたは登録が必要です</p><div id="localSyncAuth" class="localSyncPrimary" hidden><h3>Webアカウントに接続</h3><div class="profileHint">Localはアカウントなしで使えます。Webへ共有・同期するときだけ、Web版の既存アカウントでログインするか、新しいWebアカウントを作成します。WebパスワードはLocalには保存しません。</div><label>Webサーバー<input id="authSyncServer" value="https://network-notes.duckdns.org"></label><label>Webユーザー名<input id="authWebUsername" autocomplete="username" maxlength="32" placeholder="ユーザー名"></label><label>Webパスワード<input id="authWebPassword" type="password" autocomplete="current-password" placeholder="8文字以上"></label><div class="authActions"><button id="authWebLoginBtn" type="button">既存アカウントでログイン</button><button id="authWebRegisterBtn" type="button">Webアカウントを作成</button><button id="authOpenWebBtn" type="button">Web版を開く</button></div><details class="localSyncSecondary"><summary>同期キーで接続する</summary><label>ローカル同期キー<input id="authSyncToken" type="password" autocomplete="off" placeholder="nn_... の同期キー"></label><div class="authActions"><button id="authSyncConnectBtn" type="button">同期キーで接続</button></div></details></div><div id="localPasswordAuth"><label>ユーザー名<input id="authUsername" autocomplete="username" maxlength="32" /></label><label>パスワード<input id="authPassword" type="password" autocomplete="current-password" minlength="8" /></label><div class="authActions"><button id="loginBtn" type="submit">ログイン</button><button id="registerBtn" type="button">新規登録</button></div></div><div class="authActions"><button id="authCancelBtn" type="button">キャンセル</button></div><div id="authError" class="authError"></div></form></div>
<header>
  <div id="headerBrand"><strong>Network Notes</strong><button id="mobileNodesBtn" class="mobileOnly" type="button" aria-controls="sidebar" aria-expanded="false">ノート</button></div>
  <div id="headerCenter">
    <div id="authorBar"><span id="noteAuthorAvatar"></span><div class="authorText"><span id="noteAuthorName" class="authorName"></span><span id="noteAuthorHandle" class="authorHandle"></span></div><div class="authorMeta"><button id="likeBtn" type="button">♡ 0</button><button id="reportNoteBtn" type="button" style="display:none">通報</button></div></div>
    <div id="docBar">
      <div id="fileTitle">Index.md</div>
      <button id="viewModeToggle" class="viewModeToggle" type="button" aria-label="整理ビューとソースを切替" title="Ctrl+E: 整理ビュー / ソース切替">整理ビュー</button>
      <button id="vimIndicator" class="vimIndicator insert" type="button" title="Esc: NORMAL / i: INSERT">VIM INSERT</button>
      <button id="newRootBtn" class="guestWriteBtn" type="button">＋ ノートを作成</button>
      <button id="contextActionBtn" title="Vim: em">移動・分類</button>
      <button id="deleteCurrentBtn" type="button" style="display:none;border-color:#b91c1c" title="Vim: nd">削除</button>
      <button id="copyLinkBtn" type="button">リンクをコピー</button>
      <label id="uploadToggleWrap" class="uploadToggle" style="display:none"><input id="uploadToggle" type="checkbox" checked> Webへ</label>
      <button id="publicVersionBtn" type="button" style="display:none">公開版</button>
      <input id="imageInput" type="file" accept="image/jpeg,image/png,image/gif,image/webp" hidden />
      <input id="attachmentInput" type="file" accept="image/*,application/pdf,text/plain,text/markdown,.md,.txt,.pdf" hidden />
      <button id="attachmentBtn" type="button">添付</button>
      <button id="taskBtn" type="button" title="チェックボックスを作る（Vim: nt / 切替: nx）">☑</button>
      <button id="tableBtn" type="button" title="Markdownテーブルを挿入（Vim: mt）">表</button>
      <button id="shareCommunityBtn" type="button">コミュニティに共有</button>
    </div>
  </div>
  <div id="headerRight">
    <div id="mainNavWrap" class="mainNavWrap">
      <button id="mainNavBtn" class="mainNavBtn" type="button" aria-haspopup="menu" aria-expanded="false">ホーム ▾</button>
      <div id="mainNavMenu" class="mainNavMenu" role="menu" hidden>
        <button type="button" data-main-nav="home">ホーム</button>
        <button type="button" data-main-nav="communities">コミュニティ</button>
        <button type="button" data-main-nav="search">検索</button>
        <button type="button" data-main-nav="dm">メッセージ</button>
        <button type="button" data-main-nav="data">データ</button>
        <button id="adminNavOption" type="button" data-main-nav="admin">管理</button>
      </div>
    </div>
    <span id="status" role="status" aria-live="polite" aria-atomic="true"></span>
    <button id="profileBtn" class="profileBtn" type="button" title="プロフィール"><span id="profileAvatar"></span><span id="profileHandle">user</span></button>
    <button id="logoutBtn" type="button" style="padding:5px 8px;font-size:11px">ログアウト</button>
  </div>
</header><div id="mobileOverlay" class="mobileOverlay"></div>
<div id="trailBar"><span id="trailLabel">Outgoing</span><div id="trail"></div><button id="trailReset" type="button">リセット</button></div>
<div id="layout">
<aside id="sidebar" aria-hidden="true"><select id="nodeSort"><option value="newest">新しい順</option><option value="oldest">古い順</option></select><button id="nodeSelectBtn" type="button">選択</button><button id="nodeDeleteBtn" type="button" disabled>削除</button><div id="files"></div></aside>
<main id="editorPane">
  <div id="editWrap"><div id="editStructured">
    <div id="editParentEdges"></div>
    <div id="editBodyShell"><div id="editBodyLabel">本文</div><div id="bodyEditorWrap"><textarea id="bodySource"></textarea></div></div>
    <div id="editChildEdges"></div>
  </div></div>
  <div id="sourceWrap"><textarea id="source"></textarea></div>
  <div id="organizeWrap"><div id="organizeView"></div></div>
</main>
<aside id="graphPane">
  <div id="graphControls">
    <div class="graphTitleRow"><strong>Local graph</strong><span id="graphCountLabel" class="metrics"></span><button id="graphControlsToggle" class="graphControlsToggle" type="button" aria-expanded="true">隠す</button></div>
    <label class="graphControl"><span>ノード数</span><input id="graphLimit" type="range" min="5" max="50" step="1" value="18"><span id="graphLimitValue" class="graphValue">18</span></label>
    <label class="graphControl"><span>段数</span><input id="graphDepth" type="range" min="1" max="4" step="1" value="2"><span id="graphDepthValue" class="graphValue">2</span></label>
    <label class="graphControl"><span>間隔</span><input id="graphSpacing" type="range" min="45" max="180" step="5" value="90"><span id="graphSpacingValue" class="graphValue">90</span></label>
    <label class="graphControl"><span>文字サイズ</span><input id="graphFontSize" type="range" min="8" max="20" step="1" value="11"><span id="graphFontSizeValue" class="graphValue">11</span></label>
    <label class="graphControl"><span>関係名</span><input id="graphRelationLabels" type="checkbox" checked><span id="graphRelationLabelsValue" class="graphValue">ON</span></label>
  </div>
  <div id="graphWrap"><svg id="localGraph" role="img" aria-label="ローカルグラフ"></svg><div class="graphHint">ドラッグで移動・クリックで開く</div></div>
</aside>
</div>
<section id="socialView"><div id="socialContent" class="socialInner"></div></section>
<dialog id="newDialog"><form method="dialog" id="newForm">
<h3 style="margin:0">ノードを追加</h3>
<label>タイトル<input id="newTitle" required /></label>
<div>
  <div style="font-size:13px;margin-bottom:7px">現在のページとの関係</div>
  <div id="relationChoices" class="relationChoices"></div>
</div>
<label id="customRelationWrap" style="display:none">その他の関係<input id="customRelation" placeholder="関係名" /></label>
<div style="font-size:12px;opacity:.7">関係は <code>関係::[ノート](file.md)</code> 形式で保存されます。</div>
<div class="actions"><button value="cancel">キャンセル</button><button id="createBtn" value="default">作成</button></div>
</form></dialog>
<dialog id="organizeEdgesDialog"><form method="dialog" id="organizeEdgesForm">
<h3 style="margin:0">移動・分類</h3>
<div class="profileHint">現在のページに表示されているChildリンクを、カテゴリーへ移動または追加します。他の人が作ったリンクは移動できませんが、追加はできます。</div>
<div class="organizeEdgesGrid">
  <label>対象リンク<select id="organizeEdgeItem" size="7"></select></label>
  <div class="row"><label>関係<select id="organizeEdgeRelation"><option>カテゴリー</option><option>ノート</option><option>賛同</option><option>否定</option><option>質問</option><option>回答</option><option>関連</option><option>言及</option><option>雑談</option></select></label><label>処理<div class="organizeEdgeMode"><label><input type="radio" name="organizeEdgeMode" value="move" checked>移動</label><label><input type="radio" name="organizeEdgeMode" value="add">追加</label></div></label></div>
  <label>既存カテゴリー<select id="organizeEdgeCategory"></select></label>
  <div class="row"><label>または新しいカテゴリー<input id="organizeEdgeNewCategory" maxlength="160" placeholder="カテゴリー名"></label><div class="profileHint" id="organizeEdgePermissionHint"></div></div>
</div>
<div class="actions"><button value="cancel">キャンセル</button><button id="organizeEdgeSubmit" type="button">実行</button></div>
</form></dialog>
<dialog id="profileDialog"><form method="dialog" id="profileForm">
<h3 style="margin:0">プロフィール</h3>
<div class="avatarPreview"><span id="profileDialogAvatar"></span><label>プロフィール画像<input id="profileAvatarInput" type="file" accept="image/jpeg,image/png,image/gif,image/webp" /></label></div>
<label>ユーザー名<input id="profileUsername" maxlength="32" readonly /></label><div class="profileHint">ユーザー名は固有IDです。登録後は変更できません。</div>
<label>表示名<input id="profileDisplayName" maxlength="120" /></label>
<label>自己紹介<textarea id="profileBio" class="profileBio" maxlength="1000"></textarea></label>
<div class="profileHint">自分のノートにも、プロフィール画像・表示名・ユーザー名が常に表示されます。</div>
<div class="actions"><button value="cancel">キャンセル</button><button id="profileSave" value="default">保存</button></div>
</form></dialog>
<dialog id="communityCreateDialog"><form method="dialog" id="communityCreateForm"><h3 style="margin:0">コミュニティを作成</h3><label>名前<input id="communityName" maxlength="120" required /></label><label>説明<textarea id="communityDescription" class="profileBio" maxlength="1000"></textarea></label><div class="actions"><button value="cancel">キャンセル</button><button value="default">作成</button></div></form></dialog>
<dialog id="communityIndexDialog"><form method="dialog" id="communityIndexForm"><h3 style="margin:0">コミュニティIndexを編集</h3><label>Index<textarea id="communityIndexMarkdown" class="profileBio" style="min-height:280px" placeholder="# Index"></textarea></label><div class="actions"><button value="cancel">キャンセル</button><button id="communityIndexSave" value="default">保存</button></div></form></dialog>
<dialog id="communityShareDialog"><form method="dialog" id="communityShareForm"><h3 style="margin:0">コミュニティに共有</h3><label>コミュニティ<select id="communityShareSelect"></select></label><div class="actions"><button value="cancel">キャンセル</button><button value="default">共有</button></div></form></dialog>
<div id="editorContextMenu" class="editorContextMenu"><button id="linkifyMenuItem" type="button">リンク化</button><button id="imageMenuItem" type="button">画像を添付</button></div>
<dialog id="linkifyDialog"><form method="dialog" id="linkifyForm"><h3 style="margin:0">リンク化</h3><div class="profileHint">選択した文章は表示名として固定され、リンク先ノート名を変更しても同期しません。</div><div id="linkifySelected" class="linkifySelected"></div><label>リンク先を検索<input id="linkifySearch" placeholder="ノート名 / @ユーザー名" autocomplete="off" /></label><label>既存ノート<select id="linkifyTarget" class="linkifyTarget" size="8"></select></label><div style="border-top:1px solid var(--border);padding-top:10px"><label>新しいノートのタイトル<input id="linkifyNewTitle" maxlength="160" placeholder="選択した文章を初期値にします" /></label></div><div class="actions"><button value="cancel">キャンセル</button><button id="linkifyNewBtn" type="button">＋ 新しいノートを作成してリンク</button><button id="linkifySubmit" value="default">既存ノートにリンク</button></div></form></dialog>

<dialog id="deleteNotesDialog"><form method="dialog" id="deleteNotesForm"><h3 style="margin:0">ノートを削除</h3><div class="profileHint">自分のノートだけ削除できます。Indexは削除できません。</div><div id="deleteNotesList" style="max-height:260px;overflow:auto;border:1px solid var(--border);border-radius:8px;padding:9px;font-size:12px"></div><div class="actions"><button value="cancel">キャンセル</button><button id="deleteNotesConfirm" type="button" style="border-color:#b91c1c">削除する</button></div></form></dialog>
<dialog id="edgeDialog"><form method="dialog" id="edgeForm"><h3 id="edgeDialogTitle" style="margin:0">エッジを追加</h3><div id="edgeDialogHint" class="profileHint"></div><label>関係<select id="edgeRelation"><option>カテゴリー</option><option>ノート</option><option>賛同</option><option>否定</option><option>質問</option><option>回答</option><option>関連</option><option>言及</option><option>雑談</option><option class="localOnlyRelation" value="公開版" hidden>公開版</option><option value="__custom__">その他...</option></select></label><label id="edgeCustomWrap" style="display:none">関係名<input id="edgeCustomRelation" maxlength="80" placeholder="関係名" /></label><div class="edgeDialogSearchRow"><label id="edgeSearchLabel">ノートを検索<input id="edgeSearch" autocomplete="off" placeholder="タイトル・本文・@ユーザー名" /></label><label>候補<select id="edgeTarget" class="edgeTargetList" size="8"></select></label></div><label>またはMarkdownリンク / ファイル名を貼り付け<input id="edgePaste" class="edgePaste" placeholder="[ノート名](username__20260829123456.md)" /></label><div class="edgeNewBox"><div class="profileHint">または、この関係で新しいノートを作成</div><label>新しいノートのタイトル<input id="edgeNewTitle" maxlength="160" placeholder="タイトル" /></label><button id="edgeNewBtn" type="button">＋ 新しいノートを作成</button></div><div class="actions"><button value="cancel">キャンセル</button><button id="edgeSubmit" value="default">既存ノートを追加</button></div></form></dialog>

<dialog id="localExportDialog"><form method="dialog" id="localExportForm"><h3 style="margin:0">Webへエクスポート</h3><div class="profileHint">オンライン版へ送るノートと添付ファイルを選択します。ローカル専用ノート・非公開リンク・公開版の規則は自動的に適用されます。</div><div class="exportSectionTitle">ノート</div><div id="localExportNotes" class="exportList"></div><div class="actions"><button id="localExportNotesAll" type="button">ノート全選択</button><button id="localExportNotesNone" type="button">ノート解除</button></div><div class="exportSectionTitle">添付ファイル</div><div id="localExportAttachments" class="exportList"></div><div class="actions"><button id="localExportAttachmentsAll" type="button">添付全選択</button><button id="localExportAttachmentsNone" type="button">添付解除</button></div><div id="localExportSummary" class="profileHint"></div><div class="actions"><button value="cancel">キャンセル</button><button id="localExportConfirm" type="button">選択したものをWebへ送る</button></div></form></dialog>
<dialog id="registerSaveDialog"><form method="dialog" id="registerSaveForm"><h3 style="margin:0">パスワードを今すぐ保存してください</h3><div class="passwordWarn">このサービスはパスワードの平文を保存しません。忘れた場合に現在のパスワードを表示することはできません。アカウントを作成する前に、パスワードマネージャーなどへ保存してください。</div><label>登録するパスワード<input id="registerPasswordPreview" class="registerPasswordBox" readonly /></label><div class="actions"><button id="registerCopyBtn" type="button">パスワードをコピー</button></div><label style="display:flex;grid-template-columns:auto 1fr;align-items:center;gap:8px"><input id="registerSavedCheck" type="checkbox">保存したことを確認しました</label><div class="actions"><button value="cancel">戻る</button><button id="registerConfirmBtn" type="button" disabled>保存したので登録</button></div></form></dialog>
<script src="/static/codemirror.js"></script>
<script src="/static/xml.js"></script>
<script src="/static/meta.js"></script>
<script src="/static/markdown.js"></script>
<script src="/static/continuelist.js"></script>
<script src="/static/active-line.js"></script>
<script>
let current=null, dirty=false, currentData=null, mode='organize', autosaveTimer=null, loadingDoc=false, relationSyncPending=false;
let editRevision=0;
const saveClientSession=(globalThis.crypto?.randomUUID?.()||('nn-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)));
let saveChain=Promise.resolve();
let modeSwitchPromise=null;
let currentStructureSignature='';
const imeIdleWaiters=[];
const GUEST_PROFILE={id:null,username:'guest',display_name:'ゲスト',bio:'',avatar_url:'',index_file:null,role:'guest',status:'active',local_mode:false,guest:true};
let runtimeLocalMode=false;
let profile={...GUEST_PROFILE};
let pendingAuthAction=null;
function isGuest(){return !runtimeLocalMode&&!profile?.id}
let activeSocialView='network';
let socialPollTimer=null;
let navigationTrail=[];
let organizeLinkIndex=-1;
let organizeSectionIndex=-1;
let graphTimer=null;
let graphFrame=null;
let graphRunToken=0;
let graphShowRelationLabels=localStorage.getItem('nnGraphRelationLabels')!=='0';
let graphControlsCollapsed=localStorage.getItem('nnGraphControlsCollapsed')==='1';
let topicLineWidgets=[];
let pendingLinkifySelection=null;
let imageInsertEditor=null;
let linkifyTargets=[];
let nodeSelectionMode=false;
let selectedNodeFiles=new Set();
let edgeDialogMode='outgoing';
let edgeSearchTimer=null;
let edgeEditMode={outgoing:false,incoming:false};
let selectedEdgeKeys={outgoing:new Set(),incoming:new Set()};
let showOtherEdgeNodes={outgoing:localStorage.getItem('nnShowOtherOutgoing')!=='0',incoming:localStorage.getItem('nnShowOtherIncoming')!=='0'};
let edgeExpandedGroups={outgoing:new Set(),incoming:new Set()};
let edgeExpandAll={outgoing:false,incoming:false};
const EDGE_GROUP_PREVIEW={outgoing:4,incoming:5};
let organizeEdgePrefillFile='';
let searchState={q:'',scope:'all',community_id:0,user_id:0};
let activeProfileUserId=0;let communityViewState={id:0,tab:'posts'};
let searchTimer=null;
const voterId=(()=>{let v=localStorage.getItem('networkNotesVoterId');if(!v){v=(globalThis.crypto&&crypto.randomUUID)?crypto.randomUUID():'local-'+Date.now()+'-'+Math.random().toString(16).slice(2);localStorage.setItem('networkNotesVoterId',v)}return v})();
const sectionSort=new Map();
const $=id=>document.getElementById(id);
let vimInputMode='insert';
let vimVisual=null;          // null | 'char' | 'line' (only meaningful while vimInputMode==='normal')
let vimVisualAnchor=null;    // {line,ch} fixed end of the visual selection
let vimPendingCommand='';
let vimRegister='';
let vimRegisterLinewise=false;
let vimNormalLinkMarks=[];
let pendingSourceCursorFromBody=null;
const vimImeComposing=new WeakSet();
const vimImeEndedAt=new WeakMap();
function requestedNoteFromUrl(){try{return new URL(window.location.href).searchParams.get('note')||''}catch(_){return ''}}
function syncNoteUrl(name,replace=false){
  if(!name)return;
  const u=new URL(window.location.href);
  u.searchParams.set('note',name);
  u.hash='';
  const next=u.pathname+u.search;
  const cur=window.location.pathname+window.location.search;
  if(next===cur)return;
  const fn=replace?'replaceState':'pushState';
  history[fn]({note:name},'',next);
}
async function api(path,opts={}){const r=await fetch(path,opts);let data=null;try{data=await r.json()}catch(_){data={error:await r.text()}}if(!r.ok){if(r.status===401&&data?.auth_required)showAuth(data?.error||'ログインが必要です');throw new Error(data?.error||('HTTP '+r.status))}return data;}
let statusTimer=null;
function status(msg,{kind='info',timeout}={}){
  const el=$('status');
  if(kind==='info'&&/(?:エラー|失敗|できません|見つかりません)/.test(String(msg||'')))kind='error';
  if(statusTimer){clearTimeout(statusTimer);statusTimer=null}
  el.textContent=String(msg||'');
  el.classList.toggle('error',kind==='error');
  el.classList.toggle('visible',!!msg);
  if(!msg)return;
  const delay=timeout??(kind==='error'?6000:2200);
  if(delay>0)statusTimer=setTimeout(()=>{
    if(el.textContent===String(msg)){el.classList.remove('visible');el.textContent=''}
  },delay);
}
function profileUsername(){return isGuest()?'guest':(String(profile?.username||'user').trim()||'user')}
function initials(u){const t=String(u?.display_name||u?.username||'?').trim();return (t[0]||'?').toUpperCase()}
function secureAssetUrl(url){const s=String(url||'');const own='http://network-notes.duckdns.org/';if(s.startsWith(own))return '/'+s.slice(own.length);return s}
function avatarHtml(u,cls=''){const c='avatar'+(cls?' '+cls:'');const src=secureAssetUrl(u?.avatar_url||'');return src?'<img class="'+c+'" src="'+escapeHtml(src)+'" alt="" referrerpolicy="same-origin">':'<span class="'+c+'">'+escapeHtml(initials(u))+'</span>'}
function updateProfileUi(){
  const guest=isGuest(),local=!!profile?.local_mode;
  $('profileHandle').textContent=local?'Local':(guest?'ゲスト':profileUsername());
  $('profileAvatar').innerHTML=local?'<span class="avatar small">L</span>':avatarHtml(profile,'small');
  $('profileBtn').title=local?'Localワークスペース（アカウント不要）':(guest?'ゲストとして閲覧中':((profile.display_name?profile.display_name+' · ':'')+'@'+profileUsername()));
  $('logoutBtn').style.display=(guest||local)?'none':'inline-block';
  const adminOpt=$('adminNavOption');if(adminOpt)adminOpt.hidden=guest||profile?.local_mode||!['owner','moderator'].includes(profile?.role);
  const dl=$('downloadBtn');if(dl)dl.textContent=profile?.local_mode?'Web版':'Local';
  const menu=$('mainNavMenu');if(menu){menu.querySelectorAll('[data-main-nav]').forEach(b=>{const v=b.dataset.mainNav;b.hidden=(['communities','dm'].includes(v)&&!!profile?.local_mode)||(v==='admin'&&(guest||profile?.local_mode||!['owner','moderator'].includes(profile?.role)))});const active=menu.querySelector('.active');if(active?.hidden)setTopNav('')}
  document.querySelectorAll('.localOnlyRelation').forEach(o=>o.hidden=!profile?.local_mode);
  const selectBtn=$('nodeSelectBtn'),deleteBtn=$('nodeDeleteBtn');if(selectBtn)selectBtn.style.display=guest?'none':'inline-block';if(deleteBtn&&guest)deleteBtn.style.display='none';
  updateFileTitle();
}
function updateFileTitle(){
  if(!currentData)return;
  $('fileTitle').textContent=currentData.title;
  $('fileTitle').title=currentData.name||current;
}
function updateAuthorBar(){
  if(!currentData)return;
  const au=currentData.author||profile;
  $('noteAuthorAvatar').innerHTML=avatarHtml(au);
  $('noteAuthorName').textContent=au.display_name||au.username||'';
  $('noteAuthorHandle').textContent='@'+(au.username||'');
  $('likeBtn').textContent=(currentData.liked?'♥ ':'♡ ')+(currentData.like_count||0);
  $('likeBtn').style.display=currentData.is_index?'none':'inline-block';
  const report=$('reportNoteBtn');if(report)report.style.display=(!currentData.can_edit&&!currentData.is_index)?'inline-block':'none';
}
function collapseVimSelection(cm,pos=null){
  if(!cm)return null;
  try{
    const head=pos||cm.getCursor('head')||cm.getCursor();
    const line=Math.max(0,Math.min(Number(head.line)||0,Math.max(0,cm.lineCount()-1)));
    const text=cm.getLine(line)||'';
    const caret={line,ch:Math.max(0,Math.min(Number(head.ch)||0,text.length))};
    cm.operation(()=>cm.setSelection(caret,caret,{scroll:false}));
    const sel=window.getSelection?.();if(sel&&sel.rangeCount)sel.removeAllRanges();
    return caret;
  }catch(_){return null}
}
function anyImeComposing(){return vimImeComposing.has(editor)||vimImeComposing.has(bodyEditor)}
function resolveImeIdleWaiters(){if(anyImeComposing())return;while(imeIdleWaiters.length){try{imeIdleWaiters.shift()()}catch(_){}}}
function waitForImeIdle(timeout=2500){
  if(!anyImeComposing())return Promise.resolve();
  return new Promise(resolve=>{let done=false;const finish=()=>{if(done)return;done=true;resolve()};imeIdleWaiters.push(finish);setTimeout(finish,timeout)});
}
function bindVimIme(cm){
  const input=cm.getInputField?.();if(!input)return;
  input.addEventListener('compositionstart',()=>{
    vimImeComposing.add(cm);
    // A timer started by the preceding keystroke must not save a half-finished
    // Japanese conversion string. Saving resumes after compositionend.
    if(autosaveTimer){clearTimeout(autosaveTimer);autosaveTimer=null}
    if(liveLinkRefreshTimer){clearTimeout(liveLinkRefreshTimer);liveLinkRefreshTimer=null}
  });
  input.addEventListener('compositionend',()=>{
    vimImeComposing.delete(cm);
    vimImeEndedAt.set(cm,performance.now());
    // Let Chromium and the IME finish their final selection update before any
    // autosave/marking work runs. Never collapse the conversion range here.
    setTimeout(()=>{
      try{
        if(cm===editor)refreshSourceFrontmatterStyle();
        if(!loadingDoc&&cm===editor&&mode==='source'){dirty=true;queueAutosave(550)}
        resolveImeIdleWaiters();
      }catch(_){resolveImeIdleWaiters()}
    },0);
  });
  // NORMAL mode must never accept native text insertion (including IME,
  // paste or drag/drop). Vim editing commands are programmatic and do not
  // depend on beforeinput, so this does not block dd/x/p/etc.
  input.addEventListener('beforeinput',e=>{
    if(vimInputMode==='normal')e.preventDefault();
  });
  input.addEventListener('paste',e=>{if(vimInputMode==='normal')e.preventDefault()});
  input.addEventListener('drop',e=>{if(vimInputMode==='normal')e.preventDefault()});
}
function applyEditorReadOnly(){
  const editable=!!currentData?.can_edit;
  // Other users' notes remain fully navigable/selectable; only mutation is blocked.
  // `true` keeps a visible cursor, unlike CodeMirror's `nocursor`.
  const ro=editable?false:true;
  editor.setOption('readOnly',ro);
  bodyEditor.setOption('readOnly',ro);
}
function updateVimUi(){
  const b=$('vimIndicator');if(!b)return;
  const available=!!currentData&&mode==='source';
  b.style.display=available?'inline-block':'none';
  const label=vimInputMode!=='normal'?'INSERT':(vimVisual==='line'?'V-LINE':vimVisual==='char'?'VISUAL':'NORMAL');
  b.textContent='VIM '+label;
  b.classList.toggle('normal',vimInputMode==='normal'&&!vimVisual);
  b.classList.toggle('visual',vimInputMode==='normal'&&!!vimVisual);
  b.classList.toggle('insert',vimInputMode!=='normal');
}
function bodyCursorMappedToSource(){
  const cur=bodyEditor.getCursor(),needle=bodyEditor.getLine(cur.line)||'';
  const bodyLines=bodyEditor.getValue().split('\n'),rawLines=editor.getValue().split('\n');
  let nth=0;for(let i=0;i<=cur.line;i++)if(bodyLines[i]===needle)nth++;
  let seen=0;
  for(let i=0;i<rawLines.length;i++){
    if(rawLines[i]!==needle)continue;
    seen++;if(seen===nth)return{line:i,ch:Math.min(cur.ch,rawLines[i].length)};
  }
  return{line:Math.min(cur.line,Math.max(0,rawLines.length-1)),ch:cur.ch};
}
function clearVimNormalLinkMarks(){
  const marks=vimNormalLinkMarks;vimNormalLinkMarks=[];
  for(const m of marks){try{m.clear()}catch(_){}}
}
function refreshVimNormalLinks(){
  clearVimNormalLinkMarks();
  if(vimInputMode!=='normal'||mode!=='source')return;
  const cm=editor;
  const re=/\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+"label-fixed")?\)/g;
  for(let lineNo=0;lineNo<cm.lineCount();lineNo++){
    const line=cm.getLine(lineNo)||'';re.lastIndex=0;let m;
    while((m=re.exec(line))){
      const start=m.index,end=start+m[0].length,labelStart=start+1,labelEnd=labelStart+m[1].length;
      vimNormalLinkMarks.push(cm.markText({line:lineNo,ch:start},{line:lineNo,ch:labelStart},{collapsed:true,atomic:true}));
      vimNormalLinkMarks.push(cm.markText({line:lineNo,ch:labelEnd},{line:lineNo,ch:end},{collapsed:true,atomic:true}));
      vimNormalLinkMarks.push(cm.markText({line:lineNo,ch:labelStart},{line:lineNo,ch:labelEnd},{className:'cm-live-link'}));
    }
  }
}
let vimScrollRaf=0;
function vimEnsureCursorVisible(cm,center=false){
  if(vimScrollRaf)cancelAnimationFrame(vimScrollRaf);
  // Use CodeMirror's scroll API rather than mutating its DOM scroller. Direct
  // DOM scrolling can be overwritten by CodeMirror's cached scroll position,
  // which made distant Tab link jumps appear not to move the viewport.
  const ensure=()=>{
    vimScrollRaf=0;
    try{
      const cur=cm.getCursor(),info=cm.getScrollInfo(),c=cm.charCoords(cur,'local');
      const topSafe=58,bottomSafe=72;
      let target=null;
      if(center)target=Math.max(0,(c.top+c.bottom-info.clientHeight)/2);
      else if(c.top<info.top+topSafe)target=Math.max(0,c.top-topSafe);
      else if(c.bottom>info.top+info.clientHeight-bottomSafe)target=Math.max(0,c.bottom-info.clientHeight+bottomSafe);
      if(target===null||Math.abs(target-info.top)<2)return;
      cm.scrollTo(null,target);
    }catch(_){}
  };
  ensure();
  // Collapsed link marks and wrapped lines can settle after the cursor moves.
  // Recalculate on two frames so the final rendered caret remains centered.
  vimScrollRaf=requestAnimationFrame(()=>{
    ensure();
    vimScrollRaf=requestAnimationFrame(ensure);
  });
}
function vimMove(cm,command){cm.execCommand(command);vimEnsureCursorVisible(cm)}
function setVimInputMode(next,cm=null){
  const previousVimInputMode=vimInputMode;
  const active=cm||editor;
  const wantsNormal=next==='normal';
  if(wantsNormal&&vimImeComposing.has(active)){
    // A mode switch while the IME owns the selection is unsafe. The first
    // Escape is allowed to finish/cancel conversion; the next exits INSERT.
    return;
  }
  const normalCaret=wantsNormal?collapseVimSelection(active,active?.getCursor?.('head')):null;
  vimInputMode=wantsNormal?'normal':'insert';vimVisual=null;vimVisualAnchor=null;vimPendingCommand='';
  if(previousVimInputMode==='insert'&&vimInputMode==='normal'&&mode==='source'&&relationSyncPending){
    flushAutosave(true).catch(console.error);
  }
  applyEditorReadOnly();updateVimUi();

  if(vimInputMode==='normal'&&mode!=='source'){
    clearLiveLinkMarks();clearVimNormalLinkMarks();
    switchMode('source',{enterInsert:false});
    return;
  }

  if(vimInputMode==='normal'){
    clearLiveLinkMarks();
    refreshVimNormalLinks();
  }else{
    clearVimNormalLinkMarks();
    clearLiveLinkMarks();
  }
  if(currentData&&mode==='source'){try{
    active.focus();
    if(vimInputMode==='normal'&&normalCaret){
      // CodeMirror and Chromium can each perform one late selection update
      // after IME/read-mode transitions. Collapse on two animation frames so
      // NORMAL always ends with one caret, never a selected Japanese range.
      collapseVimSelection(active,normalCaret);
      requestAnimationFrame(()=>{
        collapseVimSelection(active,normalCaret);
        requestAnimationFrame(()=>{collapseVimSelection(active,normalCaret);vimEnsureCursorVisible(active)});
      });
    }else vimEnsureCursorVisible(active);
  }catch(_){} }
}
function updateEditPermissions(){
  const editable=!!currentData?.can_edit;
  applyEditorReadOnly();
  updateViewModeToggle();
  $('contextActionBtn').style.display=editable?'inline-block':'none';
  $('shareCommunityBtn').style.display=(editable&&!currentData?.is_index&&!currentData?.is_topic&&!profile?.local_mode)?'inline-block':'none';
  $('uploadToggleWrap').style.display='none';
  $('publicVersionBtn').style.display=(editable&&profile?.local_mode&&!currentData?.is_index)?'inline-block':'none';
  $('taskBtn').style.display=editable?'inline-block':'none';$('tableBtn').style.display=editable?'inline-block':'none';
  if(profile?.local_mode&&currentData)$('uploadToggle').checked=currentData.upload_enabled!==false;
  updateVimUi();
}
async function refreshProfile(){profile=await api('/api/profile');updateProfileUi()}
function escapeHtml(s){return String(s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]||c));}
function stripAuto(s){return String(s||'').replace(/\n?<!-- edges:auto:start -->[\s\S]*?<!-- edges:auto:end -->\n?/g,'\n').replace(/\n+$/,'')+'\n';}
const editor=CodeMirror.fromTextArea($('source'),{
  mode:{name:'markdown',highlightFormatting:true},
  lineNumbers:false,
  lineWrapping:true,
  styleActiveLine:false,
  indentUnit:2,
  tabSize:2,
  extraKeys:{
    'Enter':'newlineAndIndentContinueMarkdownList',
    'Ctrl-S':()=>flushAutosave(true).catch(console.error),
    'Cmd-S':()=>flushAutosave(true).catch(console.error)
  }
});
const bodyEditor=CodeMirror.fromTextArea($('bodySource'),{
  mode:{name:'markdown',highlightFormatting:true},
  lineNumbers:false,
  lineWrapping:true,
  styleActiveLine:false,
  indentUnit:2,
  tabSize:2,
  viewportMargin:Infinity,
  extraKeys:{
    'Enter':'newlineAndIndentContinueMarkdownList',
    'Ctrl-S':()=>flushAutosave(true).catch(console.error),
    'Cmd-S':()=>flushAutosave(true).catch(console.error)
  }
});
// Keep the body editor as ordinary document flow: the page scrolls, not a nested CodeMirror pane.
bodyEditor.setSize(null,'auto');
bindVimIme(editor);bindVimIme(bodyEditor);
let sourceFrontmatterStyledLines=[];
function refreshSourceFrontmatterStyle(){
  if(typeof editor!=='undefined'&&vimImeComposing.has(editor))return;
  for(const line of sourceFrontmatterStyledLines){
    try{editor.removeLineClass(line,'wrap','nnFrontmatterLine')}catch(_){}
  }
  sourceFrontmatterStyledLines=[];
  if(editor.lineCount()<1||String(editor.getLine(0)||'').trim()!=='---')return;
  let closing=-1;
  const limit=Math.min(editor.lineCount(),80);
  for(let i=1;i<limit;i++){if(String(editor.getLine(i)||'').trim()==='---'){closing=i;break}}
  if(closing<0)return;
  for(let i=0;i<=closing;i++){editor.addLineClass(i,'wrap','nnFrontmatterLine');sourceFrontmatterStyledLines.push(i)}
}
let liveLinkMarks=[];
let liveLinkRefreshTimer=null;
let activeLiveLinkKey=null;
function clearLiveLinkMarks(){
  const marks=liveLinkMarks;liveLinkMarks=[];
  for(const m of marks){try{m.clear()}catch(_){}}
}
function liveLinkKeyAtCursor(){
  const cur=bodyEditor.getCursor();
  const info=markdownLinkAt(bodyEditor.getLine(cur.line)||'',cur.ch);
  return info?cur.line+':'+info.start+':'+info.end:null;
}
function scheduleLiveLinkRefresh(delay=0){
  if(liveLinkRefreshTimer)clearTimeout(liveLinkRefreshTimer);
  liveLinkRefreshTimer=setTimeout(refreshLiveLinks,delay);
}
function refreshLiveLinks(){
  clearLiveLinkMarks();
  activeLiveLinkKey=null;
  // INSERT is raw: [表示名](file.md) remains fully visible.
  // NORMAL uses Vim marks so only 表示名 is visible.
  if(vimInputMode==='normal')refreshVimNormalLinks();
}
bodyEditor.on('change',()=>{
  if(loadingDoc)return;
  editRevision++;dirty=true;
  if(!vimImeComposing.has(bodyEditor))queueAutosave(550);
  queueTopicWidgets();
  // Existing CodeMirror marks track edits automatically. Re-scan only after
  // a short idle period so normal typing/IME input is never interrupted.
  if(!vimImeComposing.has(bodyEditor))scheduleLiveLinkRefresh(350);
});
editor.on('beforeChange',(cm,change)=>{
  if(loadingDoc||!sourceAutoEdgeLines.size)return;
  for(let line=change.from.line;line<=change.to.line;line++){
    if(sourceAutoEdgeLines.has(line)){
      change.cancel();status('他のユーザーが追加した関係はボックス側から操作してください');return;
    }
  }
});
editor.on('change',()=>{
  const composing=vimImeComposing.has(editor);
  if(!composing){refreshSourceFrontmatterStyle();refreshSourceAutoEdgeStyle()}
  if(loadingDoc||mode!=='source')return;
  editRevision++;dirty=true;
  // Child/backlink rebuilding is expensive and used to run after every body
  // keystroke. Only title/relation changes need a structural commit.
  const sig=structureSignatureFromText(editor.getValue());
  if(sig!==currentStructureSignature){currentStructureSignature=sig;relationSyncPending=true}
  // Never run save/visual maintenance in the middle of an IME composition.
  // compositionend schedules the normal draft save after the IME has settled.
  if(!composing)queueAutosave(550);
});
function markdownLinkAt(line,ch){
  const re=/\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+"(label-fixed)")?\)/g;let m;
  while((m=re.exec(line||''))){
    if(ch>=m.index&&ch<=m.index+m[0].length){
      return{label:m[1].replace(/\\([\[\]\\])/g,'$1'),file:decodeURIComponent(m[2].split('/').pop()),fixed:m[3]==='label-fixed',start:m.index,end:m.index+m[0].length};
    }
  }
  return null;
}
// Obsidian-like link behavior in edit mode:
// if the text cursor is already inside this link, clicking edits it;
// otherwise a normal click follows the link.
bodyEditor.on('cursorActivity',()=>{
  const key=liveLinkKeyAtCursor();
  if(key!==activeLiveLinkKey)scheduleLiveLinkRefresh(0);
});
bodyEditor.on('focus',()=>scheduleLiveLinkRefresh(0));
bodyEditor.on('blur',()=>scheduleLiveLinkRefresh(80));
// Capture the pointer before CodeMirror moves the caret.  Otherwise the
// click itself makes the link look like it was already being edited.
bodyEditor.getWrapperElement().addEventListener('mousedown',e=>{
  if(e.button!==0)return;

  // Follow a link only when the pointer is actually on the visible blue
  // link label.  coordsChar() alone is intentionally not enough here:
  // collapsed Markdown syntax can make a click in the whitespace beside a
  // link resolve to a character position *inside* the raw [label](file.md).
  // In that case CodeMirror must receive the click normally so it can move
  // the caret to the requested position.
  const linkVisual=e.target?.closest?.('.cm-live-link');
  if(!linkVisual||!bodyEditor.getWrapperElement().contains(linkVisual))return;

  const pos=bodyEditor.coordsChar({left:e.clientX,top:e.clientY},'window');
  const clicked=markdownLinkAt(bodyEditor.getLine(pos.line)||'',pos.ch);
  if(!clicked)return;

  // IMPORTANT: this is the caret position *before* the click because this
  // handler runs in the capture phase.  If the caret was already inside the
  // same Markdown link, let CodeMirror handle the click normally so the raw
  // [label](file.md) stays editable.  Otherwise follow the link.
  const cur=bodyEditor.getCursor();
  const active=(cur.line===pos.line)?markdownLinkAt(bodyEditor.getLine(cur.line)||'',cur.ch):null;
  const editingSameLink=!!(active&&active.start===clicked.start&&active.end===clicked.end);
  if(editingSameLink)return;

  e.preventDefault();
  e.stopPropagation();
  if(e.stopImmediatePropagation)e.stopImmediatePropagation();
  openFile(clicked.file).catch(console.error);
},true);

function hideEditorContextMenu(){$('editorContextMenu').classList.remove('open')}
function escapeMarkdownLabel(s){return String(s||'').replace(/([\\\[\]])/g,'\\$1')}
function attachLinkifyContextMenu(cm){
  cm.getWrapperElement().addEventListener('contextmenu',e=>{
    if(!currentData?.can_edit)return;
    e.preventDefault();
    imageInsertEditor=cm;
    if(cm.somethingSelected())pendingLinkifySelection={cm,from:cm.getCursor('from'),to:cm.getCursor('to'),text:cm.getSelection()};
    else{
      pendingLinkifySelection=null;
      try{cm.setCursor(cm.coordsChar({left:e.clientX,top:e.clientY},'window'))}catch(_){}
    }
    $('linkifyMenuItem').style.display=pendingLinkifySelection?.text?'block':'none';
    const menu=$('editorContextMenu');
    menu.style.left=Math.min(e.clientX,window.innerWidth-170)+'px';
    menu.style.top=Math.min(e.clientY,window.innerHeight-90)+'px';
    menu.classList.add('open');
  });
}
attachLinkifyContextMenu(bodyEditor);
attachLinkifyContextMenu(editor);
document.addEventListener('mousedown',e=>{if(!e.target.closest?.('#editorContextMenu'))hideEditorContextMenu()});
window.addEventListener('blur',hideEditorContextMenu);
$('imageMenuItem').onclick=()=>{hideEditorContextMenu();if(currentData?.can_edit)$('imageInput').click()};

async function loadLinkifyTargets(){
  const d=await api('/api/link-targets');
  linkifyTargets=d.targets||[];
  renderLinkifyTargets();
}
function renderLinkifyTargets(){
  const q=String($('linkifySearch').value||'').trim().toLocaleLowerCase('ja');
  const sel=$('linkifyTarget');sel.innerHTML='';
  const items=linkifyTargets.filter(x=>!q||String(x.title||'').toLocaleLowerCase('ja').includes(q)||String(x.author?.username||'').toLocaleLowerCase('ja').includes(q)||String(x.author?.display_name||'').toLocaleLowerCase('ja').includes(q));
  for(const x of items){const o=document.createElement('option');o.value=x.file;o.textContent=(x.title||x.file)+' · @'+(x.author?.username||'');sel.appendChild(o)}
  $('linkifySubmit').disabled=!items.length;
}
function applyFixedLinkToSelection(target,message='リンク化しました'){
  const sel=pendingLinkifySelection;if(!sel||!target)return;
  const md='['+escapeMarkdownLabel(sel.text)+']('+target+' "label-fixed")';
  const cm=sel.cm||bodyEditor;
  cm.replaceRange(md,sel.from,sel.to,'linkify');
  cm.setCursor(cm.posFromIndex(cm.indexFromPos(sel.from)+md.length));
  pendingLinkifySelection=null;$('linkifyDialog').close();queueAutosave(100);scheduleLiveLinkRefresh(0);status(message);
}
$('linkifyMenuItem').onclick=async()=>{
  hideEditorContextMenu();
  if(!pendingLinkifySelection?.text)return;
  $('linkifySelected').textContent=pendingLinkifySelection.text;
  $('linkifySearch').value='';
  $('linkifyNewTitle').value=pendingLinkifySelection.text.trim().replace(/\s+/g,' ').slice(0,160);
  $('linkifyTarget').innerHTML='<option>読み込み中...</option>';
  $('linkifyDialog').showModal();
  try{await loadLinkifyTargets();setTimeout(()=>$('linkifySearch').focus(),0)}catch(e){status(e.message);$('linkifyDialog').close()}
};
$('linkifySearch').addEventListener('input',renderLinkifyTargets);
$('linkifyForm').addEventListener('submit',e=>{
  e.preventDefault();
  const target=$('linkifyTarget').value;if(!pendingLinkifySelection||!target)return;
  applyFixedLinkToSelection(target);
});
$('linkifyNewBtn').onclick=async()=>{
  if(!pendingLinkifySelection)return;
  const title=$('linkifyNewTitle').value.trim();if(!title){status('新しいノートのタイトルを入力してください');$('linkifyNewTitle').focus();return}
  try{
    const d=await api('/api/new-linked',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})});
    await refreshFiles();
    applyFixedLinkToSelection(d.file,'新しいノートを作成してリンク化しました');
  }catch(e){status(e.message)}
};
$('linkifyDialog').addEventListener('close',()=>{pendingLinkifySelection=null});

async function copyCurrentNoteLink(){
  if(!currentData||!current)return;
  const md='['+escapeMarkdownLabel(currentData.title||current)+']('+current+')';
  try{await navigator.clipboard.writeText(md)}catch(_){const ta=document.createElement('textarea');ta.value=md;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove()}
  status('ノートのリンクをコピーしました');
}
$('copyLinkBtn').onclick=()=>copyCurrentNoteLink().catch(e=>status(e.message));

function splitYamlFrontmatter(text){
  const normalized=String(text||'').replace(/\r\n/g,'\n');
  const lines=normalized.split('\n');
  if(!lines.length||lines[0].trim()!=='---')return{frontmatter:'',body:normalized};
  for(let i=1;i<lines.length;i++){
    if(lines[i].trim()==='---')return{frontmatter:lines.slice(0,i+1).join('\n'),body:lines.slice(i+1).join('\n')};
  }
  return{frontmatter:'',body:normalized};
}
function formatLocalDateTime(value){
  if(value===null||value===undefined||value==='')return'';
  let d;
  if(typeof value==='number')d=new Date(value*1000);
  else{
    let raw=String(value).trim();
    // SQLite CURRENT_TIMESTAMP is UTC despite having no suffix.
    if(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(raw))raw=raw.replace(' ','T')+'Z';
    d=new Date(raw);
  }
  if(Number.isNaN(d.getTime()))return String(value);
  return new Intl.DateTimeFormat(undefined,{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(d);
}
function creatorMetadataLine(text){
  const body=splitYamlFrontmatter(text).body;
  const lines=String(body||'').replace(/\r\n/g,'\n').split('\n');
  for(let i=0;i<Math.min(lines.length,12);i++){
    const line=lines[i];
    if(!line.trim())continue;
    const m=line.match(/^\s*creator::\s*(.+?)\s*$/i);
    if(m)return 'creator::'+m[1].trim();
    // Creator metadata is kept at the top of the note. Once real note
    // content starts, do not interpret later prose as metadata.
    if(/^#\s+/.test(line)||relationLineInfo(line)||/^\s*---\s*$/.test(line))break;
  }
  return '';
}
function groupEdgeMarkdown(edges){
  const groups=[];const by=new Map();
  for(const e of (edges||[])){
    const rel=String(e.relation||'関連').trim()||'関連';
    if(!by.has(rel)){const g={relation:rel,items:[]};by.set(rel,g);groups.push(g)}
    by.get(rel).items.push(e);
  }
  return groups.map(g=>g.items.map(e=>g.relation+'::['+escapeMarkdownLabel(e.title||e.file)+']('+e.file+')').join('\n')).join('\n');
}
function externalEdgeSourceLines(edges,direction){
  const list=(edges||[]).filter(e=>e&&e.edge_kind==='external');
  if(!list.length)return '';
  const seen=new Set(), lines=[];
  for(const e of list){
    const rel=String(e.relation||'関連').trim()||'関連';
    const file=String(e.file||'').trim();if(!file)continue;
    const key=normRel(rel)+'\u0000'+file+'\u0000'+String(e.edge_id||'');if(seen.has(key))continue;seen.add(key);
    const who=String(e.edge_creator_username||'').trim();
    lines.push(rel+'::['+escapeMarkdownLabel(e.title||file)+']('+file+')'+(who?' <!-- 追加 @'+who+' -->':''));
  }
  if(!lines.length)return '';
  const label=direction==='outgoing'?'Parent：他のユーザーが追加した関係':'Child：他のユーザーが追加した関係';
  return '<!-- edges:auto:start -->\n<!-- '+label+'（ボックスと自動同期・ソースからは編集不可） -->\n'+lines.join('\n')+'\n<!-- edges:auto:end -->';
}
function splitDirectionSourceForProjection(raw){
  const text=String(raw||'').replace(/\r\n/g,'\n').replace(/\n+$/,'');
  const lines=text.split('\n');
  let start=0;
  if(lines[0]?.trim()==='---'){for(let i=1;i<lines.length;i++){if(lines[i].trim()==='---'){start=i+1;break}}}
  for(let i=start;i<lines.length;i++){if(lines[i].trim()==='---')return{parent:lines.slice(0,i).join('\n').replace(/\n+$/,''),divider:'---',child:lines.slice(i+1).join('\n').replace(/^\n+|\n+$/g,'')}}
  return{parent:text,divider:'---',child:''};
}
function insertAutoAfterLeadingRelations(segment,block,{title=false}={}){
  if(!block)return String(segment||'').replace(/\n+$/,'');
  const lines=String(segment||'').replace(/\n+$/,'').split('\n');
  let i=0;
  if(lines[0]?.trim()==='---'){
    for(let j=1;j<lines.length;j++){if(lines[j].trim()==='---'){i=j+1;break}}
  }
  while(i<lines.length&&!lines[i].trim())i++;
  if(title&&i<lines.length&&/^#\s+/.test(lines[i]))i++;
  let lastRelationEnd=i, sawRelation=false;
  while(i<lines.length){
    if(!lines[i].trim()){i++;if(sawRelation)lastRelationEnd=i;continue}
    if(relationLineInfo(lines[i])){sawRelation=true;i++;lastRelationEnd=i;continue}
    break;
  }
  const at=sawRelation?lastRelationEnd:i;
  const before=lines.slice(0,at).join('\n').replace(/\n+$/,'');
  const after=lines.slice(at).join('\n').replace(/^\n+/, '');
  return [before,block,after].filter(Boolean).join('\n\n');
}
function sourceProjectionWithBoxEdges(content){
  const raw=stripAuto(content).replace(/\n+$/,'');
  const outAuto=externalEdgeSourceLines(currentData?.outgoing||[],'outgoing');
  const inAuto=externalEdgeSourceLines(currentData?.incoming||[],'incoming');
  if(!outAuto&&!inAuto)return raw+'\n';
  const parts=splitDirectionSourceForProjection(raw);
  let parent=insertAutoAfterLeadingRelations(parts.parent,outAuto,{title:true});
  let child=insertAutoAfterLeadingRelations(parts.child,inAuto,{title:false});
  let result=parent.replace(/\n+$/,'')+'\n\n'+parts.divider+'\n';
  if(child.trim())result+='\n'+child.replace(/^\n+|\n+$/g,'')+'\n';
  return result;
}
let sourceAutoEdgeLines=new Set();
function refreshSourceAutoEdgeStyle(){
  sourceAutoEdgeLines.forEach(line=>{try{editor.removeLineClass(line,'wrap','nnAutoEdgeLine')}catch(_){}});
  sourceAutoEdgeLines=new Set();
  let inside=false;
  for(let i=0;i<editor.lineCount();i++){
    const t=String(editor.getLine(i)||'').trim();
    if(t==='<!-- edges:auto:start -->')inside=true;
    if(inside){sourceAutoEdgeLines.add(i);try{editor.addLineClass(i,'wrap','nnAutoEdgeLine')}catch(_){}}
    if(t==='<!-- edges:auto:end -->')inside=false;
  }
}
function splitLeadingTitle(body){
  const text=String(body||'').replace(/\r\n/g,'\n').trim();
  if(!text)return{title:'',rest:''};
  const lines=text.split('\n');
  if(/^#\s+/.test(lines[0]))return{title:lines[0].trimEnd(),rest:lines.slice(1).join('\n').trim()};
  return{title:'',rest:text};
}
function composeStructuredMarkdown(){
  const body=String(bodyEditor.getValue()||'').replace(/\r\n/g,'\n').trim();
  const lead=splitLeadingTitle(body);
  const parent=groupEdgeMarkdown(currentData?.outgoing||[]).trim();
  const child=groupEdgeMarkdown(currentData?.incoming||[]).trim();
  const before=[];
  if(lead.title)before.push(lead.title);
  if(parent)before.push(parent);
  if(lead.rest)before.push(lead.rest);
  let out=before.join('\n\n').trimEnd();
  out+=(out?'\n\n':'')+'---\n';
  if(child)out+='\n'+child+'\n';
  const rawSource=editor.getValue();
  const fm=splitYamlFrontmatter(rawSource).frontmatter.trim();
  const creator=creatorMetadataLine(rawSource);
  const metadata=[fm,creator].filter(Boolean).join('\n\n');
  if(metadata)out=metadata+'\n\n'+out;
  return stripAuto(out);
}
function structureSignatureFromText(text){
  const parts=splitDirectionSourceForProjection(stripAuto(String(text||'')));
  const lines=String(parts.parent||'').split('\n');
  let title='';const edges=[];
  for(const line of lines){
    const h=headingInfo(line);if(!title&&h&&h.level===1)title=h.text.trim();
    const e=relationLineInfo(line);if(e)edges.push(normRel(e.relation)+'\u0000'+e.file);
  }
  return title+'\u0001'+edges.join('\u0002');
}
function setEditorsFromRaw(content,{keepBody=false}={}){
  const raw=stripAuto(content);
  const projected=sourceProjectionWithBoxEdges(raw);
  relationSyncPending=false;
  // A document swap invalidates any in-progress visual selection.
  vimVisual=null;vimVisualAnchor=null;
  currentStructureSignature=structureSignatureFromText(raw);
  loadingDoc=true;clearLiveLinkMarks();editor.setValue(projected);refreshSourceFrontmatterStyle();refreshSourceAutoEdgeStyle();
  if(!keepBody)bodyEditor.setValue(bodyWithoutPureEdgeSections(raw));
  bodyEditor.setSize(null,'auto');
  loadingDoc=false;scheduleLiveLinkRefresh(0);if(vimInputMode==='normal'&&mode==='source')setTimeout(refreshVimNormalLinks,0);
}
function editorText(){return stripAuto(editor.getValue());}
function normRel(x){return String(x||'').replace(/\s+/g,'').toLowerCase()}
function relIs(x,name){
  const n=normRel(x), target=normRel(name);
  const category=['カテゴリー','トピック','topic','topics','分類'];
  const classified=['分類した','下位カテゴリー','subcategory','subtopic'];
  const support=['賛成した','賛成','肯定','賛同','支持','support','supports'];
  const oppose=['反対した','反対','反論','oppose','opposes','objection'];
  const supplement=['補足した','補足'];
  const related=['関連した','関連'];
  const question=['質問した','質問'];
  const answer=['回答した','回答'];
  const summary=['まとめた','まとめ'];
  if(target==='カテゴリー'||target==='トピック')return category.includes(n);
  if(target==='分類した'||target==='下位カテゴリー')return classified.includes(n);
  if(target==='賛成した'||target==='賛成'||target==='肯定')return support.includes(n);
  if(target==='反対した'||target==='反対'||target==='反論')return oppose.includes(n);
  if(target==='補足した'||target==='補足')return supplement.includes(n);
  if(target==='関連した'||target==='関連')return related.includes(n);
  if(target==='質問した'||target==='質問')return question.includes(n);
  if(target==='回答した'||target==='回答')return answer.includes(n);
  if(target==='まとめた'||target==='まとめ')return summary.includes(n);
  if(target==='ノート')return ['ノート','note','notes'].includes(n);
  return n===target;
}
function outgoingOf(data,relation){return (data?.outgoing||[]).filter(e=>relIs(e.relation,relation))}
function updateContextAction(){
  const b=$('contextActionBtn');if(!b)return;
  b.textContent='移動・分類';b.title='Childリンクをカテゴリーへ移動/追加（Vim: em）';
  b.style.display=currentData?'inline-block':'none';
  const del=$('deleteCurrentBtn');if(del)del.style.display=(currentData?.can_edit&&!currentData?.is_index)?'inline-block':'none';
}
function metric(file){return currentData?.metrics?.[file]||{node_count:0,support_count:0,oppose_count:0,created_key:''}}
function authorFor(file){return currentData?.authors?.[file]||{username:'legacy',display_name:'Legacy',avatar_url:''}}
function authorMiniHtml(u){return '<span class="previewAuthor">'+avatarHtml(u,'small')+'<span class="previewAuthorName">'+escapeHtml(u.display_name||u.username||'')+'</span></span>'}
function headingInfo(line){const m=line.match(/^(#{1,6})\s+(.+?)\s*$/);return m?{level:m[1].length,text:m[2]}:null}
function linkInfo(line){const m=line.match(/^\s*(?:[-*+]\s+)?\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+"label-fixed")?\)\s*$/);if(!m)return null;return{label:m[1].replace(/\\([\[\]\\])/g,'$1'),file:decodeURIComponent(m[2].split('/').pop())}}
function sortedLinks(items,kind){const a=[...items],k=x=>metric(x.file);if(kind==='name')a.sort((x,y)=>x.label.localeCompare(y.label,'ja'));else if(kind==='newest')a.sort((x,y)=>k(y).created_key.localeCompare(k(x).created_key));else if(kind==='oldest')a.sort((x,y)=>k(x).created_key.localeCompare(k(y).created_key));else if(kind==='nodes')a.sort((x,y)=>k(y).node_count-k(x).node_count);else if(kind==='support')a.sort((x,y)=>k(y).support_count-k(x).support_count);else if(kind==='oppose')a.sort((x,y)=>k(y).oppose_count-k(x).oppose_count);else if(kind==='topicRank')a.sort((x,y)=>(k(y).topic_score-k(x).topic_score)||(k(y).topic_use_count-k(x).topic_use_count)||(k(y).topic_appropriate-k(x).topic_appropriate)||x.label.localeCompare(y.label,'ja'));return a}
function inlinePreview(s){let x=escapeHtml(s);x=x.replace(/!\[([^\]]*)\]\((\/media\/[^)]+)\)/g,(_m,a,t)=>'<img class="inlineImage" src="'+t+'" alt="'+a+'">').replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*]+)\*/g,'<em>$1</em>').replace(/\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+(?:"label-fixed"|&quot;label-fixed&quot;))?\)/g,(_m,l,t)=>'<a href="#" data-file="'+escapeHtml(decodeURIComponent(t.split('/').pop()))+'">'+l.replace(/\\([\[\]\\])/g,'$1')+'</a>');return x}
function relationGroups(edges){
  const map=new Map();
  for(const e of (edges||[])){const k=String(e.relation||'関連').trim()||'関連';if(!map.has(k))map.set(k,[]);map.get(k).push({...e,label:e.title||e.file,file:e.file,relation:k,private:!!e.private})}
  return [...map.entries()];
}
function edgeKey(relation,file){return String(relation||'')+'\u0000'+String(file||'')}
function edgeStatsHtml(li,relation,direction){
  const m=metric(li.file),isTopic=relIs(relation,'トピック');
  if(direction==='outgoing'&&isTopic&&!currentData?.is_topic&&!currentData?.is_index&&!currentData?.can_edit){const r=topicEdgeRatingFor(li.file);return '適切 '+r.appropriate+'・不適切 '+r.inappropriate}
  if(direction==='outgoing'&&isTopic&&(currentData?.is_topic||currentData?.is_index))return '利用 '+m.topic_use_count;
  if(direction==='outgoing'&&!isTopic)return 'ノード '+m.node_count+'・肯定 '+m.support_count+'・反論 '+m.oppose_count;
  return '';
}
function canEditEdgeItem(direction,li){
  if(!profile?.id)return false;
  if(li?.edge_kind==='external')return Number(li?.edge_creator_id||0)===Number(profile.id);
  if(direction==='outgoing')return !!currentData?.can_edit;
  const a=authorFor(li.file);return Number(a?.id||0)===Number(profile.id);
}
function updateEdgeDeleteButton(direction,zone){
  const b=zone?.querySelector('[data-edge-delete="'+direction+'"]');if(!b)return;
  const n=selectedEdgeKeys[direction].size;b.textContent='削除'+(n?' ('+n+')':'');b.disabled=!n;
}
function toggleEdgeEdit(direction){edgeEditMode[direction]=!edgeEditMode[direction];selectedEdgeKeys[direction].clear();renderEditEdges();if(mode==='organize')renderOrganize()}
async function toggleEdgePrivacy(sourceNote,targetNote,makePrivate){
  try{
    await api('/api/note-publish-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:sourceNote,target:targetNote,private:makePrivate})});
    currentData=await api('/api/file?name='+encodeURIComponent(current)+'&voter='+encodeURIComponent(voterId));
    setEditorsFromRaw(currentData.content);dirty=false;renderEditEdges();if(mode==='organize')renderOrganize();status(makePrivate?'このリンクをWebでは非表示にします':'このリンクをWebにも表示します');
  }catch(e){status(e.message)}
}
async function deleteSelectedEdges(direction){
  const keys=[...selectedEdgeKeys[direction]];if(!keys.length)return;
  const edges=keys.map(k=>{const parts=k.split('\u0000');return{relation:parts[0],file:parts[1],edge_id:(parts[2]||'').startsWith('ext:')?Number(parts[2].slice(4)):0}});
  if(!confirm(edges.length+'件のエッジ関係を削除しますか？'))return;
  try{
    await flushAutosave();
    const d=await api('/api/edge-delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({direction,current,edges})});
    currentData=d;setEditorsFromRaw(d.content);dirty=false;selectedEdgeKeys[direction].clear();edgeEditMode[direction]=false;await refreshFiles();queueGraph();renderEditEdges();if(mode==='organize')renderOrganize();status(edges.length+'件のエッジを削除しました');
  }catch(err){status(err.message)}
}
function renderEdgeZone(root,direction){
  const outgoing=direction==='outgoing';
  if(outgoing&&currentData?.is_index)return;
  const zone=document.createElement('section');zone.className='edgeZone '+(outgoing?'outgoing':'incoming');
  const zh=document.createElement('div');zh.className='edgeZoneHeader';
  const zt=document.createElement('div');zt.className='edgeZoneTitle';zt.textContent=outgoing?'Parentとの関係':'Childとの関係';zh.appendChild(zt);
  const rawEdges=outgoing?(currentData?.outgoing||[]):(currentData?.incoming||[]);
  const edgeCreatorId=e=>Number(e?.edge_creator_id||authorFor(e.file)?.id||0);
  const ownEdge=e=>edgeCreatorId(e)===Number(profile?.id||0);
  const hasOther=rawEdges.some(e=>!ownEdge(e));
  if(hasOther){
    const lab=document.createElement('label');lab.className='edgeOtherToggle';
    const cb=document.createElement('input');cb.type='checkbox';cb.checked=showOtherEdgeNodes[direction];cb.tabIndex=-1;
    cb.onchange=()=>{showOtherEdgeNodes[direction]=cb.checked;localStorage.setItem(direction==='outgoing'?'nnShowOtherOutgoing':'nnShowOtherIncoming',cb.checked?'1':'0');renderEditEdges();if(mode==='organize')renderOrganize()};
    lab.appendChild(cb);lab.appendChild(document.createTextNode('他の人のノードを表示'));zh.appendChild(lab);
  }
  const canAdd=!!profile?.id;
  const editableCount=rawEdges.reduce((n,e)=>n+(canEditEdgeItem(direction,e)?1:0),0);
  if(!edgeEditMode[direction]){
    if(canAdd){const add=document.createElement('button');add.type='button';add.textContent='＋';add.title=outgoing?'Parentとの関係を追加（他人のノートにも追加可）':'Childとの関係を追加';add.onclick=()=>openEdgeDialog(direction);zh.appendChild(add)}
    if(editableCount){const edit=document.createElement('button');edit.type='button';edit.textContent='編集';edit.title='自分が作成した関係を編集';edit.onclick=()=>toggleEdgeEdit(direction);zh.appendChild(edit)}
    if(rawEdges.length){const all=document.createElement('button');all.type='button';all.className='edgeZoneExpandAll';all.textContent=edgeExpandAll[direction]?'折りたたむ':'すべて展開';all.onclick=()=>{edgeExpandAll[direction]=!edgeExpandAll[direction];if(!edgeExpandAll[direction])edgeExpandedGroups[direction].clear();renderEditEdges();if(mode==='organize')renderOrganize()};zh.appendChild(all)}
  }else{
    const del=document.createElement('button');del.type='button';del.className='edgeDeleteBtn';del.dataset.edgeDelete=direction;del.textContent='削除';del.disabled=true;del.onclick=()=>deleteSelectedEdges(direction);zh.appendChild(del);
    const done=document.createElement('button');done.type='button';done.textContent='完了';done.onclick=()=>toggleEdgeEdit(direction);zh.appendChild(done);
  }
  zone.appendChild(zh);
  const edges=rawEdges.filter(e=>showOtherEdgeNodes[direction]||ownEdge(e));
  const groups=relationGroups(edges);
  if(!groups.length){const em=document.createElement('div');em.className='edgeEmpty';em.textContent=rawEdges.length?'他の人のノードは非表示です':'エッジ関係はまだありません';zone.appendChild(em)}
  for(const [relation,itemsRaw] of groups){
    const block=document.createElement('section');block.className='previewSection edgeGroup';block.dataset.headingLevel='2';
    const head=document.createElement('div');head.className='sectionHead';const hd=document.createElement('div');hd.className='heading';hd.innerHTML='<h2>'+escapeHtml(relation)+'</h2>';head.appendChild(hd);
    const key=direction+'\u0000'+relation;
    if(itemsRaw.length>=2&&!edgeEditMode[direction]){const sel=document.createElement('select');sel.className='sectionSort';sel.tabIndex=-1;const isTopic=relIs(relation,'カテゴリー');const opts=isTopic?[['source','記載順'],['nodes','ノード数'],['newest','新しい順'],['oldest','古い順'],['name','名前順']]:[['source','記載順'],['nodes','ノード数'],['support','賛同数'],['oppose','否定数'],['newest','新しい順'],['oldest','古い順'],['name','名前順']];for(const [v,t] of opts){const o=document.createElement('option');o.value=v;o.textContent=t;sel.appendChild(o)}sel.value=sectionSort.get(key)||'source';sel.onchange=e=>{sectionSort.set(key,e.currentTarget.value);renderEditEdges();if(mode==='organize')renderOrganize()};head.appendChild(sel)}
    block.appendChild(head);
    const kind=sectionSort.get(key)||'source';
    const items=sortedLinks(itemsRaw,kind).sort((a,b)=>{if(outgoing){const ao=a.owner_set?0:1,bo=b.owner_set?0:1;if(ao!==bo)return ao-bo}return 0});
    const isExpanded=edgeEditMode[direction]||edgeExpandAll[direction]||edgeExpandedGroups[direction].has(key);
    const shown=isExpanded?items:items.slice(0,EDGE_GROUP_PREVIEW[direction]);
    const list=document.createElement('div');list.className='edgeGroupItems';
    let insertedOtherDivider=false;
    for(const li of shown){
      if(outgoing&&!li.owner_set&&!insertedOtherDivider&&shown.some(x=>x.owner_set)){const sep=document.createElement('div');sep.className='edgeOtherDivider';sep.textContent='その他の人が追加したParent';list.appendChild(sep);insertedOtherDivider=true}
      const editable=canEditEdgeItem(direction,li),d=document.createElement('div');d.className='previewLink'+(edgeEditMode[direction]?' edgeEditing':'')+(!editable&&edgeEditMode[direction]?' edgeNotEditable':'');
      const stats=edgeStatsHtml(li,relation,direction);
      if(edgeEditMode[direction]&&editable){const cb=document.createElement('input');cb.type='checkbox';cb.className='edgeSelect';cb.tabIndex=-1;const ek=edgeKey(relation,li.file)+(li.edge_kind==='external'?'\u0000ext:'+String(li.edge_id||''):'');cb.checked=selectedEdgeKeys[direction].has(ek);cb.onchange=()=>{if(cb.checked)selectedEdgeKeys[direction].add(ek);else selectedEdgeKeys[direction].delete(ek);updateEdgeDeleteButton(direction,zone)};d.appendChild(cb)}
      const content=document.createElement('div');content.style.display='contents';content.innerHTML=authorMiniHtml(authorFor(li.file))+'<a href="#" data-file="'+escapeHtml(li.file)+'">'+escapeHtml(li.label)+'</a>'+(li.edge_kind==='external'?'<span class="edgeOwnerBadge">追加 @'+escapeHtml(li.edge_creator_username||'')+'</span>':'')+(stats?'<span class="metrics">'+stats+'</span>':'');d.appendChild(content);
      if(profile?.local_mode&&editable&&li.edge_kind!=='external'){const lock=document.createElement('button');lock.type='button';lock.tabIndex=-1;lock.className='edgePrivacyBtn'+(li.private?' private':'');lock.textContent=li.private?'非公開':'公開';lock.title='この関係をWebに表示するか';const sourceNote=outgoing?current:li.file,targetNote=outgoing?li.file:current;lock.onclick=e=>{e.preventDefault();e.stopPropagation();toggleEdgePrivacy(sourceNote,targetNote,!li.private)};d.appendChild(lock)}
      list.appendChild(d);
    }
    block.appendChild(list);
    if(!isExpanded&&items.length>shown.length){const more=document.createElement('div');more.className='edgeGroupMore';const b=document.createElement('button');b.type='button';b.textContent='展開（残り '+(items.length-shown.length)+'）';b.onclick=()=>{edgeExpandedGroups[direction].add(key);renderEditEdges();if(mode==='organize')renderOrganize()};more.appendChild(b);block.appendChild(more)}
    zone.appendChild(block);
  }
  if(outgoing&&!edgeExpandAll.outgoing&&!edgeEditMode.outgoing&&(rawEdges.length>6||groups.length>2)){zone.classList.add('edgeZoneBounded');const reveal=document.createElement('div');reveal.className='edgeGroupMore';const b=document.createElement('button');b.type='button';b.textContent='Parent全体を展開';b.onclick=()=>{edgeExpandAll.outgoing=true;renderEditEdges();if(mode==='organize')renderOrganize()};reveal.appendChild(b);zone.appendChild(reveal)}
  root.appendChild(zone);
  if(edgeEditMode[direction])updateEdgeDeleteButton(direction,zone);
}
function relationLineInfo(line){
  const m=String(line||'').match(/^\s*([^:\n][^:\n]{0,79}?)::\s*\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+"label-fixed")?\)\s*$/);
  if(!m)return null;
  return{relation:m[1].trim(),label:m[2].replace(/\\([\[\]\\])/g,'$1'),file:decodeURIComponent(m[3].split('/').pop())};
}
function bodyWithoutPureEdgeSections(text){
  // YAML frontmatter belongs to Source view. Edit/Organize show only the note
  // itself, while the structural Parent/Child divider remains hidden too.
  const visible=splitYamlFrontmatter(text).body;
  // Canonical relationship metadata is one `関係::[ノート](file.md)` line.
  // Legacy `## 関係` + standalone-link blocks are still hidden/read for migration.
  const lines=String(visible||'').replace(/\n$/,'').split('\n');
  const out=[];
  for(let i=0;i<lines.length;){
    if(/^\s*---\s*$/.test(lines[i])){i++;continue}
    if(/^\s*creator::\s*.+?\s*$/i.test(lines[i])){i++;continue}
    if(relationLineInfo(lines[i])){i++;continue}
    const h=headingInfo(lines[i]);
    if(h&&h.level===2){
      let j=i+1;
      while(j<lines.length&&!lines[j].trim())j++;
      if(j<lines.length&&linkInfo(lines[j])){
        let k=j,lastLinkEnd=j;
        while(k<lines.length){
          if(linkInfo(lines[k])){lastLinkEnd=k+1;k++;continue}
          if(!lines[k].trim()){
            let n=k;while(n<lines.length&&!lines[n].trim())n++;
            if(n<lines.length&&linkInfo(lines[n])){k=n;continue}
          }
          break;
        }
        i=lastLinkEnd;continue;
      }
    }
    out.push(lines[i]);i++;
  }
  return out.join('\n').replace(/^\n+|\n+$/g,'');
}
function taskLineInfo(line){const m=String(line||'').match(/^\s*[-*+]\s+\[([ xX])\]\s+(.*)$/);return m?{done:m[1].toLowerCase()==='x',text:m[2]}:null}
function tableSeparatorLine(line){return /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(String(line||''))}
function tableCells(line){let x=String(line||'').trim();if(x.startsWith('|'))x=x.slice(1);if(x.endsWith('|'))x=x.slice(0,-1);return x.split('|').map(v=>v.trim())}
function isTableStart(lines,i){return i+1<lines.length&&String(lines[i]||'').includes('|')&&tableSeparatorLine(lines[i+1])}
function renderMarkdownDocument(root,text,{taskInteractive=false}={}){
  const lines=String(text||'').split('\n');let taskNo=0;
  for(let i=0;i<lines.length;){
    if(isTableStart(lines,i)){
      const head=tableCells(lines[i]);let j=i+2,rows=[];while(j<lines.length&&String(lines[j]||'').includes('|')&&lines[j].trim()){rows.push(tableCells(lines[j]));j++}
      const w=document.createElement('div');w.className='mdTableWrap';const t=document.createElement('table');t.className='mdTable';const thead=document.createElement('thead'),trh=document.createElement('tr');for(const c of head){const th=document.createElement('th');th.innerHTML=inlinePreview(c);trh.appendChild(th)}thead.appendChild(trh);t.appendChild(thead);const tb=document.createElement('tbody');for(const row of rows){const tr=document.createElement('tr');for(let k=0;k<head.length;k++){const td=document.createElement('td');td.innerHTML=inlinePreview(row[k]||'');tr.appendChild(td)}tb.appendChild(tr)}t.appendChild(tb);w.appendChild(t);root.appendChild(w);i=j;continue;
    }
    const task=taskLineInfo(lines[i]);
    if(task){const lab=document.createElement('label');lab.className='taskItem'+(task.done?' done':'');const cb=document.createElement('input');cb.type='checkbox';cb.checked=task.done;cb.disabled=!taskInteractive;cb.dataset.taskNo=String(taskNo++);const span=document.createElement('span');span.className='taskText';span.innerHTML=inlinePreview(task.text);lab.appendChild(cb);lab.appendChild(span);if(taskInteractive)cb.onchange=()=>toggleTaskByOrdinal(Number(cb.dataset.taskNo)).catch(err=>status(err.message));root.appendChild(lab);i++;continue}
    const h=headingInfo(lines[i]);
    if(h){const block=document.createElement('section');block.className='previewSection';block.dataset.headingLevel=String(h.level);const head=document.createElement('div');head.className='sectionHead';const hd=document.createElement('div');hd.className='heading';hd.innerHTML='<h'+h.level+'>'+inlinePreview(h.text)+'</h'+h.level+'>';head.appendChild(hd);block.appendChild(head);i++;while(i<lines.length&&!String(lines[i]||'').trim())i++;while(i<lines.length&&!headingInfo(lines[i])&&!isTableStart(lines,i)&&!taskLineInfo(lines[i])){const d=document.createElement('div');d.className='previewLine';d.innerHTML=lines[i].trim()?inlinePreview(lines[i]):'&nbsp;';block.appendChild(d);i++}root.appendChild(block);continue}
    const d=document.createElement('div');d.className='previewLine';d.innerHTML=lines[i].trim()?inlinePreview(lines[i]):'&nbsp;';root.appendChild(d);i++;
  }
}
function renderBodyPreview(root,text){
  const wrap=document.createElement('section');wrap.className='organizeBody';renderMarkdownDocument(wrap,text,{taskInteractive:!!currentData?.can_edit});root.appendChild(wrap);
}
function renderEditEdges(){
  const p=$('editParentEdges'),c=$('editChildEdges');if(!p||!c)return;
  p.innerHTML='';c.innerHTML='';
  renderEdgeZone(p,'outgoing');renderEdgeZone(c,'incoming');
  for(const root of [p,c])root.querySelectorAll('[data-file]').forEach(a=>a.onclick=e=>{e.preventDefault();openFile(a.dataset.file)});
}
function renderOrganize(){
  const root=$('organizeView');root.innerHTML='';
  // Parent / Child are directions, not Markdown headings or visible labels.
  // Outgoing (parent-side) relations stay above the boundary; incoming
  // (child-side/backlink) relations stay below it.
  renderEdgeZone(root,'outgoing');
  renderBodyPreview(root,bodyWithoutPureEdgeSections(editorText()));
  if(!currentData?.is_index){const divider=document.createElement('div');divider.className='edgeDirectionGap';divider.setAttribute('aria-hidden','true');root.appendChild(divider)}
  renderEdgeZone(root,'incoming');
  root.querySelectorAll('[data-file]').forEach(a=>a.onclick=e=>{e.preventDefault();organizeLinkIndex=[...root.querySelectorAll('a[data-file]')].indexOf(a);openFile(a.dataset.file)});
  organizeLinkIndex=-1;organizeSectionIndex=-1;
}
function organizeLinks(){return [...$('organizeView').querySelectorAll('a[data-file]')]}
function organizeH2Sections(){return [...$('organizeView').querySelectorAll('section.previewSection[data-heading-level="2"]')]}
function clearOrganizeSectionSelection(){organizeH2Sections().forEach(s=>s.classList.remove('keyboardSectionSelected'))}
function selectOrganizeLink(nextIndex){
  const links=organizeLinks();
  links.forEach(a=>a.classList.remove('keyboardSelected'));
  if(!links.length){organizeLinkIndex=-1;return}
  if(nextIndex<0||nextIndex>=links.length)return;
  organizeLinkIndex=nextIndex;
  const a=links[organizeLinkIndex];
  a.classList.add('keyboardSelected');
  const sec=a.closest('section.previewSection[data-heading-level="2"]');
  if(sec){const sections=organizeH2Sections();organizeSectionIndex=sections.indexOf(sec);clearOrganizeSectionSelection();sec.classList.add('keyboardSectionSelected')}
  try{a.focus({preventScroll:true})}catch(_){a.focus()}
  a.scrollIntoView({behavior:'smooth',block:'nearest',inline:'nearest'});
}
function moveOrganizeSection(direction){
  const sections=organizeH2Sections();
  if(!sections.length)return;
  let idx=organizeSectionIndex;
  if(idx<0){
    const active=document.activeElement?.closest?.('section.previewSection[data-heading-level="2"]');
    idx=active?sections.indexOf(active):(direction>0?-1:0);
  }
  const next=idx+direction;if(next<0||next>=sections.length)return;idx=next;
  organizeSectionIndex=idx;
  clearOrganizeSectionSelection();
  const sec=sections[idx];
  sec.classList.add('keyboardSectionSelected');
  const first=sec.querySelector('a[data-file]');
  if(first){
    const links=organizeLinks();
    selectOrganizeLink(links.indexOf(first));
  }else{
    organizeLinks().forEach(a=>a.classList.remove('keyboardSelected'));
    organizeLinkIndex=-1;
    try{$('organizeView').focus({preventScroll:true})}catch(_){ }
    sec.scrollIntoView({behavior:'smooth',block:'nearest',inline:'nearest'});
  }
}
async function navigateBack(){
  // Vim Backspace follows the exact path the user actually travelled.
  // Example: A -> Index -> B becomes B -> Index -> A with two presses,
  // regardless of whether any item is an Index or has appeared before.
  if(navigationTrail.length<2)return;
  navigationTrail.pop();
  const prev=navigationTrail[navigationTrail.length-1];
  await openFile(prev.file,{record:false,replaceUrl:true});
  renderTrail();
  if(mode==='organize')setTimeout(()=>$('organizeView').focus({preventScroll:true}),0);
}
function pushTrail(file,title){
  // Keep chronological navigation history. Do not collapse an older occurrence
  // of the same file: A -> B -> A is a real path and Backspace must retrace it.
  if(!navigationTrail.length){navigationTrail=[{file,title}];renderTrail();return}
  const last=navigationTrail[navigationTrail.length-1];
  if(last.file===file){last.title=title;renderTrail();return}
  navigationTrail.push({file,title});
  renderTrail();
}
function renderTrail(){
  const root=$('trail');root.innerHTML='';
  navigationTrail.forEach((item,i)=>{
    if(i){const a=document.createElement('span');a.className='trailArrow';a.textContent='→';root.appendChild(a)}
    const b=document.createElement('button');b.className='trailItem'+(i===navigationTrail.length-1?' current':'');b.textContent=item.title||item.file;b.title=item.file;
    b.onclick=async()=>{navigationTrail=navigationTrail.slice(0,i+1);await openFile(item.file,{record:false,replaceUrl:true});renderTrail()};
    root.appendChild(b);
  });
  requestAnimationFrame(()=>{root.scrollLeft=root.scrollWidth});
}
$('trailReset').onclick=()=>{
  const title=currentData?.title||current;
  navigationTrail=[{file:current,title}];
  renderTrail();
};
function graphSettings(){return{limit:Number($('graphLimit')?.value||18),depth:Number($('graphDepth')?.value||2),spacing:Number($('graphSpacing')?.value||90),fontSize:Number($('graphFontSize')?.value||11)}}
function relationClass(relation){const r=String(relation||'').trim();if(['賛同','賛成した','肯定','賛成','支持'].includes(r))return 'support';if(['否定','反対した','反論','反対'].includes(r))return 'oppose';if(['質問','質問した'].includes(r))return 'question';if(['回答','回答した'].includes(r))return 'answer';if(r==='公開版'||r==='派生')return 'derive';if(['関連','関連した','言及','補足した','補足'].includes(r))return 'related';if(['カテゴリー','トピック','分類'].includes(r))return 'topic';if(['ノート','分類した','下位カテゴリー'].includes(r))return 'note';if(r==='雑談')return 'other';return ''}
function relationNodeColor(relation){return '#000000'}
function queueGraph(delay=80){if(graphTimer)clearTimeout(graphTimer);graphTimer=setTimeout(()=>refreshGraph().catch(console.error),delay)}
function svgEl(name,attrs={}){const n=document.createElementNS('http://www.w3.org/2000/svg',name);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n}
function shortenLabel(s,n=18){s=String(s||'');return s.length>n?s.slice(0,n-1)+'…':s}
async function refreshGraph(){
  if(!current)return;
  const token=++graphRunToken;
  if(graphFrame){cancelAnimationFrame(graphFrame);graphFrame=null}
  const {limit,depth,spacing,fontSize}=graphSettings();
  const data=await api('/api/graph?center='+encodeURIComponent(current)+'&limit='+limit+'&depth='+depth);
  if(token!==graphRunToken)return;
  const svg=$('localGraph'),wrap=$('graphWrap');svg.innerHTML='';
  $('graphCountLabel').textContent=(data.nodes?.length||0)+' nodes';
  if(!data.nodes?.length)return;
  const rect=wrap.getBoundingClientRect(),w=Math.max(280,rect.width||340),h=Math.max(280,rect.height||520);
  svg.setAttribute('viewBox','0 0 '+w+' '+h);
  const cx=w/2,cy=h/2;
  const rawById=new Map((data.nodes||[]).map(n=>[n.id,n]));
  const nodes=(data.nodes||[]).map((n,i)=>{
    const angle=(i/Math.max(1,data.nodes.length))*Math.PI*2+(n.distance||0)*0.35;
    const radius=n.id===current?0:Math.min(Math.min(w,h)*0.44, spacing*(0.72+0.58*(n.distance||1)));
    return{...n,x:cx+Math.cos(angle)*radius,y:cy+Math.sin(angle)*radius,vx:0,vy:0,fx:null,fy:null,dragging:false};
  });
  const byId=new Map(nodes.map(n=>[n.id,n]));
  const edges=(data.edges||[]).map(e=>({...e,a:byId.get(e.source),b:byId.get(e.target)})).filter(e=>e.a&&e.b);
  const edgeLayer=svgEl('g'),edgeLabelLayer=svgEl('g'),nodeLayer=svgEl('g');svg.appendChild(edgeLayer);svg.appendChild(edgeLabelLayer);svg.appendChild(nodeLayer);
  const edgeEls=edges.map(e=>{
    const isPrimary=(e.source===current||e.target===current);const line=svgEl('line',{class:'graphEdge'+(isPrimary?' primary':''),stroke:isPrimary?'#737373':'#a3a3a3'});
    edgeLayer.appendChild(line);
    let label=null;if(graphShowRelationLabels&&String(e.relation||'').trim()){label=svgEl('text',{class:'graphEdgeLabel','text-anchor':'middle','font-size':Math.max(8,fontSize-1)});label.textContent=String(e.relation||'').trim();edgeLabelLayer.appendChild(label)}
    return{edge:e,el:line,label};
  });
  // Color nodes by the relation on the edge that connects them toward the
  // current/center node. Edges themselves intentionally stay neutral gray.
  const nodeRelationClass=new Map();
  for(const n of nodes){
    if(n.id===current)continue;
    const nd=Number(n.distance||0);
    const candidates=edges.filter(e=>{
      if(e.source!==n.id&&e.target!==n.id)return false;
      const other=e.source===n.id?e.b:e.a;
      return Number(other?.distance||0)<nd;
    });
    const chosen=candidates[0]||edges.find(e=>e.source===n.id||e.target===n.id);
    if(chosen){nodeRelationClass.set(n.id,chosen.relation||'')}
  }
  const nodeEls=[];
  let dragNode=null,dragStart=null,dragMoved=false;
  function pointerToSvg(ev){
    const r=svg.getBoundingClientRect();
    return{x:(ev.clientX-r.left)*(w/Math.max(1,r.width)),y:(ev.clientY-r.top)*(h/Math.max(1,r.height))};
  }
  function wake(){
    if(graphFrame)return;
    let quiet=0,frames=0;
    const step=()=>{
      if(token!==graphRunToken){graphFrame=null;return}
      frames++;
      // pairwise repulsion
      for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
        const a=nodes[i],b=nodes[j];let dx=b.x-a.x,dy=b.y-a.y,d2=dx*dx+dy*dy;
        if(d2<16){dx+=(i-j)*0.23;dy+=(j-i)*0.17;d2=dx*dx+dy*dy}
        const d=Math.sqrt(d2)||1,repulseBase=spacing*spacing*0.16,force=Math.min(3.2,repulseBase/d2),fx=force*dx/d,fy=force*dy/d;
        if(a.fx==null){a.vx-=fx;a.vy-=fy}if(b.fx==null){b.vx+=fx;b.vy+=fy}
      }
      // spring forces on edges
      for(const e of edges){
        const a=e.a,b=e.b,dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1;
        const wanted=spacing*(0.82+0.18*Math.min(2,Math.max(a.distance||0,b.distance||0)));
        const force=(d-wanted)*0.0065,fx=force*dx/d,fy=force*dy/d;
        if(a.fx==null){a.vx+=fx;a.vy+=fy}if(b.fx==null){b.vx-=fx;b.vy-=fy}
      }
      let energy=0;
      for(const n of nodes){
        if(n.fx!=null){n.x=n.fx;n.y=n.fy;n.vx=0;n.vy=0;continue}
        n.vx+=(cx-n.x)*0.0018;n.vy+=(cy-n.y)*0.0018;
        const pad=25;if(n.x<pad)n.vx+=(pad-n.x)*0.014;if(n.x>w-pad)n.vx-=(n.x-(w-pad))*0.014;
        if(n.y<pad)n.vy+=(pad-n.y)*0.014;if(n.y>h-pad)n.vy-=(n.y-(h-pad))*0.014;
        n.vx*=0.86;n.vy*=0.86;n.x+=n.vx;n.y+=n.vy;energy+=Math.abs(n.vx)+Math.abs(n.vy);
      }
      render();
      if(dragNode||energy>0.035||frames<150){quiet=0}else quiet++;
      if(quiet>24||frames>900){graphFrame=null;return}
      graphFrame=requestAnimationFrame(step);
    };
    graphFrame=requestAnimationFrame(step);
  }
  function render(){
    for(const {edge:e,el,label} of edgeEls){el.setAttribute('x1',e.a.x);el.setAttribute('y1',e.a.y);el.setAttribute('x2',e.b.x);el.setAttribute('y2',e.b.y);if(label){label.setAttribute('x',(e.a.x+e.b.x)/2);label.setAttribute('y',(e.a.y+e.b.y)/2-4)}}
    for(const {node:n,el} of nodeEls)el.setAttribute('transform','translate('+n.x+' '+n.y+')');
  }
  for(const n of nodes){
    const relation=nodeRelationClass.get(n.id)||'';const rc=relationClass(relation);const g=svgEl('g',{class:'graphNode'+(rc?' '+rc:'')+(n.id===current?' current':'')});
    const r=n.id===current?8:6;const nodeColor='#000000';g.appendChild(svgEl('circle',{cx:0,cy:0,r,fill:nodeColor,stroke:nodeColor}));
    const t=svgEl('text',{x:0,y:r+fontSize+4,'text-anchor':'middle','font-size':fontSize});t.textContent=shortenLabel(n.title,n.id===current?38:28);g.appendChild(t);
    const tt=svgEl('title');tt.textContent=n.title+'\n'+n.id;g.appendChild(tt);nodeLayer.appendChild(g);nodeEls.push({node:n,el:g});
    g.addEventListener('pointerdown',ev=>{
      if(ev.button!==0)return;ev.preventDefault();g.setPointerCapture(ev.pointerId);dragNode=n;n.dragging=true;dragMoved=false;dragStart={x:ev.clientX,y:ev.clientY};
      const p=pointerToSvg(ev);n.fx=p.x;n.fy=p.y;n.x=p.x;n.y=p.y;wake();
    });
    g.addEventListener('pointermove',ev=>{
      if(dragNode!==n)return;const p=pointerToSvg(ev);n.fx=p.x;n.fy=p.y;n.x=p.x;n.y=p.y;
      if(dragStart&&Math.hypot(ev.clientX-dragStart.x,ev.clientY-dragStart.y)>4)dragMoved=true;render();wake();
    });
    const finish=ev=>{
      if(dragNode!==n)return;try{g.releasePointerCapture(ev.pointerId)}catch(_){ }
      const wasMoved=dragMoved;dragNode=null;n.dragging=false;dragStart=null;dragMoved=false;
      n.fx=null;n.fy=null
      wake();
      if(!wasMoved&&n.id!==current)openFile(n.id).catch(console.error);
    };
    g.addEventListener('pointerup',finish);g.addEventListener('pointercancel',finish);
  }
  render();wake();
}
let cachedFiles=[];
function updateNodeDeleteButton(){
  const b=$('nodeDeleteBtn');if(!b)return;
  b.disabled=!nodeSelectionMode||selectedNodeFiles.size===0;
  b.textContent=selectedNodeFiles.size?'削除 '+selectedNodeFiles.size:'削除';
}
function renderFiles(){
  const sort=$('nodeSort')?.value||'newest';
  const index=cachedFiles.find(f=>f.is_index);
  const rest=cachedFiles.filter(f=>!f.is_index).slice().sort((a,b)=>{
    const av=Number(a.time||0),bv=Number(b.time||0);
    if(av!==bv)return sort==='oldest'?av-bv:bv-av;
    return String(a.title||'').localeCompare(String(b.title||''),'ja');
  });
  const items=index?[index,...rest]:rest;
  $('files').innerHTML='';
  for(const f of items){
    if(nodeSelectionMode){
      const row=document.createElement('div');row.className='fileSelectRow';
      const cb=document.createElement('input');cb.type='checkbox';cb.className='fileSelectCheck';cb.disabled=!!f.is_index;cb.checked=selectedNodeFiles.has(f.name);cb.setAttribute('aria-label',f.title+' を選択');
      cb.onchange=()=>{if(cb.checked)selectedNodeFiles.add(f.name);else selectedNodeFiles.delete(f.name);updateNodeDeleteButton()};
      const b=document.createElement('button');b.className='file'+(f.name===current?' active':'');b.textContent=f.title;b.title=f.name+(f.time?' · '+formatLocalDateTime(f.time):'');
      b.onclick=()=>{if(f.is_index){openFile(f.name);return}cb.checked=!cb.checked;cb.onchange()};
      row.appendChild(cb);row.appendChild(b);$('files').appendChild(row);
    }else{
      const b=document.createElement('button');
      b.className='file'+(f.name===current?' active':'');
      b.textContent=f.title;
      b.title=f.name+(f.time?' · '+formatLocalDateTime(f.time):'');
      b.onclick=()=>openFile(f.name);
      $('files').appendChild(b);
    }
  }
  $('nodeSelectBtn').textContent=nodeSelectionMode?'選択解除':'選択';
  updateNodeDeleteButton();
}
async function refreshFiles(){const data=await api('/api/files');cachedFiles=data.files||[];if(data.index_file)profile.index_file=data.index_file;renderFiles()}
async function flushAutosave(commitRelations=true){
  if(autosaveTimer){clearTimeout(autosaveTimer);autosaveTimer=null}
  // Never capture an unfinished IME conversion. Navigation/view switching waits
  // for compositionend instead of dropping or half-saving Japanese input.
  if(anyImeComposing())await waitForImeIdle();
  const needRelationCommit=!!(commitRelations&&relationSyncPending);
  if((!dirty&&!needRelationCommit)||!currentData?.can_edit){return await saveChain}

  const name=current,content=editorText(),revision=editRevision;
  const sourceCursor=(mode==='source')?editor.indexFromPos(editor.getCursor()):null;
  const previousTitle=currentData?.title||'';
  dirty=false;
  if(needRelationCommit)relationSyncPending=false;

  const previous=saveChain.catch(()=>{});
  const task=previous.then(async()=>{
    const d=await api('/api/file',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,content,voter:voterId,commit_relations:needRelationCommit,draft_response:!needRelationCommit,client_save_session:saveClientSession,client_seq:revision})});
    if(current===name){
      const newerEdits=editRevision!==revision||dirty||anyImeComposing();
      if(!newerEdits){
        currentData=needRelationCommit?d:{...currentData,...d};
        let trailTitleChanged=false;for(const item of navigationTrail){if(item.file===name){item.title=d.title;trailTitleChanged=true}}if(trailTitleChanged)renderTrail();
        // Draft autosave never replaces Source text. A structural commit may
        // refresh the projection only when no newer keystroke exists.
        if(mode!=='source'||needRelationCommit){
          loadingDoc=true;clearLiveLinkMarks();editor.setValue(sourceProjectionWithBoxEdges(d.content));refreshSourceFrontmatterStyle();refreshSourceAutoEdgeStyle();loadingDoc=false;
          currentStructureSignature=structureSignatureFromText(d.content);
          if(mode==='source'&&sourceCursor!=null){try{editor.setCursor(editor.posFromIndex(Math.min(sourceCursor,editor.getValue().length)))}catch(_){}}
        }
        updateFileTitle();updateAuthorBar();updateEditPermissions();
      }
      // Graph/edge DOM work is only needed when structure actually changed.
      if(needRelationCommit){queueTopicWidgets();queueGraph();renderEditEdges();if(mode==='organize')renderOrganize()}
      if(!newerEdits&&String(d.title||'')!==String(previousTitle||''))await refreshFiles();
    }
    return d;
  });
  saveChain=task;
  try{return await task}catch(e){
    if(current===name){dirty=true;if(needRelationCommit)relationSyncPending=true}
    status('保存エラー: '+(e?.message||''),{kind:'error'});throw e
  }
}

function queueAutosave(delay=550){
  if(autosaveTimer)clearTimeout(autosaveTimer);
  // Timed autosave is draft-only. Relationship mirrors are committed at an
  // edit-confirm boundary instead of continuously overwriting Source text.
  autosaveTimer=setTimeout(()=>{flushAutosave(false).catch(console.error)},delay)
}
async function openFile(name,opts={}){
  await flushAutosave();
  const d=await api('/api/file?name='+encodeURIComponent(name)+'&voter='+encodeURIComponent(voterId));
  current=name;currentData=d;relationSyncPending=false;if(opts.url!==false)syncNoteUrl(name,opts.replaceUrl===true);sectionSort.clear();edgeEditMode={outgoing:false,incoming:false};edgeExpandedGroups.outgoing.clear();edgeExpandedGroups.incoming.clear();edgeExpandAll={outgoing:false,incoming:false};selectedEdgeKeys.outgoing.clear();selectedEdgeKeys.incoming.clear();setEditorsFromRaw(d.content);dirty=false;updateFileTitle();updateAuthorBar();updateEditPermissions();updateContextAction();renderEditEdges();
  if(!d.can_edit)clearTopicWidgets();
  if(opts.record!==false)pushTrail(name,d.title);
  await refreshFiles();setMobileSidebar(false);queueTopicWidgets();queueGraph();if(mode==='organize')renderOrganize();else if(mode==='source'){setTimeout(()=>{editor.refresh();editor.focus();},0)}else{setTimeout(()=>{bodyEditor.setSize(null,'auto');bodyEditor.refresh();bodyEditor.focus();},0)}
}
function clearTopicWidgets(){for(const w of topicLineWidgets){try{w.clear()}catch(_){}}topicLineWidgets=[]}
let topicWidgetTimer=null;
function queueTopicWidgets(){if(topicWidgetTimer)clearTimeout(topicWidgetTimer);topicWidgetTimer=setTimeout(renderTopicWidgets,120)}
function topicSectionLinks(){
  const out=[];let inTopic=false;
  for(let i=0;i<editor.lineCount();i++){const line=editor.getLine(i),h=headingInfo(line);if(h){if(h.level===1)inTopic=false;else inTopic=(h.level===2&&h.text.trim()==='トピック');continue}if(inTopic){const li=linkInfo(line);if(li)out.push({line:i,...li})}}
  return out;
}
function topicEdgeRatingFor(target){return currentData?.topic_edge_ratings?.[target]||{appropriate:0,inappropriate:0,current_vote:null}}
async function voteTopicEdge(target,vote){
  if(isGuest()){showAuth('評価するにはログインまたは新規登録してください',()=>voteTopicEdge(target,vote));return}
  // Topic relevance voting is only available while viewing another user's
  // ordinary note in organize view.  Own notes never show or accept votes.
  if(mode!=='organize'||currentData?.can_edit||currentData?.is_topic||currentData?.is_index)return;
  const cur=topicEdgeRatingFor(target).current_vote||null,next=cur===vote?null:vote;
  const d=await api('/api/topic-edge-vote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:current,target,vote:next})});
  currentData=d;queueGraph();renderOrganize();
}
function renderTopicWidgets(){
  // No 適切/不適切 controls in the Markdown editor. They belong to organize view only.
  clearTopicWidgets();
}
function renderConnections(d){}
function updateViewModeToggle(){
  const b=$('viewModeToggle');if(!b)return;
  b.textContent=mode==='source'?'ソース':'整理ビュー';
  b.setAttribute('aria-pressed',mode==='source'?'true':'false');
  b.title='Ctrl+E: 整理ビュー / ソース切替';
}
function setModeVisibility(next){
  // v70 has only two user-facing modes: Organize and Source.
  $('editWrap').style.display='none';
  $('sourceWrap').style.display=next==='source'?'block':'none';
  $('organizeWrap').style.display=next==='organize'?'block':'none';
  updateViewModeToggle();updateVimUi();
}
function applySourceInsertState(focus){
  // Source is the writing surface: entering it must accept ordinary keyboard/
  // IME input immediately. Runs synchronously so a slow or failed autosave can
  // never strand the editor in NORMAL, where `beforeinput` blocks every key.
  vimVisual=null;vimVisualAnchor=null;vimInputMode='insert';vimPendingCommand='';
  clearVimNormalLinkMarks();applyEditorReadOnly();updateVimUi();
  if(focus&&mode==='source'){try{editor.focus();vimEnsureCursorVisible(editor,true)}catch(_){}}
}
function switchMode(next,opts={}){
  next=next==='source'?'source':'organize';
  const forceNormal=!!opts.forceNormal;
  // Explicit transitions into Source default to INSERT. Only opts.enterInsert
  // === false (Esc pressed from Organize) keeps NORMAL.
  const enterInsert=next==='source'&&!forceNormal&&opts.enterInsert!==false;
  if(enterInsert)applySourceInsertState(false);
  if(modeSwitchPromise){
    // A switch is already in flight. Do not drop a fresh explicit edit intent:
    // re-assert INSERT and focus once the running transition settles.
    if(enterInsert)modeSwitchPromise.then(()=>{if(mode==='source')applySourceInsertState(true)}).catch(()=>{});
    return modeSwitchPromise;
  }
  modeSwitchPromise=(async()=>{
    await waitForImeIdle();
    // Freeze Vim input before the asynchronous save. Otherwise a user can type
    // more characters while Ctrl+E is waiting for disk/network I/O and those
    // characters belong to neither side of the transition cleanly.
    if(forceNormal){
      const active=mode==='source'?editor:bodyEditor;
      const caret=mode==='source'?collapseVimSelection(editor,editor.getCursor('head')):null;
      vimVisual=null;vimVisualAnchor=null;vimInputMode='normal';vimPendingCommand='';
      clearLiveLinkMarks();clearVimNormalLinkMarks();applyEditorReadOnly();updateVimUi();
      if(mode==='source'&&caret){collapseVimSelection(editor,caret)}
    }
    // A failed autosave (offline / auth) must not abort the transition; the
    // save retries on its own and the user still gets a usable editor.
    try{await flushAutosave(true)}catch(_){}
    if(enterInsert)applySourceInsertState(false);
    if(next===mode){
      setModeVisibility(next);
      if(next==='source')setTimeout(()=>{editor.refresh();if(vimInputMode==='normal'&&!vimVisual)refreshVimNormalLinks();else clearVimNormalLinkMarks();editor.focus();vimEnsureCursorVisible(editor,true)},0);
      else if(forceNormal)refreshVimNormalLinks();
      return;
    }
    mode=next;setModeVisibility(next);organizeLinkIndex=-1;organizeSectionIndex=-1;
    if(next==='organize'){
      vimVisual=null;vimVisualAnchor=null;
      clearVimNormalLinkMarks();renderOrganize();$('organizeView').tabIndex=-1;setTimeout(()=>$('organizeView').focus({preventScroll:true}),0);
    }else{
      setTimeout(()=>{
        editor.refresh();
        if(vimInputMode==='normal'&&!vimVisual)refreshVimNormalLinks();else clearVimNormalLinkMarks();
        editor.focus();vimEnsureCursorVisible(editor,true);
      },0);
    }
  })().catch(e=>{status(e?.message||'表示切替に失敗しました');throw e}).finally(()=>{modeSwitchPromise=null});
  return modeSwitchPromise;
}
function toggleViewMode(opts={}){
  const next=mode==='source'?'organize':'source';
  return switchMode(next,opts);
}

function vimAllLinks(cm){
  const out=[];const re=/\[((?:\\.|[^\]\\])+)]\(([^)\s]+\.md)(?:\s+"label-fixed")?\)/g;
  for(let line=0;line<cm.lineCount();line++){
    const text=cm.getLine(line)||'';re.lastIndex=0;let m;
    while((m=re.exec(text))){out.push({line,start:m.index,end:m.index+m[0].length,labelStart:m.index+1,file:decodeURIComponent(m[2].split('/').pop())})}
  }
  return out;
}
function vimJumpLink(cm,dir){
  const links=vimAllLinks(cm);if(!links.length){status('リンクがありません');return}
  const cur=cm.getCursor();
  const currentIndex=links.findIndex(x=>x.line===cur.line&&cur.ch>=x.start&&cur.ch<=x.end);
  let target=null;
  if(currentIndex>=0){
    const nextIndex=currentIndex+(dir>0?1:-1);
    if(nextIndex<0||nextIndex>=links.length){status(dir>0?'最後のリンクです':'最初のリンクです');vimEnsureCursorVisible(cm);return}
    target=links[nextIndex];
  }else{
    const pos=cm.indexFromPos(cur);
    const withIndex=links.map(x=>({...x,index:cm.indexFromPos({line:x.line,ch:x.start})}));
    if(dir>0)target=withIndex.find(x=>x.index>pos)||null;
    else target=[...withIndex].reverse().find(x=>x.index<pos)||null;
    if(!target){status(dir>0?'最後のリンクです':'最初のリンクです');vimEnsureCursorVisible(cm);return}
  }
  cm.setCursor({line:target.line,ch:target.labelStart});
  if(cm===bodyEditor)scheduleLiveLinkRefresh(0);
  vimEnsureCursorVisible(cm,true);
}

function vimOpenCursorLink(cm){
  const cur=cm.getCursor(),hit=markdownLinkAt(cm.getLine(cur.line)||'',cur.ch);
  if(hit){openFile(hit.file).catch(e=>status(e.message));return true}
  return false;
}
function vimDeleteLine(cm){
  const cur=cm.getCursor(),line=cm.getLine(cur.line)||'';vimRegister=line+'\n';vimRegisterLinewise=true;
  const last=cm.lineCount()-1;
  if(last===0)cm.replaceRange('',{line:0,ch:0},{line:0,ch:line.length},'+vim');
  else if(cur.line<last)cm.replaceRange('',{line:cur.line,ch:0},{line:cur.line+1,ch:0},'+vim');
  else cm.replaceRange('',{line:cur.line-1,ch:(cm.getLine(cur.line-1)||'').length},{line:cur.line,ch:line.length},'+vim');
  cm.setCursor({line:Math.min(cur.line,cm.lineCount()-1),ch:0});
}
function vimYankLine(cm){const cur=cm.getCursor();vimRegister=(cm.getLine(cur.line)||'')+'\n';vimRegisterLinewise=true;status('1行コピー')}
function vimPaste(cm,before=false){
  if(!vimRegister)return;
  const cur=cm.getCursor();
  if(vimRegisterLinewise){const line=before?cur.line:cur.line+1;cm.replaceRange(vimRegister,{line:Math.min(line,cm.lineCount()),ch:0},null,'+vim');cm.setCursor({line:Math.min(line,cm.lineCount()-1),ch:0})}
  else cm.replaceRange(vimRegister,cur,null,'+vim');
}
async function toggleTaskByOrdinal(ord){
  if(!currentData?.can_edit)return;
  const lines=editor.getValue().split('\n');let seen=0;
  for(let i=0;i<lines.length;i++){if(!taskLineInfo(lines[i]))continue;if(seen++!==ord)continue;lines[i]=lines[i].replace(/\[([ xX])\]/,m=>/x/i.test(m)?'[ ]':'[x]');editor.setValue(lines.join('\n'));dirty=true;queueAutosave(80);if(mode==='organize')renderOrganize();return}
}
function toggleTaskAtCursor(cm){const cur=cm.getCursor(),line=cm.getLine(cur.line)||'';if(!taskLineInfo(line)){status('この行はチェックボックスではありません');return false}cm.replaceRange(line.replace(/\[([ xX])\]/,m=>/x/i.test(m)?'[ ]':'[x]'),{line:cur.line,ch:0},{line:cur.line,ch:line.length},'+vim');cm.setCursor({line:cur.line,ch:Math.min(cur.ch,cm.getLine(cur.line).length)});vimEnsureCursorVisible(cm);return true}
function makeTaskAtCursor(cm){const cur=cm.getCursor(),line=cm.getLine(cur.line)||'';if(taskLineInfo(line)){status('すでにチェックボックスです');return}let next;if(!line.trim())next='- [ ] ';else if(/^\s*[-*+]\s+/.test(line))next=line.replace(/^(\s*[-*+]\s+)/,'$1[ ] ');else next='- [ ] '+line;cm.replaceRange(next,{line:cur.line,ch:0},{line:cur.line,ch:line.length},'+vim');cm.setCursor({line:cur.line,ch:Math.min(next.length,Math.max(6,cur.ch+6))});vimEnsureCursorVisible(cm)}
function insertMarkdownTable(cm){const cur=cm.getCursor();const before=(cm.getLine(cur.line)||'').trim()?'\n':'';const md=before+'| 列1 | 列2 |\n| --- | --- |\n|  |  |';cm.replaceSelection(md,'end','+table');const pos=cm.getCursor();cm.setCursor({line:Math.max(0,pos.line),ch:2});vimEnsureCursorVisible(cm,true)}
function tableCellMove(cm,dir){const cur=cm.getCursor(),line=cm.getLine(cur.line)||'';if(!line.includes('|'))return false;const bars=[];for(let i=0;i<line.length;i++)if(line[i]==='|')bars.push(i);if(bars.length<2)return false;const cells=[];for(let i=0;i<bars.length-1;i++)cells.push({line:cur.line,ch:Math.min(line.length,bars[i]+2)});let idx=0;for(let i=0;i<cells.length;i++)if(cells[i].ch<=cur.ch)idx=i;let targetIdx=idx+dir;if(targetIdx>=0&&targetIdx<cells.length){cm.setCursor(cells[targetIdx]);vimEnsureCursorVisible(cm);return true}const nextLine=cur.line+(dir>0?1:-1);if(nextLine<0||nextLine>=cm.lineCount())return false;const nl=cm.getLine(nextLine)||'';if(!nl.includes('|'))return false;const nb=[];for(let i=0;i<nl.length;i++)if(nl[i]==='|')nb.push(i);if(nb.length<2)return false;cm.setCursor({line:nextLine,ch:dir>0?Math.min(nl.length,nb[0]+2):Math.min(nl.length,nb[nb.length-2]+2)});vimEnsureCursorVisible(cm);return true}
function vimPosCmp(a,b){return (a.line-b.line)||(a.ch-b.ch)}
function vimSelExtend(cm){
  // Re-project the visual selection from the fixed anchor to the live head,
  // keeping the caret on the moving end so the next motion continues cleanly.
  const anchor=vimVisualAnchor;if(!anchor)return;
  const head=cm.getCursor('head');
  if(vimVisual==='line'){
    const top=Math.min(anchor.line,head.line),bot=Math.max(anchor.line,head.line);
    const a={line:top,ch:0},b={line:bot,ch:(cm.getLine(bot)||'').length};
    if(head.line>=anchor.line)cm.setSelection(a,b,{scroll:false});else cm.setSelection(b,a,{scroll:false});
  }else if(vimPosCmp(anchor,head)<=0){
    const to={line:head.line,ch:Math.min((cm.getLine(head.line)||'').length,head.ch+1)};
    cm.setSelection(anchor,to,{scroll:false});
  }else{
    const from={line:anchor.line,ch:Math.min((cm.getLine(anchor.line)||'').length,anchor.ch+1)};
    cm.setSelection(from,head,{scroll:false});
  }
}
function vimVisualMotion(cm,command){
  // CodeMirror motions collapse a non-empty selection to an edge instead of
  // moving one unit, so collapse to the live head first, then re-extend.
  const head=cm.getCursor('head');
  cm.setSelection(head,head,{scroll:false});
  cm.execCommand(command);
  vimSelExtend(cm);
  vimEnsureCursorVisible(cm);
}
function vimVisualEnter(cm,kind){
  if(vimInputMode!=='normal'||mode!=='source')return;
  if(vimVisual===kind){vimVisualExit(cm);return}
  const keepAnchor=vimVisual?vimVisualAnchor:cm.getCursor('head');
  vimVisual=kind;vimVisualAnchor=keepAnchor||cm.getCursor('head');
  clearVimNormalLinkMarks();
  vimSelExtend(cm);updateVimUi();vimEnsureCursorVisible(cm);
}
function vimVisualExit(cm){
  const head=cm.getCursor('head');
  vimVisual=null;vimVisualAnchor=null;
  collapseVimSelection(cm,head);
  updateVimUi();
  if(vimInputMode==='normal'&&mode==='source')refreshVimNormalLinks();
}
function vimVisualYank(cm){
  const linewise=vimVisual==='line';
  const text=cm.getSelection()||'';
  vimRegister=linewise?(text.endsWith('\n')?text:text+'\n'):text;
  vimRegisterLinewise=linewise;
  const sel=cm.listSelections()[0];
  const start=sel?(vimPosCmp(sel.anchor,sel.head)<=0?sel.anchor:sel.head):cm.getCursor();
  vimVisualExit(cm);
  cm.setCursor(linewise?{line:start.line,ch:0}:start);
  status(linewise?'コピーしました（行）':'コピーしました');
}
function vimVisualDelete(cm,thenInsert){
  if(!currentData?.can_edit){vimVisualExit(cm);return}
  const linewise=vimVisual==='line';
  const sel=cm.listSelections()[0];
  let from=cm.getCursor(),to=from;
  if(sel){from=vimPosCmp(sel.anchor,sel.head)<=0?sel.anchor:sel.head;to=(from===sel.anchor)?sel.head:sel.anchor;}
  const text=cm.getSelection()||'';
  vimRegister=linewise?(text.endsWith('\n')?text:text+'\n'):text;
  vimRegisterLinewise=linewise;
  vimVisual=null;vimVisualAnchor=null;updateVimUi();
  if(linewise){
    const a=from.line,b=to.line,last=cm.lineCount()-1;
    if(thenInsert){
      cm.replaceRange('',{line:a,ch:0},{line:b,ch:(cm.getLine(b)||'').length},'+vim');
      cm.setCursor({line:a,ch:0});setVimInputMode('insert',cm);return;
    }
    if(a<=0&&b>=last)cm.replaceRange('',{line:0,ch:0},{line:last,ch:(cm.getLine(last)||'').length},'+vim');
    else if(b<last)cm.replaceRange('',{line:a,ch:0},{line:b+1,ch:0},'+vim');
    else cm.replaceRange('',{line:a-1,ch:(cm.getLine(a-1)||'').length},{line:b,ch:(cm.getLine(b)||'').length},'+vim');
    cm.setCursor({line:Math.min(a,cm.lineCount()-1),ch:0});
  }else{
    cm.replaceRange('',from,to,'+vim');cm.setCursor(from);
    if(thenInsert){setVimInputMode('insert',cm);return}
  }
  if(vimInputMode==='normal'&&mode==='source')refreshVimNormalLinks();
  vimEnsureCursorVisible(cm);
}
function handleVimKey(cm,e,viewName){
  if(mode!==viewName)return;
  const editable=!!currentData?.can_edit;
  if(vimInputMode==='insert'){
    // Do not steal keys from an active Japanese/IME composition.  Some
    // browsers report keyCode 229 instead of a normal key while composing.
    if(e.isComposing||vimImeComposing.has(cm)||e.keyCode===229)return;
    if(e.key==='Escape'){
      const ended=Number(vimImeEndedAt.get(cm)||0);
      if(ended&&performance.now()-ended<90){
        // Some Japanese IMEs emit compositionend immediately before the
        // Escape keydown that closed conversion. Consume that Escape only;
        // a deliberate next Escape enters NORMAL.
        e.preventDefault();e.stopPropagation();return;
      }
      e.preventDefault();e.stopPropagation();
      setVimInputMode('normal',cm);
      return;
    }
    if(e.key==='Tab'&&tableCellMove(cm,e.shiftKey?-1:1)){e.preventDefault();e.stopPropagation();return}
    if(e.key==='Tab'){
      // Tab uses the same link-to-link navigation in both editor input modes.
      // Leave ordinary Tab behavior intact when the document has no links.
      if(vimAllLinks(cm).length){e.preventDefault();e.stopPropagation();vimJumpLink(cm,e.shiftKey?-1:1);return}
    }
    return;
  }
  // NORMAL mode is available even on somebody else's read-only note.
  // Navigation/copy commands work there; mutating Vim commands do not.
  if(e.ctrlKey&&String(e.key).toLowerCase()==='r'){
    if(editable){e.preventDefault();cm.execCommand('redo');vimEnsureCursorVisible(cm)}
    return;
  }
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  const key=e.key;
  e.preventDefault();e.stopPropagation();
  if(key==='Escape'){vimPendingCommand='';if(vimVisual)vimVisualExit(cm);return}
  // ---- VISUAL sub-mode: motions extend the selection; y/d/c/x operate on it ----
  if(vimVisual){
    if(key==='g'){if(vimPendingCommand==='g'){vimPendingCommand='';vimVisualMotion(cm,'goDocStart')}else vimPendingCommand='g';return}
    vimPendingCommand='';
    if(key==='v'){vimVisualEnter(cm,'char');return}
    if(key==='V'){vimVisualEnter(cm,'line');return}
    if(key==='h'||key==='ArrowLeft'){vimVisualMotion(cm,'goCharLeft');return}
    if(key==='j'||key==='ArrowDown'){vimVisualMotion(cm,'goLineDown');return}
    if(key==='k'||key==='ArrowUp'){vimVisualMotion(cm,'goLineUp');return}
    if(key==='l'||key==='ArrowRight'){vimVisualMotion(cm,'goCharRight');return}
    if(key==='w'){vimVisualMotion(cm,'goWordRight');return}
    if(key==='b'){vimVisualMotion(cm,'goWordLeft');return}
    if(key==='0'){vimVisualMotion(cm,'goLineStart');return}
    if(key==='^'){vimVisualMotion(cm,'goLineStartSmart');return}
    if(key==='$'){vimVisualMotion(cm,'goLineEnd');return}
    if(key==='G'){vimVisualMotion(cm,'goDocEnd');return}
    if(key==='o'){
      const h=cm.getCursor('head'),a=vimVisualAnchor||h;
      vimVisualAnchor={line:h.line,ch:h.ch};
      cm.setSelection(h,a,{scroll:false});vimSelExtend(cm);vimEnsureCursorVisible(cm);return;
    }
    if(key==='y'||key==='Enter'){vimVisualYank(cm);return}
    if(key==='d'||key==='x'||key==='Delete'){vimVisualDelete(cm,false);return}
    if(key==='c'||key==='s'){vimVisualDelete(cm,true);return}
    return; // any other key: stay in VISUAL
  }
  if(key==='ArrowLeft'){vimPendingCommand='';vimMove(cm,'goCharLeft');return}
  if(key==='ArrowDown'){vimPendingCommand='';vimMove(cm,'goLineDown');return}
  if(key==='ArrowUp'){vimPendingCommand='';vimMove(cm,'goLineUp');return}
  if(key==='ArrowRight'){vimPendingCommand='';vimMove(cm,'goCharRight');return}
  if(key==='Tab'){vimPendingCommand='';vimJumpLink(cm,e.shiftKey?-1:1);return}
  if(key==='Enter'){vimPendingCommand='';if(!vimOpenCursorLink(cm))vimMove(cm,'goLineDown');return}
  if(key==='Backspace'){vimPendingCommand='';navigateBack().catch(console.error);return}
  if(vimPendingCommand==='g'){vimPendingCommand='';if(key==='g')vimMove(cm,'goDocStart');return}
  if(vimPendingCommand==='d'){vimPendingCommand='';if(key==='d'&&editable){vimDeleteLine(cm);vimEnsureCursorVisible(cm)}return}
  if(vimPendingCommand==='y'){
    vimPendingCommand='';
    if(key==='n'){copyCurrentNoteLink().catch(err=>status(err.message));return}
    if(key==='y'){vimYankLine(cm);return}
    return;
  }
  if(vimPendingCommand==='n'){
    vimPendingCommand='';
    if(key==='n'){openNewNodeDialog();return}
    if(key==='p'){openEdgeDialog('outgoing',true).catch(err=>status(err.message));return}
    if(key==='c'){openEdgeDialog('incoming',true).catch(err=>status(err.message));return}
    if(key==='x'&&editable){toggleTaskAtCursor(cm);return}
    if(key==='t'&&editable){makeTaskAtCursor(cm);return}
    if(key==='d'&&currentData?.can_edit&&!currentData?.is_index){deleteCurrentNote().catch(err=>status(err.message));return}
    return;
  }
  if(vimPendingCommand==='m'){vimPendingCommand='';if(key==='t'&&editable){insertMarkdownTable(cm);return}return}
  if(vimPendingCommand==='e'){vimPendingCommand='';if(key==='m'){openOrganizeEdgesDialog(vimLinkFileAtCursor(cm)).catch(err=>status(err.message));return}return}
  if(key==='g'){vimPendingCommand='g';return}
  if(key==='d'){vimPendingCommand='d';return}
  if(key==='y'){vimPendingCommand='y';return}
  if(key==='n'){vimPendingCommand='n';return}
  if(key==='m'){vimPendingCommand='m';return}
  if(key==='e'){vimPendingCommand='e';return}
  if(key==='h'){vimMove(cm,'goCharLeft');return}
  if(key==='j'){vimMove(cm,'goLineDown');return}
  if(key==='k'){vimMove(cm,'goLineUp');return}
  if(key==='l'){vimMove(cm,'goCharRight');return}
  if(key==='w'){vimMove(cm,'goWordRight');return}
  if(key==='b'){vimMove(cm,'goWordLeft');return}
  if(key==='0'){vimMove(cm,'goLineStart');return}
  if(key==='^'){vimMove(cm,'goLineStartSmart');return}
  if(key==='$'){vimMove(cm,'goLineEnd');return}
  if(key==='G'){vimMove(cm,'goDocEnd');return}
  if(key==='v'){vimVisualEnter(cm,'char');return}
  if(key==='V'){vimVisualEnter(cm,'line');return}
  if(!editable)return;
  if(key==='i'){setVimInputMode('insert',cm);return}
  if(key==='a'){cm.execCommand('goCharRight');setVimInputMode('insert',cm);return}
  if(key==='A'){cm.execCommand('goLineEnd');setVimInputMode('insert',cm);return}
  if(key==='I'){cm.execCommand('goLineStartSmart');setVimInputMode('insert',cm);return}
  if(key==='o'){cm.execCommand('goLineEnd');cm.replaceSelection('\n','end','+vim');setVimInputMode('insert',cm);return}
  if(key==='O'){cm.execCommand('goLineStart');cm.replaceSelection('\n','start','+vim');cm.execCommand('goLineUp');setVimInputMode('insert',cm);return}
  if(key==='x'){cm.execCommand('delCharAfter');vimEnsureCursorVisible(cm);return}
  if(key==='u'){cm.execCommand('undo');vimEnsureCursorVisible(cm);return}
  if(key==='p'){vimPaste(cm,false);vimEnsureCursorVisible(cm);return}
  if(key==='P'){vimPaste(cm,true);vimEnsureCursorVisible(cm);return}
}

bodyEditor.on('keydown',(cm,e)=>handleVimKey(cm,e,'edit'));
editor.on('keydown',(cm,e)=>handleVimKey(cm,e,'source'));
$('vimIndicator').onclick=()=>setVimInputMode(vimInputMode==='normal'?'insert':'normal',editor);
$('taskBtn').onclick=async()=>{if(!currentData?.can_edit)return;await switchMode('source');makeTaskAtCursor(editor);setVimInputMode('insert',editor);editor.focus()};
$('tableBtn').onclick=async()=>{if(!currentData?.can_edit)return;await switchMode('source');insertMarkdownTable(editor);setVimInputMode('insert',editor);editor.focus()};
$('viewModeToggle').addEventListener('click',toggleViewMode);
window.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&!e.altKey&&!e.shiftKey&&String(e.key).toLowerCase()==='e'){
    if(document.querySelector('dialog[open]')||activeSocialView!=='network'||!currentData)return;
    const active=document.activeElement;
    const inCodeMirror=!!active?.closest?.('.CodeMirror');
    const isTextControl=['INPUT','TEXTAREA','SELECT'].includes(active?.tagName||'')||active?.isContentEditable;
    if(isTextControl&&!inCodeMirror)return;
    e.preventDefault();e.stopPropagation();
    // Ctrl+E opens Source ready for normal typing. Esc remains available for
    // users who explicitly want Vim NORMAL mode.
    toggleViewMode().catch(console.error);return;
  }
},true);
window.addEventListener('keydown',e=>{
  if(mode!=='organize'||document.querySelector('dialog[open]'))return;
  const active=document.activeElement;
  const tag=active?.tagName||'';
  const isFormControl=['INPUT','TEXTAREA','SELECT','BUTTON'].includes(tag);
  if(e.key==='Tab'){
    // 整理ビューでは Tab / Shift+Tab の対象をノードリンクだけに限定する。
    // select・button などに現在フォーカスがあっても、次の Tab でリンク選択へ戻す。
    const links=organizeLinks();
    e.preventDefault();
    if(!links.length)return;
    const activeLink=(tag==='A'&&active?.dataset?.file)?active:null;
    let base=activeLink?links.indexOf(activeLink):organizeLinkIndex;
    if(base<0)base=e.shiftKey?0:-1;
    selectOrganizeLink(base+(e.shiftKey?-1:1));return;
  }
  if(e.key==='Enter'){
    if(isFormControl)return;
    const links=organizeLinks();
    let a=(tag==='A'&&active?.dataset?.file)?active:null;
    if(!a&&organizeLinkIndex>=0)a=links[organizeLinkIndex];
    if(a?.dataset?.file){e.preventDefault();openFile(a.dataset.file).catch(console.error)}
    return;
  }
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){
    if(isFormControl)return;
    e.preventDefault();const direction=e.key==='ArrowDown'?1:-1;const sections=organizeH2Sections();if(sections.length)moveOrganizeSection(direction);else $('organizeWrap').scrollBy({top:direction*90,behavior:'smooth'});return;
  }
  if(e.key==='Backspace'){
    if(isFormControl)return;
    if(navigationTrail.length>1){e.preventDefault();navigateBack().catch(console.error)}
  }
});
async function deleteCurrentNote(){
  if(!currentData?.can_edit||currentData?.is_index)return;
  if(!confirm('「'+(currentData.title||current)+'」を削除しますか？この操作は元に戻せません。'))return;
  await flushAutosave();const d=await api('/api/delete-notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files:[current]})});
  if((d.deleted||[]).includes(current)){navigationTrail=[];await refreshFiles();await openFile(profile.index_file,{record:false});pushTrail(current,currentData.title);status('ノートを削除しました')}
}
$('deleteCurrentBtn').onclick=()=>deleteCurrentNote().catch(e=>status(e.message));
$('nodeSelectBtn').onclick=()=>{nodeSelectionMode=!nodeSelectionMode;if(!nodeSelectionMode)selectedNodeFiles.clear();renderFiles()};
$('nodeDeleteBtn').onclick=()=>{
  if(!selectedNodeFiles.size)return;
  const byName=new Map(cachedFiles.map(f=>[f.name,f]));
  const items=[...selectedNodeFiles].map(n=>byName.get(n)).filter(Boolean);
  $('deleteNotesList').innerHTML=items.map(f=>'<div>• '+escapeHtml(f.title)+'</div>').join('');
  $('deleteNotesDialog').showModal();
};
$('deleteNotesConfirm').onclick=async()=>{
  const files=[...selectedNodeFiles];if(!files.length)return;
  try{
    await flushAutosave();
    const d=await api('/api/delete-notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files})});
    $('deleteNotesDialog').close();selectedNodeFiles.clear();nodeSelectionMode=false;
    await refreshFiles();
    const deleted=new Set(d.deleted||[]);
    if(current&&deleted.has(current)){navigationTrail=[];await openFile(profile.index_file,{record:false});pushTrail(current,currentData.title)}
    else if(current){const refreshed=await api('/api/file?name='+encodeURIComponent(current)+'&voter='+encodeURIComponent(voterId));currentData=refreshed;setEditorsFromRaw(refreshed.content);dirty=false;renderEditEdges();updateFileTitle();updateAuthorBar();updateEditPermissions();updateContextAction();if(mode==='organize')renderOrganize();queueGraph()}
    status((d.deleted||[]).length+'件のノートを削除しました');
  }catch(e){status(e.message)}
};
$('nodeSort').addEventListener('change',renderFiles);
const BASE_RELATIONS=['カテゴリー','ノート','賛同','否定','質問','回答','関連','言及','雑談'];
let selectedRelation='カテゴリー';
function pageRelations(){
  const out=[];
  for(const line of editorText().split('\n')){
    const info=relationLineInfo(line);
    if(info&&info.relation&&!out.includes(info.relation))out.push(info.relation);
  }
  return out;
}
function chooseRelation(name){
  selectedRelation=name;
  $('customRelationWrap').style.display=name==='__custom__'?'grid':'none';
  document.querySelectorAll('.relationChoice').forEach(b=>b.classList.toggle('selected',b.dataset.relation===name));
  if(name==='__custom__')setTimeout(()=>$('customRelation').focus(),0);
}
async function startNewRootNote(){
  if(!requireAuth('自分のノートを書くにはログインまたは新規登録してください',()=>startNewRootNote()))return;
  showNetwork();
  if(!profile?.index_file){status('自分のIndexが見つかりません');return}
  if(current!==profile.index_file)await openFile(profile.index_file,{record:false});
  openNewNodeDialog();
}
function openNewNodeDialog(){
  if(isGuest()){showAuth('自分のノートを書くにはログインまたは新規登録してください',()=>startNewRootNote());return}
  if(!currentData?.can_edit){status('新しいノードは自分のノートから作成してください');return}
  $('newTitle').value='';$('customRelation').value='';
  renderRelationChoices();
  $('newDialog').showModal();
  setTimeout(()=>$('newTitle').focus(),0);
}
function renderRelationChoices(){
  const root=$('relationChoices');root.innerHTML='';
  const page=new Set(pageRelations());
  const names=[...BASE_RELATIONS];if(profile?.local_mode)names.push('公開版');
  // Legacy/custom relations already present on the page remain selectable,
  // while the default vocabulary stays intentionally small and predictable.
  for(const name of page){if(!names.includes(name))names.push(name)}
  for(const name of names){
    const b=document.createElement('button');b.type='button';b.className='relationChoice'+(page.has(name)?' pageItem':'');b.dataset.relation=name;b.textContent=name;b.onclick=()=>chooseRelation(name);root.appendChild(b);
  }
  const other=document.createElement('button');other.type='button';other.className='relationChoice';other.dataset.relation='__custom__';other.textContent='＋ その他';other.onclick=()=>chooseRelation('__custom__');root.appendChild(other);
  chooseRelation(names[0]);
}
function fillSelect(sel,items,emptyText){
  sel.innerHTML='';
  if(!items.length){const o=document.createElement('option');o.value='';o.textContent=emptyText;sel.appendChild(o);sel.disabled=true;return}
  sel.disabled=false;for(const x of items){const o=document.createElement('option');o.value=x.file;o.textContent=x.title;sel.appendChild(o)}
}
function currentChildCandidates(){
  return (currentData?.incoming||[]).map(e=>({...e,label:e.title||e.file,can_move:!!e.can_move}));
}
function currentCategoryCandidates(){
  return currentChildCandidates().filter(e=>relIs(e.relation,'カテゴリー'));
}
function refreshOrganizeEdgePermission(){
  const sel=$('organizeEdgeItem'),opt=sel.options[sel.selectedIndex];const canMove=opt?.dataset?.canMove==='1';
  const move=$('organizeEdgesForm').querySelector('input[name="organizeEdgeMode"][value="move"]');
  const add=$('organizeEdgesForm').querySelector('input[name="organizeEdgeMode"][value="add"]');
  move.disabled=!canMove;if(!canMove&&move.checked)add.checked=true;
  $('organizeEdgePermissionHint').textContent=canMove?'自分が作ったリンクなので「移動」または「追加」を選べます。':'他の人が作ったリンクなので「追加」のみ可能です。';
  if(opt?.dataset?.relation)$('organizeEdgeRelation').value=BASE_RELATIONS.includes(opt.dataset.relation)?opt.dataset.relation:'関連';
}
async function openOrganizeEdgesDialog(prefillFile=''){
  if(!profile?.id){showAuth('リンクを整理するにはログインまたは新規登録してください',()=>openOrganizeEdgesDialog(prefillFile));return}
  await flushAutosave();
  currentData=await api('/api/file?name='+encodeURIComponent(current)+'&voter='+encodeURIComponent(voterId));
  const items=currentChildCandidates(),sel=$('organizeEdgeItem');sel.innerHTML='';
  for(const e of items){const o=document.createElement('option');o.value=e.file;o.textContent=(e.relation||'関連')+' · '+(e.title||e.file)+' · @'+(authorFor(e.file)?.username||'');o.dataset.relation=e.relation||'関連';o.dataset.canMove=e.can_move?'1':'0';o.dataset.edgeId=String(e.edge_id||0);o.dataset.edgeKind=e.edge_kind||'owner';sel.appendChild(o)}
  sel.disabled=!items.length;
  if(prefillFile&&items.some(x=>x.file===prefillFile))sel.value=prefillFile;
  const cats=currentCategoryCandidates().filter(x=>x.file!==sel.value);fillSelect($('organizeEdgeCategory'),cats,'既存カテゴリーはありません');
  $('organizeEdgeNewCategory').value='';
  $('organizeEdgeSubmit').disabled=!items.length;
  sel.onchange=()=>{const cats2=currentCategoryCandidates().filter(x=>x.file!==sel.value);fillSelect($('organizeEdgeCategory'),cats2,'既存カテゴリーはありません');refreshOrganizeEdgePermission()};
  refreshOrganizeEdgePermission();$('organizeEdgesDialog').showModal();setTimeout(()=>sel.focus(),0);
}
$('contextActionBtn').onclick=()=>openOrganizeEdgesDialog('').catch(e=>status(e.message));
$('organizeEdgeSubmit').onclick=async()=>{
  const item=$('organizeEdgeItem').value;if(!item)return;
  const modeEl=$('organizeEdgesForm').querySelector('input[name="organizeEdgeMode"]:checked');const action=modeEl?.value||'add';
  const relation=$('organizeEdgeRelation').value||'ノート';const selectedOpt=$('organizeEdgeItem').options[$('organizeEdgeItem').selectedIndex];const originalRelation=selectedOpt?.dataset?.relation||relation;const edgeId=Number(selectedOpt?.dataset?.edgeId||0);const category=$('organizeEdgeCategory').disabled?'':$('organizeEdgeCategory').value;const newCategory=$('organizeEdgeNewCategory').value.trim();
  if(!category&&!newCategory){status('既存カテゴリーを選ぶか、新しいカテゴリー名を入力してください');return}
  try{
    const d=await api('/api/organize-link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({container:current,item,category,new_category:newCategory,action,relation,original_relation:originalRelation,edge_id:edgeId})});
    $('organizeEdgesDialog').close();currentData=d.current;setEditorsFromRaw(currentData.content);dirty=false;renderEditEdges();if(mode==='organize')renderOrganize();await refreshFiles();queueGraph();status(action==='move'?'リンクを移動しました':'カテゴリーへ追加しました');
  }catch(e){status(e.message)}
};
function vimLinkFileAtCursor(cm){const cur=cm.getCursor(),hit=markdownLinkAt(cm.getLine(cur.line)||'',cur.ch);return hit?.file||''}

function currentEdgeRelation(){const v=$('edgeRelation').value;return v==='__custom__'?$('edgeCustomRelation').value.trim():v}
$('edgeRelation').addEventListener('change',()=>{$('edgeCustomWrap').style.display=$('edgeRelation').value==='__custom__'?'grid':'none'});
async function loadEdgeCandidates(){
  const q=$('edgeSearch').value.trim();const scope=edgeDialogMode==='incoming'?'mine':'all';
  const d=await api('/api/search?scope='+scope+'&limit=80&q='+encodeURIComponent(q));const sel=$('edgeTarget');sel.innerHTML='';
  const items=(d.results||[]).filter(x=>x.file!==current);
  for(const x of items){const o=document.createElement('option');o.value=x.file;o.textContent=(x.title||x.file)+' · @'+(x.author?.username||'');sel.appendChild(o)}
  $('edgeSubmit').disabled=!items.length&&!$('edgePaste').value.trim();
}
async function openEdgeDialog(direction,preferNew=false){if(direction==='outgoing'&&currentData?.is_index){status('IndexにはParentを追加しません');return}
  if(isGuest()){showAuth(direction==='incoming'?'このノートにつながる自分のノートを書くにはログインまたは新規登録してください':'関係を追加するにはログインまたは新規登録してください',()=>openEdgeDialog(direction,preferNew));return}
  edgeDialogMode=direction;$('edgeDialogTitle').textContent=direction==='outgoing'?'Parentとの関係を追加':'Childとの関係を追加';
  $('edgeDialogHint').textContent=direction==='outgoing'?(currentData?.can_edit?'このノート自身のParent関係として追加します。':'このノートの所有者ではないため、あなたが追加したParentとして別管理され、本人のParentより下に表示されます。'):'自分のノート側に、現在のノートとの関係を追加します。現在のノート自体は編集しません。';
  $('edgeSearchLabel').firstChild.textContent=direction==='outgoing'?'リンク先を検索':'自分のリンク元ノートを検索';$('edgeSearch').value='';$('edgePaste').value='';$('edgeNewTitle').value='';$('edgeCustomRelation').value='';$('edgeRelation').value='関連';$('edgeCustomWrap').style.display='none';$('edgeTarget').innerHTML='<option>読み込み中...</option>';$('edgeDialog').showModal();await loadEdgeCandidates();setTimeout(()=>(preferNew?$('edgeNewTitle'):$('edgeSearch')).focus(),0);
}
$('edgeSearch').addEventListener('input',()=>{if(edgeSearchTimer)clearTimeout(edgeSearchTimer);edgeSearchTimer=setTimeout(()=>loadEdgeCandidates().catch(e=>status(e.message)),180)});
$('edgePaste').addEventListener('input',()=>{$('edgeSubmit').disabled=!$('edgePaste').value.trim()&&!$('edgeTarget').value});
$('edgeNewBtn').onclick=async()=>{
  const relation=currentEdgeRelation(),title=$('edgeNewTitle').value.trim();
  if(!relation){status('関係名を入力してください');return}
  if(!title){status('新しいノートのタイトルを入力してください');$('edgeNewTitle').focus();return}
  try{
    await flushAutosave();
    const d=await api('/api/edge-new',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({direction:edgeDialogMode,current,relation,title})});
    $('edgeDialog').close();await refreshFiles();await openFile(d.file);await switchMode('source');status(edgeDialogMode==='incoming'?'Childノートを作成しました':'Parentノートを作成しました');
  }catch(err){status(err.message)}
};
$('edgeForm').addEventListener('submit',async e=>{e.preventDefault();const relation=currentEdgeRelation();if(!relation){status('関係名を入力してください');return}const file=$('edgeTarget').value||'';const reference=$('edgePaste').value.trim();if(!file&&!reference){status('ノートを選択するかリンクを貼り付けてください');return}try{await flushAutosave();const d=await api('/api/edge-add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({direction:edgeDialogMode,current,relation,file,reference})});currentData=d;setEditorsFromRaw(d.content);dirty=false;renderEditEdges();$('edgeDialog').close();await refreshFiles();queueGraph();if(mode==='organize')renderOrganize();status('エッジを追加しました')}catch(err){status(err.message)}});

function refocusVimAfterDialog(){
  if(vimInputMode!=='normal'||mode!=='source')return;
  setTimeout(()=>{try{editor.focus();vimEnsureCursorVisible(editor)}catch(_){}},0);
}
$('newDialog').addEventListener('close',refocusVimAfterDialog);
$('edgeDialog').addEventListener('close',refocusVimAfterDialog);

$('profileBtn').onclick=()=>{if(profile?.local_mode){status('Localはアカウントなしで利用できます');return}if(isGuest()){status('ゲストとして閲覧中です。書き込みやいいねをするときにログインできます');return}renderProfile(profile.id).catch(e=>status(e.message))};
$('profileForm').addEventListener('submit',async e=>{
  e.preventDefault();
  profile=await api('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:$('profileDisplayName').value.trim(),bio:$('profileBio').value.trim()})});
  $('profileDialog').close();updateProfileUi();if(currentData?.author?.id===profile.id){currentData.author={...currentData.author,...profile};updateAuthorBar();if(mode==='organize')renderOrganize()}status('プロフィールを保存しました');
});
function showAuth(message='',resume=null){
  if(resume)pendingAuthAction=resume;
  $('authPrompt').textContent=message||(runtimeLocalMode?'Webへ共有・同期するにはWebアカウントへ接続してください':'この操作にはログインまたは登録が必要です');
  $('authGate').classList.remove('hidden');$('authError').textContent='';
  if($('localSyncAuth'))$('localSyncAuth').hidden=!runtimeLocalMode;
  if($('localPasswordAuth'))$('localPasswordAuth').hidden=runtimeLocalMode;
  if($('authCancelBtn')){$('authCancelBtn').style.display='inline-block';$('authCancelBtn').textContent=runtimeLocalMode?'キャンセル':'ゲストで続ける'}
  setTimeout(()=>{if(runtimeLocalMode)$('authWebUsername')?.focus();else $('authUsername')?.focus()},0);
}
function hideAuth(){$('authGate').classList.add('hidden');$('authError').textContent=''}
function requireAuth(message,resume){if(!isGuest())return true;showAuth(message,resume);return false}
function requireWebConnection(message,resume){
  if(!profile?.local_mode||profile?.web_connected)return true;
  showAuth(message||'Webへ共有・同期するにはWebアカウントへ接続してください',resume);
  return false;
}
async function finishAuthentication(d){
  profile=d.profile;hideAuth();updateProfileUi();await refreshFiles();
  const resume=pendingAuthAction;pendingAuthAction=null;
  if(resume){await resume();return}
  if(profile?.index_file){await openFile(profile.index_file,{record:false,replaceUrl:true});navigationTrail=[];pushTrail(current,currentData.title);showNetwork()}
}
async function enterGuestMode(preserveCurrent=false){
  profile={...GUEST_PROFILE};hideAuth();updateProfileUi();
  try{await refreshFiles()}catch(_) {cachedFiles=[];renderFiles()}
  if(preserveCurrent&&current){try{currentData=await api('/api/file?name='+encodeURIComponent(current));setEditorsFromRaw(currentData.content);dirty=false;updateAuthorBar();updateEditPermissions();if(mode==='organize')renderOrganize();showNetwork();return}catch(_){}}
  const requested=requestedNoteFromUrl();
  if(requested){try{await openFile(requested,{record:false,replaceUrl:true});navigationTrail=[];pushTrail(current,currentData.title);showNetwork();return}catch(_){}}
  current=null;currentData=null;navigationTrail=[];showSocial('home').catch(e=>status(e.message));
}
function mainNavLabel(view){return ({home:'ホーム',communities:'コミュニティ',search:'検索',dm:'メッセージ',data:'データ',admin:'管理'})[view]||'メニュー'}
function setTopNav(view){
  const menu=$('mainNavMenu'),btn=$('mainNavBtn');if(menu)menu.querySelectorAll('[data-main-nav]').forEach(b=>b.classList.toggle('active',b.dataset.mainNav===view));
  if(btn)btn.textContent=(view?mainNavLabel(view):'メニュー')+' ▾';
}
function closeNavMenu(){const menu=$('mainNavMenu'),btn=$('mainNavBtn');if(menu)menu.hidden=true;if(btn)btn.setAttribute('aria-expanded','false')}
function stopSocialPoll(){if(socialPollTimer){clearInterval(socialPollTimer);socialPollTimer=null}}
function showNetwork(){
  stopSocialPoll();activeSocialView='network';setTopNav('');$('socialView').style.display='none';$('authorBar').style.display='flex';$('docBar').style.display='flex';$('layout').style.display='grid';
  queueGraph(80);if(mode==='source')setTimeout(()=>editor.refresh(),0);
}
async function showSocial(view){
  stopSocialPoll();activeSocialView=view;setTopNav(view);$('authorBar').style.display='none';$('docBar').style.display='none';$('layout').style.display='none';$('socialView').style.display='block';
  if(view==='home'){if(!isGuest()&&profile?.id){await renderProfile(profile.id);return}else await renderHome();}
  else if(view==='latest'||view==='popular')await renderFeed(view);
  else if(view==='communities')await renderCommunities();
  else if(view==='search')await renderSearch();
  else if(view==='dm')await renderDmHome();
  else if(view==='data')await renderDataPage();
  else if(view==='admin')await renderAdminPage();
}
function socialAuthorHtml(u){return '<button type="button" class="feedAuthor profileLink" data-profile-user="'+Number(u.id||0)+'">'+avatarHtml(u)+'<span class="feedAuthorText"><span class="feedAuthorName">'+escapeHtml(u.display_name||u.username||'')+'</span><span class="feedAuthorHandle">@'+escapeHtml(u.username||'')+'</span></span></button>'}
function feedCardHtml(p){return '<article class="feedCard" data-post="'+escapeHtml(p.file)+'">'+socialAuthorHtml(p.author)+'<div class="feedTitle" data-open-post="'+escapeHtml(p.file)+'">'+escapeHtml(p.title)+'</div>'+(p.image_url?'<img class="inlineImage" src="'+escapeHtml(p.image_url)+'" alt="">':'')+(p.excerpt?'<div class="feedExcerpt">'+escapeHtml(p.excerpt)+'</div>':'')+'<div class="feedActions"><button type="button" data-like-post="'+escapeHtml(p.file)+'">'+(p.liked?'♥':'♡')+' '+p.like_count+'</button><span class="feedTime">'+escapeHtml(formatLocalDateTime(p.created_at))+' ・ 接続 '+Number(p.node_count||0)+'</span></div></article>'}
function bindProfileLinks(root){root.querySelectorAll('[data-profile-user]').forEach(el=>el.onclick=e=>{e.stopPropagation();renderProfile(Number(el.dataset.profileUser)).catch(err=>status(err.message))})}
async function toggleLike(file,button=null){
  if(!requireAuth('いいねするにはログインまたは新規登録してください',()=>toggleLike(file,button)))return;
  const d=await api('/api/like',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file})});
  if(button)button.textContent=(d.liked?'♥':'♡')+' '+d.like_count;
  if(current===file){currentData.liked=d.liked;currentData.like_count=d.like_count;updateAuthorBar()}
}
function bindFeedActions(root){
  root.querySelectorAll('[data-open-post]').forEach(el=>el.onclick=async()=>{showNetwork();await openFile(el.dataset.openPost)});
  root.querySelectorAll('[data-like-post]').forEach(b=>b.onclick=async e=>{e.stopPropagation();await toggleLike(b.dataset.likePost,b)});
  bindProfileLinks(root);
}
function toggleSocialFullscreen(){const root=$('socialContent');root.classList.toggle('fullscreen');document.body.classList.toggle('socialFullscreen',root.classList.contains('fullscreen'));const b=$('socialExpandBtn');if(b)b.textContent=root.classList.contains('fullscreen')?'縮小':'拡大'}
function headerWithExpand(title,extra=''){return '<div class="socialHeader"><h2>'+escapeHtml(title)+'</h2>'+extra+'<button id="socialExpandBtn" class="expandBtn" type="button">拡大</button></div>'}
function bindExpand(){const b=$('socialExpandBtn');if(b)b.onclick=toggleSocialFullscreen}
function markdownPreview(markdown,maxChars=620,maxLines=14){
  const lines=String(markdown||'').replace(/\r\n?/g,'\n').split('\n');let out=[],n=0;
  for(const line of lines){if(out.length>=maxLines)break;const add=line.length+1;if(n+add>maxChars){const remain=Math.max(0,maxChars-n);if(remain>0)out.push(line.slice(0,remain));break}out.push(line);n+=add}
  let text=out.join('\n').trimEnd();if(String(markdown||'').trim().length>text.trim().length)text+='\n\n…';return text;
}
function sectionHead(title,buttonId,label='すべて見る'){return '<div class="sectionHead"><h3>'+escapeHtml(title)+'</h3><button id="'+buttonId+'" class="sectionMore" type="button">'+escapeHtml(label)+' →</button></div>'}
function uniqueIndexChildren(items){
  const seen=new Set(),out=[];
  for(const x of (items||[])){
    const file=String(x?.file||'').trim();if(!file||seen.has(file))continue;seen.add(file);
    out.push({file,title:String(x?.title||file.replace(/\.md$/,'')),relation:String(x?.relation||'ノート')});
  }
  return out;
}
function markdownIndexChildren(md){
  const out=[],re=/\[((?:\\.|[^\]\\])+)\]\(([^)\s]+\.md)(?:\s+"[^"]*")?\)/g;let m;
  while((m=re.exec(String(md||'')))){let file=m[2].split('/').pop();try{file=decodeURIComponent(file)}catch(_){}out.push({file,title:m[1].replace(/\\([\[\]\\])/g,'$1'),relation:'ノート'})}
  return uniqueIndexChildren(out);
}
function indexChildPreviewHtml(items,limit=6){
  const rows=uniqueIndexChildren(items);if(!rows.length)return '';
  return '<div class="indexChildPreview"><div class="indexChildTitle">Child</div><div class="indexChildList">'+rows.slice(0,limit).map(x=>'<button class="indexChildItem" type="button" data-index-child="'+escapeHtml(x.file)+'"><span class="indexChildRelation">'+escapeHtml(x.relation)+'</span><span>'+escapeHtml(x.title)+'</span></button>').join('')+(rows.length>limit?'<div class="indexChildMore">ほか '+(rows.length-limit)+' 件 · Indexを開くとすべて表示</div>':'')+'</div></div>';
}
function bindIndexChildLinks(root){
  root?.querySelectorAll?.('[data-index-child]').forEach(b=>b.onclick=async e=>{e.preventDefault();e.stopPropagation();showNetwork();await openFile(b.dataset.indexChild)});
}

async function renderHome(){
  const root=$('socialContent');root.classList.remove('fullscreen');document.body.classList.remove('socialFullscreen');root.innerHTML=headerWithExpand('ホーム')+'<div class="emptyState">読み込み中...</div>';bindExpand();
  const [latest,popular]=await Promise.all([api('/api/feed?mode=latest'),api('/api/feed?mode=popular')]);
  root.innerHTML=headerWithExpand('ホーム','<button id="homeCreateNoteBtn" type="button">＋ ノートを作成</button>')+'<div class="homeSections"><section class="profileSection">'+sectionHead('最新','homeLatestAll')+'<div class="sectionFeed previewFeed">'+(latest.posts.length?latest.posts.slice(0,3).map(feedCardHtml).join(''):'<div class="emptyState">投稿がありません</div>')+'</div></section><section class="profileSection">'+sectionHead('人気','homePopularAll')+'<div class="sectionFeed previewFeed">'+(popular.posts.length?popular.posts.slice(0,3).map(feedCardHtml).join(''):'<div class="emptyState">投稿がありません</div>')+'</div></section></div>';bindExpand();bindFeedActions(root);
  $('homeCreateNoteBtn').onclick=()=>startNewRootNote().catch(e=>status(e.message));$('homeLatestAll').onclick=e=>{e.stopPropagation();showSocial('latest').catch(err=>status(err.message))};$('homePopularAll').onclick=e=>{e.stopPropagation();showSocial('popular').catch(err=>status(err.message))};
}
async function renderProfileFeed(userId,feedMode){
  stopSocialPoll();activeSocialView='profile';activeProfileUserId=Number(userId);setTopNav('');$('authorBar').style.display='none';$('docBar').style.display='none';$('layout').style.display='none';$('socialView').style.display='block';const root=$('socialContent');root.innerHTML='<div class="emptyState">読み込み中...</div>';
  const [d,feed]=await Promise.all([api('/api/user?id='+Number(userId)),api('/api/feed?mode='+encodeURIComponent(feedMode)+'&user_id='+Number(userId))]);const u=d.user;
  root.innerHTML='<div class="socialHeader"><button id="profileFeedBack" class="socialBackBtn" type="button">← プロフィール</button><h2>'+escapeHtml(u.display_name||u.username)+'の'+(feedMode==='popular'?'人気':'最新')+'</h2><button id="socialExpandBtn" class="expandBtn" type="button">拡大</button></div><div class="feedList">'+(feed.posts.length?feed.posts.map(feedCardHtml).join(''):'<div class="emptyState">投稿がありません</div>')+'</div>';bindExpand();bindFeedActions(root);$('profileFeedBack').onclick=()=>renderProfile(userId).catch(e=>status(e.message));
}
async function renderFeed(mode){
  const root=$('socialContent');root.classList.remove('fullscreen');document.body.classList.remove('socialFullscreen');root.innerHTML=headerWithExpand(mode==='popular'?'人気の投稿':'最新の投稿')+'<div class="emptyState">読み込み中...</div>';bindExpand();
  const d=await api('/api/feed?mode='+encodeURIComponent(mode));
  root.innerHTML=headerWithExpand(mode==='popular'?'人気の投稿':'最新の投稿')+'<div class="feedList">'+(d.posts.length?d.posts.map(feedCardHtml).join(''):'<div class="emptyState">まだ投稿がありません</div>')+'</div>';bindExpand();bindFeedActions(root);
}
function escapeRegExp(s){return String(s).replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}
function highlightSearchText(text,terms){let html=escapeHtml(text||'');for(const term of (terms||[]).filter(Boolean).sort((a,b)=>b.length-a.length)){const safe=escapeHtml(term);if(!safe)continue;try{html=html.replace(new RegExp('('+escapeRegExp(safe)+')','gi'),'<mark class="searchHit">$1</mark>')}catch(_){}}return html}
async function loadSavedSearches(){if(isGuest())return [];try{return (await api('/api/saved-searches')).searches||[]}catch(_){return []}}
async function renderSearch(){
  const root=$('socialContent');const saved=await loadSavedSearches();
  root.innerHTML=headerWithExpand('検索')+'<div class="searchShell"><div class="searchBar" style="grid-template-columns:1fr"><input id="globalSearchInput" placeholder="My 猫 / person=Yurii / community=写真 / all AI" autocomplete="off"></div><div class="savedSearchBar">'+(isGuest()?'':'<button id="saveSearchBtn" type="button">検索条件を保存</button><select id="savedSearchSelect"><option value="">保存した検索...</option>'+saved.map(x=>'<option value="'+Number(x.id)+'" data-query="'+escapeHtml(x.query)+'">'+escapeHtml(x.name)+'</option>').join('')+'</select><button id="deleteSavedSearchBtn" type="button">削除</button>')+'</div><div class="searchHelp"><strong>条件も検索欄に書けます:</strong> <code>My</code> = 自分の投稿、<code>person=Yurii</code> = 人物、<code>community=写真</code> = コミュニティ、<code>all</code> = 全体。条件を書かなければ'+(isGuest()?'全体':'自分の投稿')+'を検索します。通常語句、<code>title:</code> <code>body:</code> <code>relation:</code> <code>-除外</code> <code>OR</code> も使えます。</div><div id="searchContext" class="searchContext"></div><div id="searchResults" class="searchResults"></div></div>';bindExpand();
  $('globalSearchInput').value=searchState.q||'';
  const queue=()=>{searchState.q=$('globalSearchInput').value;if(searchTimer)clearTimeout(searchTimer);searchTimer=setTimeout(()=>runSearch().catch(e=>status(e.message)),130)};
  $('globalSearchInput').oninput=queue;
  if($('savedSearchSelect'))$('savedSearchSelect').onchange=()=>{const o=$('savedSearchSelect').selectedOptions[0];if(!o?.value)return;$('globalSearchInput').value=o.dataset.query||'';searchState.q=$('globalSearchInput').value;runSearch().catch(e=>status(e.message))};
  if($('saveSearchBtn'))$('saveSearchBtn').onclick=async()=>{const q=$('globalSearchInput').value.trim();if(!q){status('保存する検索条件を入力してください');return}const name=prompt('この検索条件の名前',q.slice(0,40));if(!name)return;await api('/api/saved-searches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,query:q})});status('検索条件を保存しました');await renderSearch()};
  if($('deleteSavedSearchBtn'))$('deleteSavedSearchBtn').onclick=async()=>{const id=Number($('savedSearchSelect').value||0);if(!id)return;await api('/api/saved-search-delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});status('保存した検索条件を削除しました');await renderSearch()};
  await runSearch();setTimeout(()=>$('globalSearchInput')?.focus(),0);
}
async function runSearch(){
  const input=$('globalSearchInput'),box=$('searchResults');if(!input||!box)return;const q=input.value.trim();box.innerHTML='<div class="searchEmpty">検索中...</div>';
  const d=await api('/api/search?limit=150&q='+encodeURIComponent(q));const context=$('searchContext');if(context)context.textContent=(d.context_label||'')+' · '+d.count+'件';
  if(!d.results.length){box.innerHTML='<div class="searchEmpty">一致するノートがありません</div>';return}
  box.innerHTML=d.results.map(x=>'<article class="searchResult" data-search-file="'+escapeHtml(x.file)+'"><div class="searchResultHead">'+avatarHtml(x.author,'small')+'<span class="searchResultTitle">'+highlightSearchText(x.title,x.match_terms)+'</span><button type="button" class="searchResultAuthor profileLink" data-profile-user="'+Number(x.author?.id||0)+'">@'+escapeHtml(x.author?.username||'')+'</button></div><div class="searchResultSnippet">'+highlightSearchText(x.snippet||'',x.match_terms)+'</div><div class="searchResultMeta">'+escapeHtml(formatLocalDateTime(x.created_at))+(x.communities?.length?' · '+x.communities.map(c=>escapeHtml(c.name)).join(', '):'')+'</div></article>').join('');
  box.querySelectorAll('[data-search-file]').forEach(el=>el.onclick=async e=>{if(e.target.closest('[data-profile-user]'))return;showNetwork();await openFile(el.dataset.searchFile)});bindProfileLinks(box);
}
async function openSearch(scope='auto',communityId=0,userId=0,q=''){
  let prefix='';
  if(scope==='mine')prefix='My ';
  else if(scope==='all')prefix='all ';
  else if(scope==='community'&&communityId){try{const d=await api('/api/community?id='+Number(communityId));prefix='community='+JSON.stringify(d.community.name)+' '}catch(_){prefix='community='+Number(communityId)+' '}}
  else if(scope==='user'&&userId){try{const d=await api('/api/user?id='+Number(userId));prefix='person='+d.user.username+' '}catch(_){prefix='person='+Number(userId)+' '}}
  searchState={q:(prefix+(q||'')).trim(),scope:'auto',community_id:0,user_id:0};await showSocial('search');
}
async function renderProfile(userId){
  stopSocialPoll();activeSocialView='profile';activeProfileUserId=Number(userId);setTopNav(Number(userId)===Number(profile?.id)?'home':'');$('authorBar').style.display='none';$('docBar').style.display='none';$('layout').style.display='none';$('socialView').style.display='block';const root=$('socialContent');root.innerHTML='<div class="emptyState">読み込み中...</div>';
  const d=await api('/api/user?id='+Number(userId)),u=d.user,isMine=Number(u.id)===Number(profile.id);
  const [latest,popular,indexData]=await Promise.all([api('/api/feed?mode=latest&user_id='+Number(u.id)),api('/api/feed?mode=popular&user_id='+Number(u.id)),d.index_file?api('/api/file?name='+encodeURIComponent(d.index_file)).catch(()=>null):Promise.resolve(null)]);
  const actions=isMine?'<button id="profileEditBtn" type="button">プロフィール編集</button>':'<button id="profileFollowBtn" type="button">'+(d.following?'フォロー解除':'フォロー')+'</button><button id="profileDmBtn" type="button">メッセージ</button><button id="profileBlockBtn" type="button">ブロック</button><button id="profileReportBtn" type="button">'+(d.reported?'通報済み':'通報')+'</button>';
  root.innerHTML=headerWithExpand('プロフィール')+'<div class="profilePage"><section class="profileHero">'+avatarHtml(u,'large')+'<div class="profileHeroText"><div class="profileHeroName">'+escapeHtml(u.display_name||u.username)+'</div><div class="profileHeroHandle">@'+escapeHtml(u.username)+'</div><div class="profileHeroBio">'+escapeHtml(u.bio||'')+'</div><div class="profileActions">'+actions+'</div></div></section><div class="profileSections"><section class="profileSection"><h3>検索</h3><div class="profileQuickSearch"><input id="profileQuickSearchInput" placeholder="このプロフィールのノートを検索"><button id="profileQuickSearchBtn" type="button">検索</button></div></section><section id="profileIndexSection" class="profileSection navigable" tabindex="0">'+sectionHead('Index','profileIndexOpen','Indexを開く')+'<div id="profileIndexBody" class="profileIndexBody preview"></div><div id="profileIndexChildren"></div></section><section class="profileSection">'+sectionHead('最新','profileLatestAll')+'<div class="sectionFeed previewFeed" id="profileLatest">'+(latest.posts.length?latest.posts.slice(0,3).map(feedCardHtml).join(''):'<div class="emptyState">投稿がありません</div>')+'</div></section><section class="profileSection">'+sectionHead('人気','profilePopularAll')+'<div class="sectionFeed previewFeed" id="profilePopular">'+(popular.posts.length?popular.posts.slice(0,3).map(feedCardHtml).join(''):'<div class="emptyState">投稿がありません</div>')+'</div></section></div></div>';bindExpand();
  const openIndex=async()=>{if(!d.index_file){status('Indexがありません');return}showNetwork();await openFile(d.index_file)};
  const ix=$('profileIndexBody');if(indexData){const md=markdownPreview(bodyWithoutPureEdgeSections(indexData.content||''));renderMarkdownDocument(ix,md,{taskInteractive:false});ix.onclick=async e=>{const a=e.target.closest('a[data-file]');if(a){e.preventDefault();e.stopPropagation();showNetwork();await openFile(a.dataset.file)}};$('profileIndexChildren').innerHTML=indexChildPreviewHtml(indexData.incoming||[]);bindIndexChildLinks($('profileIndexChildren'))}else{ix.innerHTML='<div class="profileIndexMissing">Indexがありません</div>';$('profileIndexChildren').innerHTML=''};
  $('profileIndexOpen').onclick=e=>{e.stopPropagation();openIndex().catch(err=>status(err.message))};$('profileIndexSection').onclick=e=>{if(e.target.closest('button,a'))return;openIndex().catch(err=>status(err.message))};$('profileIndexSection').onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button,a')){e.preventDefault();openIndex().catch(err=>status(err.message))}};
  $('profileLatestAll').onclick=e=>{e.stopPropagation();renderProfileFeed(u.id,'latest').catch(err=>status(err.message))};$('profilePopularAll').onclick=e=>{e.stopPropagation();renderProfileFeed(u.id,'popular').catch(err=>status(err.message))};
  bindFeedActions(root);$('profileQuickSearchBtn').onclick=()=>openSearch('user',0,u.id,$('profileQuickSearchInput').value.trim()).catch(err=>status(err.message));$('profileQuickSearchInput').onkeydown=e=>{if(e.key==='Enter')$('profileQuickSearchBtn').click()};
  if(isMine){$('profileEditBtn').onclick=openProfileEditDialog}else{$('profileFollowBtn').onclick=async()=>{if(!requireAuth('フォローするにはログインまたは新規登録してください',()=>renderProfile(u.id)))return;const x=await api('/api/follow',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:u.id})});$('profileFollowBtn').textContent=x.following?'フォロー解除':'フォロー'};$('profileDmBtn').onclick=()=>{if(!requireAuth('メッセージを送るにはログインまたは新規登録してください',()=>openDm(u.id)))return;openDm(u.id)};$('profileBlockBtn').onclick=async()=>{if(!requireAuth('ブロックするにはログインまたは新規登録してください',()=>renderProfile(u.id)))return;if(!confirm('@'+u.username+' をブロックしますか？'))return;await api('/api/block',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:u.id})});status('@'+u.username+' をブロックしました');await showSocial('data')};$('profileReportBtn').onclick=async()=>{if(!requireAuth('通報するにはログインまたは新規登録してください',()=>renderProfile(u.id)))return;const reason=prompt('通報理由','荒らし・スパム')||'';if(!reason)return;await api('/api/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:u.id,reason})});$('profileReportBtn').textContent='通報済み';status('通報しました')}}
}
function openProfileEditDialog(){$('profileUsername').value=profile.username||'user';$('profileDisplayName').value=profile.display_name||'';$('profileBio').value=profile.bio||'';$('profileDialogAvatar').innerHTML=avatarHtml(profile,'large');$('profileAvatarInput').value='';$('profileDialog').showModal();setTimeout(()=>$('profileDisplayName').focus(),0)}


async function renderCommunities(){
  const root=$('socialContent');const d=await api('/api/communities');
  root.innerHTML=headerWithExpand('コミュニティ','<button id="createCommunityBtn" type="button">＋ 作成</button>')+'<div id="communityList">'+(d.communities.length?d.communities.map(c=>'<div class="communityCard"><h3>'+escapeHtml(c.name)+'</h3><div>'+escapeHtml(c.description||'')+'</div><div class="communityMeta">メンバー '+c.member_count+' ・ 投稿 '+c.post_count+' ・ 作成者 @'+escapeHtml(c.owner.username)+'</div><div class="feedActions"><button type="button" data-community-open="'+c.id+'">開く</button><button type="button" data-community-join="'+c.id+'">'+(c.joined?'退出':'参加')+'</button></div></div>').join(''):'<div class="emptyState">まだコミュニティがありません</div>')+'</div>';bindExpand();
  $('createCommunityBtn').onclick=()=>{if(!requireAuth('コミュニティを作るにはログインまたは新規登録してください',()=>renderCommunities().then(()=>$('createCommunityBtn')?.click())))return;$('communityName').value='';$('communityDescription').value='';$('communityCreateDialog').showModal()};root.querySelectorAll('[data-community-open]').forEach(b=>b.onclick=()=>renderCommunity(Number(b.dataset.communityOpen),'overview'));root.querySelectorAll('[data-community-join]').forEach(b=>b.onclick=async()=>{if(!requireAuth('コミュニティに参加するにはログインまたは新規登録してください',()=>renderCommunities()))return;await api('/api/community-join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({community_id:Number(b.dataset.communityJoin)})});await renderCommunities()});
}
async function renderCommunity(cid,tab='overview'){
  stopSocialPoll();communityViewState={id:Number(cid),tab};const root=$('socialContent');root.innerHTML='<div class="emptyState">読み込み中...</div>';const d=await api('/api/community?id='+cid),c=d.community;
  if(tab==='index'){showNetwork();await openFile(c.index_file);return}
  const [latest,popular]=await Promise.all([api('/api/feed?mode=latest&community_id='+cid),api('/api/feed?mode=popular&community_id='+cid)]);
  let adminData=null;if(tab==='admin')adminData=await api('/api/community-admin?id='+cid);
  let main='';
  if(tab==='dm')main='<div id="communityChat" class="chatBox">'+(c.joined?'読み込み中...':'参加するとメッセージを利用できます')+'</div>'+(c.joined?'<form id="communityChatForm" class="chatComposer"><input id="communityChatInput" maxlength="4000" placeholder="コミュニティメッセージ"><button>送信</button></form>':'');
  else if(tab==='admin'){
    const rows=(adminData.members||[]).map(m=>'<div class="communityMemberRow"><div><strong>'+escapeHtml(m.display_name||m.username)+'</strong> <span class="feedAuthorHandle">@'+escapeHtml(m.username)+'</span><div class="communityMemberMeta">'+(Number(m.id)===Number(c.owner_user_id)?'作成者':m.community_moderator?'コミュニティモデレーター':'メンバー')+'</div></div><div class="communityAdminActions">'+(c.can_manage_roles&&Number(m.id)!==Number(c.owner_user_id)?'<button type="button" data-community-mod="'+m.id+'" data-enabled="'+(m.community_moderator?'0':'1')+'">'+(m.community_moderator?'モデレーター解除':'モデレーターにする')+'</button>':'')+'</div><div>'+(Number(m.id)!==Number(c.owner_user_id)?'<button type="button" data-community-remove="'+m.id+'">退出させる</button>':'')+'</div></div>').join('');
    main='<section class="profileSection"><div class="sectionHead"><h3>コミュニティ管理</h3></div><form id="communityAdminForm" class="communityAdminForm"><label>名前<input id="communityAdminName" maxlength="120" value="'+escapeHtml(c.name)+'"></label><label>説明<textarea id="communityAdminDescription" class="profileBio" maxlength="1000">'+escapeHtml(c.description||'')+'</textarea></label><div class="actions"><button type="submit">保存</button><button id="communityAdminOpenIndex" type="button">Indexを開く</button></div></form></section><section class="profileSection"><div class="sectionHead"><h3>メンバー</h3></div><div>'+rows+'</div></section>';
  }
  else if(tab==='latest'||tab==='popular')main='<section class="profileSection"><div class="sectionHead"><h3>'+(tab==='popular'?'人気':'最新')+'</h3></div><div class="sectionFeed">'+((tab==='popular'?popular.posts:latest.posts).length?(tab==='popular'?popular.posts:latest.posts).map(feedCardHtml).join(''):'<div class="emptyState">投稿がありません</div>')+'</div></section>';
  else main='<div class="profileSections"><section class="profileSection"><h3>検索</h3><div class="profileQuickSearch"><input id="communityQuickSearchInput" placeholder="このコミュニティを検索"><button id="communityQuickSearchBtn" type="button">検索</button></div></section><section id="communityIndexSection" class="profileSection navigable" tabindex="0">'+sectionHead('Index','communityIndexOpen','Indexを開く')+'<div id="communityIndexBody" class="profileIndexBody preview"></div><div id="communityIndexChildren"></div></section><section class="profileSection">'+sectionHead('最新','communityLatestAll')+'<div class="sectionFeed previewFeed">'+(latest.posts.length?latest.posts.slice(0,3).map(feedCardHtml).join(''):'<div class="emptyState">投稿がありません</div>')+'</div></section><section class="profileSection">'+sectionHead('人気','communityPopularAll')+'<div class="sectionFeed previewFeed">'+(popular.posts.length?popular.posts.slice(0,3).map(feedCardHtml).join(''):'<div class="emptyState">投稿がありません</div>')+'</div></section></div>';
  root.innerHTML='<div class="socialHeader"><button id="communityBack" type="button">←</button><h2>'+escapeHtml(c.name)+'</h2><button id="communityDmBtn" type="button">メッセージ</button>'+(c.can_manage?'<button id="communityAdminBtn" type="button">管理</button>':'')+'<button id="communityJoin" type="button">'+(c.joined?'退出':'参加')+'</button><button id="socialExpandBtn" class="expandBtn" type="button">拡大</button></div><p>'+escapeHtml(c.description||'')+'</p><div class="communityMeta">メンバー '+c.member_count+' ・ 投稿 '+c.post_count+'</div><div class="communityContent">'+main+'</div>';bindExpand();
  $('communityBack').onclick=()=>tab==='overview'?renderCommunities():renderCommunity(cid,'overview');$('communityDmBtn').onclick=()=>{if(isGuest()){showAuth('コミュニティメッセージにはログインまたは新規登録してください',()=>renderCommunity(cid,'dm'));return}renderCommunity(cid,tab==='dm'?'overview':'dm')};if($('communityAdminBtn'))$('communityAdminBtn').onclick=()=>renderCommunity(cid,tab==='admin'?'overview':'admin');$('communityJoin').onclick=async()=>{if(!requireAuth('コミュニティに参加するにはログインまたは新規登録してください',()=>renderCommunity(cid,tab)))return;await api('/api/community-join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({community_id:cid})});await renderCommunity(cid,tab)};
  if(tab==='overview'){
    const ix=$('communityIndexBody');let indexData=null;try{indexData=await api('/api/file?name='+encodeURIComponent(c.index_file))}catch(_){}if(indexData){renderMarkdownDocument(ix,markdownPreview(bodyWithoutPureEdgeSections(indexData.content||'')),{taskInteractive:false});ix.onclick=async e=>{const a=e.target.closest('a[data-file]');if(a){e.preventDefault();e.stopPropagation();showNetwork();await openFile(a.dataset.file)}};$('communityIndexChildren').innerHTML=indexChildPreviewHtml(indexData.incoming||[]);bindIndexChildLinks($('communityIndexChildren'))}else ix.innerHTML='<div class="profileIndexMissing">Indexがありません</div>';
    const openIndex=async()=>{showNetwork();await openFile(c.index_file)};$('communityIndexOpen').onclick=e=>{e.stopPropagation();openIndex().catch(err=>status(err.message))};$('communityIndexSection').onclick=e=>{if(e.target.closest('button,a'))return;openIndex().catch(err=>status(err.message))};$('communityIndexSection').onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button,a')){e.preventDefault();openIndex().catch(err=>status(err.message))}};$('communityLatestAll').onclick=e=>{e.stopPropagation();renderCommunity(cid,'latest')};$('communityPopularAll').onclick=e=>{e.stopPropagation();renderCommunity(cid,'popular')};$('communityQuickSearchBtn').onclick=()=>openSearch('community',cid,0,$('communityQuickSearchInput').value.trim()).catch(err=>status(err.message));$('communityQuickSearchInput').onkeydown=e=>{if(e.key==='Enter')$('communityQuickSearchBtn').click()};
  }
  if(tab==='admin'){
    $('communityAdminForm').onsubmit=async e=>{e.preventDefault();await api('/api/community-admin-save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({community_id:cid,name:$('communityAdminName').value.trim(),description:$('communityAdminDescription').value.trim()})});status('コミュニティ設定を保存しました');await renderCommunity(cid,'admin')};
    $('communityAdminOpenIndex').onclick=async()=>{showNetwork();await openFile(c.index_file)};
    root.querySelectorAll('[data-community-mod]').forEach(b=>b.onclick=async()=>{await api('/api/community-moderator',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({community_id:cid,user_id:Number(b.dataset.communityMod),enabled:b.dataset.enabled==='1'})});await renderCommunity(cid,'admin')});
    root.querySelectorAll('[data-community-remove]').forEach(b=>b.onclick=async()=>{if(!confirm('このメンバーをコミュニティから退出させますか？'))return;await api('/api/community-member-remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({community_id:cid,user_id:Number(b.dataset.communityRemove)})});await renderCommunity(cid,'admin')});
  }
  if(tab==='overview'||tab==='latest'||tab==='popular')bindFeedActions(root);
  if(tab==='dm'&&c.joined){const load=()=>loadCommunityChat(cid).catch(()=>{});await load();socialPollTimer=setInterval(load,4000);$('communityChatForm').onsubmit=async e=>{e.preventDefault();const input=$('communityChatInput'),body=input.value.trim();if(!body)return;await api('/api/community-message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({community_id:cid,body})});input.value='';await load()}}
}
async function loadCommunityChat(cid){const box=$('communityChat');if(!box)return;const d=await api('/api/community-messages?id='+cid);box.innerHTML=d.messages.map(m=>'<div class="chatMsg">'+avatarHtml(m.author,'small')+'<div class="chatBubble"><div class="chatName">'+escapeHtml(m.author.display_name||m.author.username)+'</div><div>'+escapeHtml(m.body)+'</div><div class="chatTime">'+escapeHtml(formatLocalDateTime(m.created_at))+'</div></div></div>').join('')||'<div class="emptyState">まだメッセージがありません</div>';box.scrollTop=box.scrollHeight}

function dmContactHtml(u,activeId=0){return '<button class="listItem dmContact '+(Number(u.id)===Number(activeId)?'active':'')+'" type="button" data-dm-user="'+u.id+'">'+avatarHtml(u,'small')+'<span class="dmContactText"><span class="dmContactName">'+escapeHtml(u.display_name||u.username)+'</span><span class="dmContactMeta">@'+escapeHtml(u.username)+(u.following?' · フォロー中':'')+(u.chatted?' · 会話あり':'')+'</span></span></button>'}
async function dmContacts(){return (await api('/api/dm-contacts')).users||[]}
async function renderDmHome(){stopSocialPoll();const root=$('socialContent');const users=await dmContacts();root.innerHTML=headerWithExpand('DM')+'<div class="socialGrid"><div class="panel"><div class="panelHead">フォロー中・会話した人</div><div class="panelBody" id="dmUsers">'+(users.length?users.map(u=>dmContactHtml(u)).join(''):'<div class="emptyState">フォローした人、またはDMした人がここに表示されます</div>')+'</div></div><div class="panel"><div class="panelHead">メッセージ</div><div class="panelBody"><div class="emptyState">相手を選択してください</div></div></div></div>';bindExpand();root.querySelectorAll('[data-dm-user]').forEach(b=>b.onclick=()=>openDm(Number(b.dataset.dmUser),users))}
async function openDm(otherId,users=null){stopSocialPoll();const root=$('socialContent');if(!users)users=await dmContacts();const d=await api('/api/dm?user_id='+otherId),other=d.other;if(!users.some(u=>Number(u.id)===Number(otherId)))users=[other,...users];root.innerHTML='<div class="socialHeader"><h2>DM</h2><button id="dmClearBtn" type="button">チャットを消す</button><button id="socialExpandBtn" class="expandBtn" type="button">拡大</button></div><div class="socialGrid"><div class="panel"><div class="panelHead">フォロー中・会話した人</div><div class="panelBody">'+users.map(u=>dmContactHtml(u,otherId)).join('')+'</div></div><div class="panel"><div class="panelHead"><button class="profileLink" data-profile-user="'+other.id+'">'+escapeHtml(other.display_name||other.username)+' <span class="feedAuthorHandle">@'+escapeHtml(other.username)+'</span></button></div><div class="panelBody"><div id="dmChat" class="chatBox"></div><form id="dmForm" class="chatComposer"><input id="dmInput" maxlength="4000" placeholder="メッセージ"><button>送信</button></form></div></div></div>';bindExpand();bindProfileLinks(root);root.querySelectorAll('[data-dm-user]').forEach(b=>b.onclick=()=>openDm(Number(b.dataset.dmUser),users));$('dmClearBtn').onclick=async()=>{if(!confirm('このDM履歴を自分の画面から削除しますか？相手側の履歴は消えません。'))return;await api('/api/dm-clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:otherId})});await renderDmHome()};const load=()=>loadDm(otherId).catch(()=>{});await load();socialPollTimer=setInterval(load,4000);$('dmForm').onsubmit=async e=>{e.preventDefault();const input=$('dmInput'),body=input.value.trim();if(!body)return;await api('/api/dm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:otherId,body})});input.value='';await load()}}
async function loadDm(otherId){const box=$('dmChat');if(!box)return;const d=await api('/api/dm?user_id='+otherId);box.innerHTML=d.messages.map(m=>'<div class="chatMsg">'+avatarHtml(m.author,'small')+'<div class="chatBubble"><div class="chatName">'+escapeHtml(m.author.display_name||m.author.username)+'</div><div>'+escapeHtml(m.body)+'</div><div class="chatTime">'+escapeHtml(formatLocalDateTime(m.created_at))+'</div></div></div>').join('')||'<div class="emptyState">メッセージはありません</div>';box.scrollTop=box.scrollHeight}
function fmtBytes(n){n=Number(n||0);if(n<1024)return n+' B';if(n<1024*1024)return (n/1024).toFixed(1)+' KB';return (n/1024/1024).toFixed(1)+' MB'}
function quotaRow(label,value,limit,display){const pct=limit?Math.min(100,Math.round(value/limit*100)):0;return '<div class="quotaRow"><span>'+escapeHtml(label)+'</span><span class="quotaBar"><i style="width:'+pct+'%"></i></span><span>'+escapeHtml(display||String(value)+' / '+String(limit))+'</span></div>'}
async function importBackupFile(file){
  if(!file)return;
  if(!confirm('このバックアップを現在のアカウントへ復元しますか？同名の自分のノートは更新されます。'))return;
  const dataUrl=await fileToDataUrl(file),b64=String(dataUrl).split(',',2)[1]||'';
  const d=await api('/api/backup-import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data_base64:b64})});
  await refreshFiles();if(current&&cachedFiles.some(x=>x.name===current)){await openFile(current,{record:false})}else{await openFile(profile.index_file,{record:false})}
  status('バックアップを復元しました: '+d.notes+'ノート');
}
async function openLocalExportDialog(){
  if(profile?.local_mode&&!profile?.web_connected){showAuth('WebへエクスポートするにはWebアカウントへログインするか、新規作成してください',()=>openLocalExportDialog());return}
  status('エクスポート候補を確認中...');
  try{
    const d=await api('/api/local-export-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const notes=d.notes||[],attachments=d.attachments||[];
    const nr=$('localExportNotes'),ar=$('localExportAttachments');
    nr.innerHTML=notes.length?notes.map(n=>'<label class="exportItem"><input type="checkbox" data-export-note="'+escapeHtml(n.file)+'" checked><span>'+escapeHtml(n.title||n.file)+'<br><small>'+escapeHtml(n.file)+'</small></span><small>'+Math.max(1,Math.round(Number(n.bytes||0)/1024))+' KB</small></label>').join(''):'<div class="profileHint">公開可能なノートはありません。</div>';
    ar.innerHTML=attachments.length?attachments.map(a=>'<label class="exportItem"><input type="checkbox" data-export-attachment="'+escapeHtml(a.path)+'" checked><span>'+escapeHtml(a.path)+'</span><small>'+Math.max(1,Math.round(Number(a.bytes||0)/1024))+' KB</small></label>').join(''):'<div class="profileHint">公開対象の添付ファイルはありません。</div>';
    const refresh=()=>{const nc=nr.querySelectorAll('[data-export-note]:checked').length,ac=ar.querySelectorAll('[data-export-attachment]:checked').length;$('localExportSummary').textContent='送信予定: '+nc+'ノート / '+ac+'添付ファイル'};
    nr.onchange=refresh;ar.onchange=refresh;
    $('localExportNotesAll').onclick=()=>{nr.querySelectorAll('[data-export-note]').forEach(x=>x.checked=true);refresh()};
    $('localExportNotesNone').onclick=()=>{nr.querySelectorAll('[data-export-note]').forEach(x=>x.checked=false);refresh()};
    $('localExportAttachmentsAll').onclick=()=>{ar.querySelectorAll('[data-export-attachment]').forEach(x=>x.checked=true);refresh()};
    $('localExportAttachmentsNone').onclick=()=>{ar.querySelectorAll('[data-export-attachment]').forEach(x=>x.checked=false);refresh()};
    $('localExportConfirm').onclick=async()=>{const selectedNotes=[...nr.querySelectorAll('[data-export-note]:checked')].map(x=>x.dataset.exportNote),selectedAttachments=[...ar.querySelectorAll('[data-export-attachment]:checked')].map(x=>x.dataset.exportAttachment);if(!selectedNotes.length&&!selectedAttachments.length){status('エクスポート対象を選択してください');return}status('選択したファイルをWebへ送信中...');try{const r=await api('/api/local-export-selected',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:selectedNotes,attachments:selectedAttachments})});$('localExportDialog').close();status('Webへエクスポートしました: '+Number(r.published||0)+'ノート / '+Number(r.attachments||0)+'添付')}catch(e){status(e.message)}};
    refresh();$('localExportDialog').showModal();status('送信する内容を選択してください');
  }catch(e){status(e.message)}
}
async function renderDataPage(){
  const root=$('socialContent');root.innerHTML=headerWithExpand('データ・バックアップ')+'<div class="emptyState">読み込み中...</div>';bindExpand();
  const q=await api('/api/quota');
  let blockedUsers=[];if(!profile?.local_mode){try{blockedUsers=(await api('/api/blocks')).users||[]}catch(_){}}
  const quota=quotaRow('ノート',q.notes,q.notes_limit,q.notes+' / '+q.notes_limit)+quotaRow('Markdown',q.note_bytes,q.note_bytes_limit,fmtBytes(q.note_bytes)+' / '+fmtBytes(q.note_bytes_limit))+quotaRow('添付',q.media_bytes,q.media_bytes_limit,fmtBytes(q.media_bytes)+' / '+fmtBytes(q.media_bytes_limit))+quotaRow('関係',q.relations,q.relations_limit,q.relations+' / '+q.relations_limit);
  let syncCard='';
  if(profile?.local_mode){
    const cfg=await api('/api/local-settings');
    syncCard='<section class="dataCard"><h3>ネット接続</h3><p>Localはログインなしで完全に使えます。ログインは、明示的にデータを転送するときだけ必要です。自動転送やマージは行いません。</p><form id="localWebLoginForm" class="syncForm"><label>Webサーバー<input id="localServerUrl" value="'+escapeHtml(cfg.server_url||'')+'"></label><label>Webユーザー名<input id="localWebUsername" autocomplete="username" maxlength="32" value="'+escapeHtml(cfg.remote_username||'')+'"></label><label>Webパスワード<input id="localWebPassword" type="password" autocomplete="current-password"></label><div class="actions"><button id="localWebLoginSubmit" type="submit">Webへログイン</button><button id="localWebRegisterSubmit" type="button">Webアカウントを作成</button></div></form><div class="syncConnected">接続先: <strong>'+escapeHtml(cfg.remote_username?('@'+cfg.remote_username):'未接続')+'</strong><br><small>最終ダウンロード: '+escapeHtml(cfg.last_pull_at||'未実行')+' · 最終アップロード: '+escapeHtml(cfg.last_push_at||'未実行')+'</small></div><div class="actions" style="margin-top:9px"><button id="pullWebBtn" type="button">ネットからダウンロード</button><button id="publishNowBtn" type="button">ネットへアップロード</button><button id="disconnectWebBtn" type="button">ログアウト</button></div><p class="localHint">ダウンロードはネットの全データでLocalを、アップロードはLocalの全データでネットを上書きします。</p></section>';
  }else{
    syncCard='<section class="dataCard"><h3>NetworkNotes Local</h3><p>ローカル版ではMarkdownをPCに保存し、公開するノートだけWebへ送れます。</p><div class="actions"><button id="openDownloadBtn" type="button">ローカル版をダウンロード</button><button id="issueSyncTokenBtn" type="button">ローカル同期キーを発行</button></div><div id="syncTokenResult" class="localHint">同期キーは発行時にだけ表示します。ローカル版の「データ」画面へ貼り付けてください。</div></section>';
  }
  const blockCard=profile?.local_mode?'':('<section class="dataCard"><h3>ブロック中</h3>'+(blockedUsers.length?blockedUsers.map(u=>'<div class="listItem">@'+escapeHtml(u.username)+' <button data-unblock-user="'+u.id+'" type="button">解除</button></div>').join(''):'<p>ブロック中のアカウントはありません。</p>')+'</section>');
  root.innerHTML=headerWithExpand('データ・バックアップ')+'<div class="dataGrid"><section class="dataCard"><h3>使用量</h3>'+quota+'</section><section class="dataCard"><h3>ローカルバックアップ</h3><p>自分のMarkdownと添付ファイルをZIPとして保存します。定期的なローカルバックアップを推奨します。</p><div class="actions"><button id="backupExportBtn" type="button">バックアップをダウンロード</button><button id="backupImportBtn" type="button">ZIPから復元</button><input id="backupImportInput" type="file" accept="application/zip,.zip" hidden></div></section>'+syncCard+blockCard+'</div>';bindExpand();
  $('backupExportBtn').onclick=()=>{window.location.href='/api/backup-export'};
  $('backupImportBtn').onclick=()=>{$('backupImportInput').value='';$('backupImportInput').click()};
  $('backupImportInput').onchange=()=>importBackupFile($('backupImportInput').files?.[0]).catch(e=>status(e.message));
  root.querySelectorAll('[data-unblock-user]').forEach(b=>b.onclick=async()=>{await api('/api/block',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:Number(b.dataset.unblockUser)})});await renderDataPage()});
  if(profile?.local_mode){
    $('localWebLoginForm').onsubmit=async e=>{e.preventDefault();const username=$('localWebUsername').value.trim(),password=$('localWebPassword').value,server_url=$('localServerUrl').value.trim();if(!username||!password){status('Webのユーザー名とパスワードを入力してください');return}const btn=$('localWebLoginSubmit');try{btn.disabled=true;btn.textContent='ログイン中...';const d=await api('/api/local-account-bootstrap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url,username,password,pull:false})});$('localWebPassword').value='';profile=d.profile;updateProfileUi();status('Web @'+(d.remote_username||username)+' にログインしました');await renderDataPage()}catch(err){status(err.message)}finally{btn.disabled=false;btn.textContent='Webへログイン'}};
    $('localWebRegisterSubmit').onclick=async()=>{const username=$('localWebUsername').value.trim(),password=$('localWebPassword').value,server_url=$('localServerUrl').value.trim();if(!username||password.length<8){status('Webユーザー名と8文字以上のパスワードを入力してください');return}if(!confirm('Web版に @'+username+' を新規作成して、このLocalと接続しますか？'))return;const btn=$('localWebRegisterSubmit');try{btn.disabled=true;btn.textContent='作成中...';const d=await api('/api/local-account-register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url,username,password,pull:false})});$('localWebPassword').value='';profile=d.profile;updateProfileUi();status('Web @'+(d.remote_username||username)+' を作成して接続しました');await renderDataPage()}catch(err){status(err.message)}finally{btn.disabled=false;btn.textContent='Webアカウントを作成'}};
    $('publishNowBtn').onclick=async()=>{if(!requireWebConnection('ネットへアップロードするにはWebアカウントへログインするか、新規作成してください',()=>$('publishNowBtn')?.click()))return;if(!confirm('Localの全データでネット上の自分のデータを完全に上書きしますか？'))return;status('ネットへアップロード中...');try{const d=await api('/api/local-publish-now',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});status('ネットへアップロードしました: '+Number(d.published||0)+'ノート')}catch(e){status(e.message)}};
    $('pullWebBtn').onclick=async()=>{if(!requireWebConnection('ネットからダウンロードするにはWebアカウントへログインするか、新規作成してください',()=>$('pullWebBtn')?.click()))return;if(!confirm('ネット上の全データでLocalを完全に上書きしますか？現在のLocalデータは作業領域から置き換えられます。'))return;status('ネットからダウンロード中...');try{const d=await api('/api/local-pull',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await refreshFiles();await openFile(profile.index_file,{record:false});status('ネットからダウンロードしました: '+Number(d.notes||0)+'ノート / '+Number(d.attachments||0)+'添付')}catch(e){status(e.message)}};
    $('disconnectWebBtn').onclick=async()=>{if(!profile?.web_connected)return;if(!confirm('Webアカウントからログアウトしますか？Localのデータは残ります。'))return;await api('/api/local-disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});profile={...profile,web_connected:false,remote_username:''};updateProfileUi();status('Webアカウントからログアウトしました');await renderDataPage()};
  }else{
    $('openDownloadBtn').onclick=()=>{window.location.href='/download'};
    $('issueSyncTokenBtn').onclick=async()=>{if(!confirm('以前の同期キーは無効になります。新しい同期キーを発行しますか？'))return;const d=await api('/api/sync-token',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});$('syncTokenResult').innerHTML='<div class="tokenBox">'+escapeHtml(d.token)+'</div><div class="localHint">このキーだけをLocal版へ貼り付けてください。@'+escapeHtml(d.username||profile.username||'')+' と自動的に紐付きます。再表示はできません。</div>';try{await navigator.clipboard.writeText(d.token)}catch(_){}};
  }
}
async function renderAdminPage(){
  if(!['owner','moderator'].includes(profile?.role)){showNetwork();return}
  const root=$('socialContent');root.innerHTML=headerWithExpand('管理')+'<div class="emptyState">読み込み中...</div>';bindExpand();
  const d=await api('/api/moderation');
  const rows=(d.users||[]).map(u=>{const q=u.quota||{},owner=u.role==='owner',self=Number(u.id)===Number(profile.id);let acts='<button data-quota-save="'+u.id+'" type="button">個別上限を保存</button>';if(!owner&&!self){if(profile.role==='owner')acts+='<button data-role-user="'+u.id+'" data-role-next="'+(u.role==='moderator'?'user':'moderator')+'">'+(u.role==='moderator'?'Moderator解除':'Moderatorにする')+'</button>';acts+='<button data-status-user="'+u.id+'" data-status-next="'+(u.status==='suspended'?'active':'suspended')+'">'+(u.status==='suspended'?'停止解除':'一時停止')+'</button><button data-delete-user="'+u.id+'" data-delete-name="'+escapeHtml(u.username)+'">削除</button>'}return '<tr><td>@'+escapeHtml(u.username)+'<br><span class="roleBadge">'+escapeHtml(u.role)+'</span></td><td class="'+(u.status==='suspended'?'statusSuspended':'')+'">'+escapeHtml(u.status)+(u.suspended_reason?'<br>'+escapeHtml(u.suspended_reason):'')+'</td><td>通報 '+Number(u.report_count||0)+'</td><td><div>'+Number(q.notes||0)+' notes · '+fmtBytes(q.note_bytes||0)+' MD · '+fmtBytes(q.media_bytes||0)+' 添付 · '+Number(q.relations||0)+' 関係</div><div class="communityMeta">'+(u.quota_override?'個別上限':'全体デフォルト')+'</div><div class="quotaInputs"><label>ノート数<input data-quota-field="notes_limit" data-quota-user="'+u.id+'" type="number" min="1" value="'+Number(q.notes_limit||1000)+'"></label><label>Markdown MB<input data-quota-field="note_mb" data-quota-user="'+u.id+'" type="number" min="1" step="1" value="'+Math.round(Number(q.note_bytes_limit||0)/1048576)+'"></label><label>添付 MB<input data-quota-field="media_mb" data-quota-user="'+u.id+'" type="number" min="1" step="1" value="'+Math.round(Number(q.media_bytes_limit||0)/1048576)+'"></label><label>関係数<input data-quota-field="relations_limit" data-quota-user="'+u.id+'" type="number" min="1" value="'+Number(q.relations_limit||5000)+'"></label></div></td><td><div class="actions">'+acts+'</div></td></tr>'}).join('');
  const reports=(d.reports||[]).map(r=>'<div class="reportCard"><strong>'+escapeHtml(r.note_file?('ノート '+r.note_file):('@'+(r.target_username||'')))+'</strong> ・ 通報者 @'+escapeHtml(r.reporter_username||'')+'<div class="reportReason">'+escapeHtml(r.reason||'理由なし')+'</div><button data-resolve-report="'+r.id+'">確認済みにする</button></div>').join('')||'<div class="emptyState">未処理の通報はありません</div>';
  const logs=(d.logs||[]).slice(0,50).map(x=>'<div class="communityMeta">'+escapeHtml(formatLocalDateTime(x.created_at))+' · @'+escapeHtml(x.actor_username||'')+' · '+escapeHtml(x.action||'')+' · '+escapeHtml(x.target_username||x.target_note||'')+'</div>').join('')||'<div class="emptyState">履歴はありません</div>';
  const g=d.global_quota||{};const globalBox=profile.role==='owner'?('<section class="globalQuotaBox"><h3>全体のデフォルト使用可能量</h3><div class="globalQuotaActions"><label>ノート数<input id="globalQuotaNotes" type="number" min="1" value="'+Number(g.notes_limit||1000)+'"></label><label>Markdown MB<input id="globalQuotaNoteMb" type="number" min="1" value="'+Math.round(Number(g.note_bytes_limit||0)/1048576)+'"></label><label>添付 MB<input id="globalQuotaMediaMb" type="number" min="1" value="'+Math.round(Number(g.media_bytes_limit||0)/1048576)+'"></label><label>関係数<input id="globalQuotaRelations" type="number" min="1" value="'+Number(g.relations_limit||5000)+'"></label><button id="globalQuotaSave" type="button">全体を保存</button></div><div class="profileHint">個別上限が設定されていないユーザー全員に適用されます。個別上限は維持されます。</div></section>'):' ';root.innerHTML=headerWithExpand('管理')+globalBox+'<section class="dataCard"><h3>ユーザー</h3><div style="overflow:auto"><table class="adminTable"><thead><tr><th>ユーザー</th><th>状態</th><th>通報</th><th>使用量</th><th>操作</th></tr></thead><tbody>'+rows+'</tbody></table></div></section><section class="dataCard" style="margin-top:12px"><h3>未処理の通報</h3>'+reports+'</section><section class="dataCard" style="margin-top:12px"><h3>管理履歴</h3>'+logs+'</section>';bindExpand();
  if($('globalQuotaSave'))$('globalQuotaSave').onclick=async()=>{await api('/api/mod-global-quota',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes_limit:Number($('globalQuotaNotes').value||0),note_mb:Number($('globalQuotaNoteMb').value||0),media_mb:Number($('globalQuotaMediaMb').value||0),relations_limit:Number($('globalQuotaRelations').value||0)})});status('全体の使用可能量を更新しました');await renderAdminPage()};
  root.querySelectorAll('[data-role-user]').forEach(b=>b.onclick=async()=>{await api('/api/mod-role',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:Number(b.dataset.roleUser),role:b.dataset.roleNext})});await renderAdminPage()});
  root.querySelectorAll('[data-status-user]').forEach(b=>b.onclick=async()=>{const susp=b.dataset.statusNext==='suspended',reason=susp?(prompt('停止理由（任意）','荒らし・スパム')||''):'';if(susp&&!confirm('このアカウントを一時停止し、投稿とリンクを通常表示から隠しますか？'))return;await api('/api/mod-status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:Number(b.dataset.statusUser),status:b.dataset.statusNext,reason})});await renderAdminPage()});
  root.querySelectorAll('[data-delete-user]').forEach(b=>b.onclick=async()=>{const name=b.dataset.deleteName,typed=prompt('完全削除します。確認のためユーザー名を入力してください:\n'+name);if(typed!==name)return;const reason=prompt('削除理由','明らかな荒らし')||'';await api('/api/mod-delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:Number(b.dataset.deleteUser),reason})});await renderAdminPage()});
  root.querySelectorAll('[data-quota-save]').forEach(b=>b.onclick=async()=>{const userId=Number(b.dataset.quotaSave);const vals={user_id:userId};root.querySelectorAll('[data-quota-user="'+userId+'"]').forEach(i=>vals[i.dataset.quotaField]=Number(i.value||0));await api('/api/mod-quota',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(vals)});status('使用可能量を更新しました');await renderAdminPage()});
  root.querySelectorAll('[data-resolve-report]').forEach(b=>b.onclick=async()=>{await api('/api/mod-report-resolve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({report_id:Number(b.dataset.resolveReport),action:'reviewed'})});await renderAdminPage()});
}

async function fileToDataUrl(file){return await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.readAsDataURL(file)})}
function dataUrlBytes(dataUrl){const b64=String(dataUrl||'').split(',')[1]||'';return Math.floor(b64.length*3/4)}
async function imageFileToJpegDataUrl(file,maxBytes=300*1024){
  if(!file?.type?.startsWith('image/'))return fileToDataUrl(file);
  const src=URL.createObjectURL(file);try{
    const img=await new Promise((resolve,reject)=>{const x=new Image();x.onload=()=>resolve(x);x.onerror=()=>reject(new Error('画像を読み込めません'));x.src=src});
    let w=img.naturalWidth||img.width,h=img.naturalHeight||img.height;const maxDim=2048;if(Math.max(w,h)>maxDim){const r=maxDim/Math.max(w,h);w=Math.max(1,Math.round(w*r));h=Math.max(1,Math.round(h*r))}
    for(let scale=1;scale>=.35;scale*=.82){const cw=Math.max(1,Math.round(w*scale)),ch=Math.max(1,Math.round(h*scale));const c=document.createElement('canvas');c.width=cw;c.height=ch;const ctx=c.getContext('2d',{alpha:false});ctx.fillStyle='#fff';ctx.fillRect(0,0,cw,ch);ctx.drawImage(img,0,0,cw,ch);let lo=.28,hi=.9,best='';for(let i=0;i<7;i++){const q=(lo+hi)/2,d=c.toDataURL('image/jpeg',q),n=dataUrlBytes(d);if(n<=maxBytes){best=d;lo=q}else hi=q}if(best)return best}
    throw new Error('300KB以下に変換できませんでした');
  }finally{URL.revokeObjectURL(src)}
}
async function loadShareCommunities(){
  const d=await api('/api/communities');const joined=d.communities.filter(c=>c.joined),sel=$('communityShareSelect');sel.innerHTML='';for(const c of joined){const o=document.createElement('option');o.value=c.id;o.textContent=c.name;sel.appendChild(o)}return joined.length;
}
window.addEventListener('popstate',()=>{
  if(!profile)return;
  const requested=requestedNoteFromUrl()||profile.index_file;
  if(requested&&requested!==current){openFile(requested,{record:false,url:false}).then(()=>{navigationTrail=[];pushTrail(current,currentData.title);showNetwork()}).catch(()=>{})}
});
async function boot(){
  try{
    const s=await api('/api/session');runtimeLocalMode=!!s.local_mode;
    if(!s.authenticated){
      await enterGuestMode(false);return
    }
    profile=s.profile;hideAuth();updateProfileUi();await refreshFiles();
    const requested=requestedNoteFromUrl();
    try{await openFile(requested||profile.index_file,{record:false,replaceUrl:true})}
    catch(_){await openFile(profile.index_file,{record:false,replaceUrl:true})}
    navigationTrail=[];pushTrail(current,currentData.title);showNetwork();
  }catch(e){status(e.message,{kind:'error'});if(!runtimeLocalMode)await enterGuestMode(false)}
}


$('profileAvatarInput').addEventListener('change',async()=>{const file=$('profileAvatarInput').files?.[0];if(!file)return;try{const data_url=await imageFileToJpegDataUrl(file);profile=await api('/api/upload-avatar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data_url})});updateProfileUi();$('profileDialogAvatar').innerHTML=avatarHtml(profile,'large');if(currentData?.author?.id===profile.id){currentData.author={...currentData.author,...profile};updateAuthorBar();if(mode==='organize')renderOrganize()}status('プロフィール画像を更新しました')}catch(e){status(e.message)}});
$('likeBtn').onclick=async()=>{if(!current||currentData?.is_index)return;await toggleLike(current)};
$('reportNoteBtn').onclick=async()=>{if(!current||currentData?.can_edit)return;if(!requireAuth('通報するにはログインまたは新規登録してください',()=>$('reportNoteBtn').click()))return;const reason=prompt('このノートの通報理由','荒らし・スパム')||'';if(!reason)return;try{await api('/api/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note:current,reason})});$('reportNoteBtn').textContent='通報済み';status('ノートを通報しました')}catch(e){status(e.message)}};
$('uploadToggle').onchange=async()=>{if(!profile?.local_mode||!currentData?.can_edit)return;const desired=$('uploadToggle').checked;if(desired&&!profile?.web_connected){$('uploadToggle').checked=false;showAuth('このノートをWebで共有するにはWebアカウントへログインするか、新規作成してください',()=>{const t=$('uploadToggle');if(t){t.checked=true;t.dispatchEvent(new Event('change'))}});return}try{await flushAutosave();currentData=await api('/api/note-publish-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:current,upload_enabled:desired})});setEditorsFromRaw(currentData.content);dirty=false;updateEditPermissions();status(desired?'このノートをWeb共有対象にしました':'このノートはLocalのみにしました')}catch(e){$('uploadToggle').checked=!desired;status(e.message)}};
$('publicVersionBtn').onclick=async()=>{if(!profile?.local_mode||!currentData?.can_edit||currentData?.is_index)return;const suggested=(currentData.title||'ノート')+'（公開版）';const title=prompt('公開版のタイトル',suggested);if(!title)return;try{await flushAutosave();const d=await api('/api/new',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:current,title,relation:'公開版'})});await refreshFiles();await openFile(d.file);await switchMode('source');status('公開版を作成しました。公開用の文章に書き換えてください')}catch(e){status(e.message)}};
$('attachmentBtn').onclick=async()=>{if(!currentData?.can_edit){status('自分のノートでのみ添付できます');return}await switchMode('source');if(vimInputMode==='normal')setVimInputMode('insert',editor);editor.focus();$('attachmentInput').value='';$('attachmentInput').click()};
$('attachmentInput').addEventListener('change',async()=>{const file=$('attachmentInput').files?.[0];if(!file||!currentData?.can_edit)return;try{const isImg=String(file.type||'').startsWith('image/');const data_url=isImg?await imageFileToJpegDataUrl(file):await fileToDataUrl(file);const uploadName=isImg?(String(file.name||'image').replace(/\.[^.]+$/,'')+'.jpg'):file.name;const d=await api('/api/upload-attachment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data_url,name:uploadName})});const cm=editor;cm.replaceSelection('\n'+d.markdown+'\n');dirty=true;queueAutosave(100);status('ファイルを添付しました')}catch(e){status(e.message)}finally{$('attachmentInput').value=''}});
$('imageInput').addEventListener('change',async()=>{const file=$('imageInput').files?.[0];if(!file||!currentData?.can_edit)return;try{const data_url=await imageFileToJpegDataUrl(file);const d=await api('/api/upload-image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data_url,name:file.name})});const cm=imageInsertEditor||editor;cm.replaceSelection('\n'+d.markdown+'\n');imageInsertEditor=null;dirty=true;queueAutosave(100);status('画像を添付しました')}catch(e){status(e.message)}finally{$('imageInput').value=''}});
$('shareCommunityBtn').onclick=async()=>{if(!currentData?.can_edit||currentData?.is_index)return;const n=await loadShareCommunities();if(!n){status('参加中のコミュニティがありません');showSocial('communities');return}$('communityShareDialog').showModal()};
$('communityShareForm').addEventListener('submit',async e=>{e.preventDefault();const cid=Number($('communityShareSelect').value);if(!cid)return;await api('/api/community-share',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({community_id:cid,file:current})});$('communityShareDialog').close();status('コミュニティに共有しました')});
$('communityIndexForm').addEventListener('submit',e=>{e.preventDefault();$('communityIndexDialog').close()});
$('communityCreateForm').addEventListener('submit',async e=>{e.preventDefault();const name=$('communityName').value.trim();if(!name)return;await api('/api/community-create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description:$('communityDescription').value.trim()})});$('communityCreateDialog').close();await renderCommunities()});
$('mainNavBtn').onclick=e=>{e.stopPropagation();const menu=$('mainNavMenu');menu.hidden=!menu.hidden;$('mainNavBtn').setAttribute('aria-expanded',menu.hidden?'false':'true')};
$('mainNavMenu').querySelectorAll('[data-main-nav]').forEach(b=>b.onclick=()=>{const v=b.dataset.mainNav;closeNavMenu();if((v==='dm'||v==='data'||v==='admin')&&isGuest()){showAuth((v==='dm'?'メッセージ':v==='data'?'自分のデータ':'管理画面')+'を使うにはログインまたは新規登録してください',()=>showSocial(v));return}showSocial(v).catch(e=>status(e.message))});
document.addEventListener('click',e=>{if(!e.target.closest('#mainNavWrap'))closeNavMenu()});
$('newRootBtn').onclick=()=>startNewRootNote().catch(e=>status(e.message));
if($('downloadBtn'))$('downloadBtn').onclick=()=>{if(profile?.local_mode)window.open('https://network-notes.duckdns.org/','_blank','noopener');else window.location.href='/download'};
$('logoutBtn').onclick=async()=>{try{await flushAutosave()}catch(_){}await api('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});stopSocialPoll();await enterGuestMode(false)};
$('authCancelBtn').onclick=()=>{pendingAuthAction=null;hideAuth()};
$('authWebLoginBtn').onclick=async()=>{const username=$('authWebUsername').value.trim(),password=$('authWebPassword').value,server_url=$('authSyncServer').value.trim();$('authError').textContent='';if(!username||!password){$('authError').textContent='Webのユーザー名とパスワードを入力してください';return}try{$('authWebLoginBtn').disabled=true;$('authWebLoginBtn').textContent='接続中...';const d=await api('/api/local-account-bootstrap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url,username,password,pull:false})});$('authWebPassword').value='';await finishAuthentication(d);status('Web @'+(d.remote_username||d.profile?.username||'')+' に接続しました')}catch(err){$('authError').textContent=err.message}finally{$('authWebLoginBtn').disabled=false;$('authWebLoginBtn').textContent='既存アカウントでログイン'}};
$('authWebRegisterBtn').onclick=async()=>{const username=$('authWebUsername').value.trim(),password=$('authWebPassword').value,server_url=$('authSyncServer').value.trim();$('authError').textContent='';if(!username||password.length<8){$('authError').textContent='Webユーザー名と8文字以上のパスワードを入力してください';return}if(!confirm('Web版に @'+username+' を新規作成して、このLocalと接続しますか？'))return;try{$('authWebRegisterBtn').disabled=true;$('authWebRegisterBtn').textContent='作成中...';const d=await api('/api/local-account-register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url,username,password,pull:false})});$('authWebPassword').value='';await finishAuthentication(d);status('Web @'+(d.remote_username||d.profile?.username||'')+' を作成して接続しました')}catch(err){$('authError').textContent=err.message}finally{$('authWebRegisterBtn').disabled=false;$('authWebRegisterBtn').textContent='Webアカウントを作成'}};
$('authSyncConnectBtn').onclick=async()=>{const token=$('authSyncToken').value.trim(),server_url=$('authSyncServer').value.trim();$('authError').textContent='';if(!token){$('authError').textContent='ローカル同期キーを入力してください';return}try{$('authSyncConnectBtn').disabled=true;$('authSyncConnectBtn').textContent='接続中...';const d=await api('/api/local-bootstrap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url,token,pull:false})});await finishAuthentication(d);status('Web @'+(d.remote_username||d.profile?.username||'')+' と接続しました')}catch(err){$('authError').textContent=err.message}finally{$('authSyncConnectBtn').disabled=false;$('authSyncConnectBtn').textContent='同期キーで接続'}};
$('authOpenWebBtn').onclick=()=>window.open('https://network-notes.duckdns.org/','_blank','noopener');
$('authForm').addEventListener('submit',async e=>{e.preventDefault();$('authError').textContent='';try{const d=await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('authUsername').value.trim(),password:$('authPassword').value})});await finishAuthentication(d)}catch(err){$('authError').textContent=err.message}});
let pendingRegistration=null;
$('registerBtn').onclick=()=>{const username=$('authUsername').value.trim(),password=$('authPassword').value;$('authError').textContent='';if(!username){$('authError').textContent='ユーザー名を入力してください';return}if(password.length<8){$('authError').textContent='パスワードは8文字以上にしてください';return}pendingRegistration={username,password};$('registerPasswordPreview').value=password;$('registerSavedCheck').checked=false;$('registerConfirmBtn').disabled=true;$('registerSaveDialog').showModal()};
$('registerSavedCheck').onchange=()=>{$('registerConfirmBtn').disabled=!$('registerSavedCheck').checked};
$('registerCopyBtn').onclick=async()=>{try{await navigator.clipboard.writeText($('registerPasswordPreview').value);$('registerCopyBtn').textContent='コピーしました';$('registerSavedCheck').checked=true;$('registerConfirmBtn').disabled=false}catch(_){$('registerPasswordPreview').focus();$('registerPasswordPreview').select();status('コピーできない場合は手動でコピーしてください')}};
$('registerConfirmBtn').onclick=async()=>{if(!pendingRegistration||!$('registerSavedCheck').checked)return;$('registerConfirmBtn').disabled=true;try{const d=await api('/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pendingRegistration)});pendingRegistration=null;$('registerSaveDialog').close();await finishAuthentication(d)}catch(err){$('registerConfirmBtn').disabled=false;$('authError').textContent=err.message;$('registerSaveDialog').close()}};
function setMobileSidebar(open){
  const expanded=!!open;document.body.classList.toggle('mobileSidebarOpen',expanded);
  $('mobileNodesBtn')?.setAttribute('aria-expanded',expanded?'true':'false');
  $('sidebar')?.setAttribute('aria-hidden',expanded?'false':'true');
}
if($('mobileNodesBtn'))$('mobileNodesBtn').onclick=()=>setMobileSidebar(!document.body.classList.contains('mobileSidebarOpen'));
if($('mobileOverlay'))$('mobileOverlay').onclick=()=>setMobileSidebar(false);
$('graphLimit').oninput=()=>{$('graphLimitValue').textContent=$('graphLimit').value;queueGraph(120)};
$('graphDepth').oninput=()=>{$('graphDepthValue').textContent=$('graphDepth').value;queueGraph(120)};
$('graphSpacing').oninput=()=>{$('graphSpacingValue').textContent=$('graphSpacing').value;queueGraph(30)};
$('graphFontSize').oninput=()=>{$('graphFontSizeValue').textContent=$('graphFontSize').value;queueGraph(30)};
$('graphRelationLabels').checked=graphShowRelationLabels;$('graphRelationLabelsValue').textContent=graphShowRelationLabels?'ON':'OFF';$('graphRelationLabels').onchange=()=>{graphShowRelationLabels=$('graphRelationLabels').checked;localStorage.setItem('nnGraphRelationLabels',graphShowRelationLabels?'1':'0');$('graphRelationLabelsValue').textContent=graphShowRelationLabels?'ON':'OFF';queueGraph(20)};
function updateGraphControlsVisibility(){const box=$('graphControls'),btn=$('graphControlsToggle');if(!box||!btn)return;box.classList.toggle('collapsed',graphControlsCollapsed);btn.textContent=graphControlsCollapsed?'パラメータを表示':'隠す';btn.setAttribute('aria-expanded',graphControlsCollapsed?'false':'true')}
$('graphControlsToggle').onclick=()=>{graphControlsCollapsed=!graphControlsCollapsed;localStorage.setItem('nnGraphControlsCollapsed',graphControlsCollapsed?'1':'0');updateGraphControlsVisibility();setTimeout(()=>queueGraph(80),0)};updateGraphControlsVisibility();
new ResizeObserver(()=>queueGraph(120)).observe($('graphWrap'));
$('newForm').addEventListener('submit',async e=>{e.preventDefault();const title=$('newTitle').value.trim();const relation=selectedRelation==='__custom__'?$('customRelation').value.trim():selectedRelation;if(!title||!relation)return;if(dirty)await flushAutosave();const d=await api('/api/new',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:current,title,relation})});$('newDialog').close();await refreshFiles();await openFile(d.file);await switchMode('source');status('ノードを作成しました')});
window.addEventListener('beforeunload',()=>{if(!isGuest()&&(dirty||relationSyncPending)){const blob=new Blob([JSON.stringify({name:current,content:editorText(),voter:voterId,commit_relations:true,client_save_session:saveClientSession,client_seq:editRevision})],{type:'application/json'});navigator.sendBeacon('/api/file',blob)}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)flushAutosave().catch(()=>{})});
boot().catch(e=>{status(e.message,{kind:'error'});if(!runtimeLocalMode)showAuth(e.message)});
</script>
</body>
</html>
'''


def ensure_vault() -> None:
    VAULT.mkdir(parents=True, exist_ok=True)
    p = VAULT / INDEX_FILE
    has_users = False
    if DB_FILE.exists():
        try:
            with sqlite3.connect(DB_FILE) as con:
                has_users = bool(con.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        except (sqlite3.Error, OSError):
            has_users = False
    # Before the first SNS account exists, keep the legacy Index so an old
    # single-user vault can be migrated into the first registered account.
    if not p.exists() and not has_users:
        atomic_text_write(p, "# Index\n")
    # Migrate files created by earlier prototypes that used ``title::...``.
    for md in VAULT.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        lines = text.splitlines()
        if lines and lines[0].startswith("title::"):
            legacy_title = lines[0].split("::", 1)[1].strip()
            rest = lines[1:]
            text = "# " + legacy_title + "\n" + ("\n".join(rest).rstrip() + "\n" if rest else "")
            atomic_text_write(md, text)


def load_profile() -> dict:
    ensure_vault()
    default = {"username": "user", "display_name": "", "bio": ""}
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default
    username = re.sub(r"[/\\\x00-\x1f]", "", str(data.get("username", "user"))).strip()[:80] or "user"
    return {
        "username": username,
        "display_name": str(data.get("display_name", "")).strip()[:120],
        "bio": str(data.get("bio", "")).strip()[:1000],
    }


def save_profile(data: dict) -> dict:
    ensure_vault()
    username = re.sub(r"[/\\\x00-\x1f]", "", str(data.get("username", ""))).strip()[:80]
    if not username:
        raise ValueError("username is required")
    profile = {
        "username": username,
        "display_name": str(data.get("display_name", "")).strip()[:120],
        "bio": str(data.get("bio", "")).strip()[:1000],
    }
    atomic_text_write(PROFILE_FILE, json.dumps(profile, ensure_ascii=False, indent=2))
    return profile


def safe_name(name: str) -> str:
    name = Path(name).name
    if not name.endswith(".md"):
        raise ValueError("Markdown file required")
    return name


_TEXT_WRITE_LOCK = threading.RLock()
_LOCAL_CONFIG_LOCK = threading.RLock()
_CLIENT_SAVE_ORDER_LOCK = threading.Lock()
_CLIENT_SAVE_ORDER: dict[tuple[int,str,str], tuple[int,float]] = {}
_GRAPH_SYNC_LOCK = threading.RLock()

def accept_client_save_order(user_id: int, name: str, client_session: str, client_seq: int) -> bool:
    """Reject a late, older autosave from the same browser/editor session."""
    sid=str(client_session or "").strip()[:96]
    if not sid or client_seq < 0:
        return True
    key=(int(user_id),safe_name(name),sid); now=time.monotonic()
    with _CLIENT_SAVE_ORDER_LOCK:
        previous=_CLIENT_SAVE_ORDER.get(key)
        if previous is not None and int(client_seq) < int(previous[0]):
            return False
        _CLIENT_SAVE_ORDER[key]=(int(client_seq),now)
        if len(_CLIENT_SAVE_ORDER)>10000:
            cutoff=now-21600
            for old_key,(_seq,seen) in list(_CLIENT_SAVE_ORDER.items()):
                if seen < cutoff: _CLIENT_SAVE_ORDER.pop(old_key,None)
    return True

def atomic_text_write(path: Path, text: str) -> None:
    """Crash-safe text replacement; readers see either the old or new file, never a partial write."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with _TEXT_WRITE_LOCK:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.{secrets.token_hex(4)}.tmp")
        try:
            with tmp.open("w", encoding="utf-8", newline="") as f:
                f.write(str(text)); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            try: tmp.unlink()
            except FileNotFoundError: pass

def read_file(name: str) -> str:
    return (VAULT / safe_name(name)).read_text(encoding="utf-8")


def write_file(name: str, content: str) -> None:
    safe = safe_name(name)
    # All Markdown writes share the graph lock. Several relation/title operations
    # are read-modify-write across multiple notes; a concurrent draft save must
    # never be overwritten by one of those older snapshots.
    with _GRAPH_SYNC_LOCK:
        # Keep the creation instant verbatim. Offsets make transferred Markdown
        # unambiguous without imposing the Web server's timezone on Local mode.
        normalized = ensure_created_frontmatter(safe, str(content or ""))
        normalized = ensure_creator_metadata(safe, normalized)
        normalized = remove_updated_frontmatter(normalized)
        atomic_text_write(VAULT / safe, normalized)


def save_client_note(user_id: int, name: str, content: str, commit_relations: bool,
                     client_session: str = "", client_seq: int = -1) -> dict:
    """Serialize browser saves and reject late stale requests before they can write."""
    uid=int(user_id); safe=safe_name(name)
    with _GRAPH_SYNC_LOCK:
        if client_session and not accept_client_save_order(uid,safe,client_session,int(client_seq)):
            return {"stale":True,"title":title_of(read_file(safe),safe)}
        old_content=read_file(safe) if (VAULT/safe).exists() else ""
        old_title=title_of(old_content,safe)
        new_title=title_of(str(content or ""),safe)
        enforce_note_write_quota(uid,safe,str(content or ""))
        write_file(safe,str(content or ""))
        if commit_relations:
            sync_plain_link_labels(safe,new_title)
            sync_source_edges_diff(safe)
        return {"stale":False,"old_title":old_title,"title":new_title}


def title_of(content: str, filename: str) -> str:
    # A node title is the first level-1 Markdown heading: ``# Title``.
    for line in content.splitlines():
        hm = HEADING_RE.match(line)
        if hm and hm.group(1) == "#":
            return hm.group(2).strip().rstrip("#").strip()
    return Path(filename).stem


def markdown_escape_label(text: str) -> str:
    return re.sub(r"([\\\[\]])", r"\\\1", str(text))


def sync_plain_link_labels(target_file: str, new_title: str) -> None:
    with _GRAPH_SYNC_LOCK:
        """Synchronize labels of ordinary links after a node title changes.

        Links made with the explicit Linkify action use the Markdown title marker
        ``"label-fixed"`` and intentionally keep their selected display text.
        """
        escaped_title = markdown_escape_label(new_title)
        for md in VAULT.glob("*.md"):
            text = md.read_text(encoding="utf-8")

            def replace_link(m):
                target = Path(urllib.parse.unquote(m.group(2))).name
                if target != target_file or m.group(3) == LINK_LABEL_FIXED:
                    return m.group(0)
                return f"[{escaped_title}]({m.group(2)})"

            changed = MARKDOWN_LINK_RE.sub(replace_link, text)
            if changed != text:
                atomic_text_write(md, changed)


def remove_links_to_targets(content: str, targets: set[str]) -> str:
    """Remove relation-list links to deleted nodes and preserve inline labels as text."""
    clean = strip_edge_block(content)
    out_lines = []
    for line in clean.splitlines():
        rm = RELATION_LINK_LINE_RE.match(line)
        if rm:
            target = Path(urllib.parse.unquote(rm.group(3))).name
            if target in targets:
                continue
        lm = LINK_LINE_RE.match(line)
        if lm:
            target = Path(urllib.parse.unquote(lm.group(2))).name
            if target in targets:
                continue

        def repl(m):
            target = Path(urllib.parse.unquote(m.group(2))).name
            return m.group(1) if target in targets else m.group(0)

        out_lines.append(MARKDOWN_LINK_RE.sub(repl, line))
    result = "\n".join(out_lines).rstrip() + "\n"
    for rel in ("ノート", "note", "notes"):
        result = remove_empty_relation_section(result, rel)
    return result


def delete_owned_notes(user_id: int, names: list[str]) -> list[str]:
    targets = []
    seen = set()
    for raw in names:
        name = safe_name(raw)
        if name in seen:
            continue
        seen.add(name)
        if is_index_file(name):
            raise PermissionError("Indexは削除できません")
        if file_owner_id(name) != int(user_id):
            raise PermissionError("自分のノートだけ削除できます")
        if not (VAULT / name).exists():
            continue
        targets.append(name)
    if not targets:
        return []

    target_set = set(targets)
    # Remove references before deleting the target files.  Inline links keep
    # their visible text; section-only relation links disappear entirely.
    for md in list(VAULT.glob("*.md")):
        if md.name in target_set:
            continue
        text = md.read_text(encoding="utf-8")
        changed = remove_links_to_targets(text, target_set)
        if changed != text:
            atomic_text_write(md, changed)

    for name in targets:
        try:
            (VAULT / name).unlink()
        except FileNotFoundError:
            pass

    with db_conn() as con:
        for name in targets:
            con.execute("DELETE FROM likes WHERE note_file=?", (name,))
            con.execute("DELETE FROM community_posts WHERE note_file=?", (name,))
            con.execute("DELETE FROM external_edges WHERE source_file=? OR target_file=?", (name,name))

    ratings = load_topic_ratings()
    changed_ratings = False
    if isinstance(ratings, dict):
        for name in targets:
            if name in ratings:
                ratings.pop(name, None); changed_ratings = True
        for source, per_target in list(ratings.items()):
            if not isinstance(per_target, dict):
                continue
            for name in targets:
                if name in per_target:
                    per_target.pop(name, None); changed_ratings = True
            if not per_target:
                ratings.pop(source, None); changed_ratings = True
    if changed_ratings:
        save_topic_ratings(ratings)
    sync_edges()
    return targets


def strip_edge_block(content: str) -> str:
    return EDGE_BLOCK_RE.sub("\n", content).rstrip() + "\n"


def split_yaml_frontmatter(content: str) -> tuple[str, str]:
    """Return (frontmatter_with_delimiters, markdown_body).

    Only a leading ``--- ... ---`` block is YAML. A later ``---`` remains the
    Network Notes Parent/Child direction divider.
    """
    text = str(content or "").replace("\r\n", "\n")
    lines = text.splitlines()
    if not lines or not DIRECTION_DIVIDER_RE.match(lines[0]):
        return "", text
    for i in range(1, len(lines)):
        if DIRECTION_DIVIDER_RE.match(lines[i]):
            frontmatter = "\n".join(lines[:i + 1]).rstrip()
            body = "\n".join(lines[i + 1:])
            return frontmatter, body
    return "", text


def strip_yaml_frontmatter(content: str) -> str:
    _frontmatter, body = split_yaml_frontmatter(content)
    return body


def yaml_created_value(content: str) -> str:
    frontmatter, _body = split_yaml_frontmatter(content)
    if not frontmatter:
        return ""
    for line in frontmatter.splitlines()[1:-1]:
        m = re.match(r"^\s*created\s*:\s*(.*?)\s*$", line, re.IGNORECASE)
        if m:
            # Do not normalize an existing value.  In particular, its original
            # offset documents the timezone in which the note was created.
            return m.group(1).strip().strip('"\'')
    return ""


def local_now_iso() -> str:
    """Current wall time with the runtime environment's UTC offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_note_datetime(value: str) -> datetime:
    """Parse current ISO values and legacy space-separated, offset-less values.

    Legacy Markdown values cannot be assigned a historical timezone safely, so
    they retain their old meaning as local wall time.  Aware values are returned
    as aware datetimes and can therefore be compared by absolute instant.
    """
    raw = str(value or "").strip().strip('"\'')
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def datetime_sort_key(value: str) -> float:
    dt = parse_note_datetime(value)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.timestamp()


def remove_updated_frontmatter(content: str) -> str:
    """Remove the obsolete generated ``updated`` field without touching ``created``."""
    frontmatter, body = split_yaml_frontmatter(content)
    if not frontmatter:
        return content
    lines = frontmatter.splitlines()
    lines = [line for i, line in enumerate(lines)
             if i in {0, len(lines) - 1} or not re.match(r"^\s*updated\s*:\s*", line, re.IGNORECASE)]
    return "\n".join(lines).rstrip() + "\n\n" + body.lstrip("\n")


def split_direction_content(content: str) -> tuple[str, str]:
    """Split Markdown at the semantic Parent/Child ``---`` divider.

    A leading YAML frontmatter block is preserved on the Parent side and is
    never mistaken for the direction divider.
    """
    clean = strip_edge_block(content).rstrip("\n")
    frontmatter, body = split_yaml_frontmatter(clean)
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if DIRECTION_DIVIDER_RE.match(line):
            parent_body = "\n".join(lines[:i]).rstrip()
            parent = (frontmatter + ("\n\n" + parent_body if parent_body else "")).rstrip()
            return parent, "\n".join(lines[i + 1:]).strip()
    parent = (frontmatter + ("\n\n" + body.rstrip() if body.rstrip() else "")).rstrip()
    return parent, ""


def _parse_relation_links(text: str):
    """Parse canonical ``関係::[ノート](file.md)`` edge lines.

    For backward compatibility, legacy ``## 関係`` headings followed by
    standalone Markdown-link lines are also accepted. Inline links in prose
    are never treated as relationship metadata.
    """
    lines = str(text or "").splitlines()
    result = []
    i = 0
    while i < len(lines):
        rm = RELATION_LINK_LINE_RE.match(lines[i])
        if rm:
            relation = rm.group(1).strip()
            label = re.sub(r"\\([\[\]\\])", r"\1", rm.group(2).strip())
            target = Path(urllib.parse.unquote(rm.group(3).strip())).name
            result.append((relation, label, target))
            i += 1
            continue

        hm = HEADING_RE.match(lines[i])
        if not (hm and len(hm.group(1)) == 2):
            i += 1
            continue
        relation = hm.group(2).strip().rstrip("#").strip()
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        while j < len(lines):
            if not lines[j].strip():
                j += 1
                continue
            lm = LINK_LINE_RE.match(lines[j])
            if not lm:
                break
            label = re.sub(r"\\([\[\]\\])", r"\1", lm.group(1).strip())
            target = Path(urllib.parse.unquote(lm.group(2).strip())).name
            result.append((relation, label, target))
            j += 1
        i += 1
    return result


def _strip_relation_edge_sections(segment: str) -> str:
    """Remove relationship metadata while preserving ordinary prose.

    Canonical ``relation::link`` lines are removed directly. Legacy
    ``## relation`` + initial standalone-link blocks are removed as a unit.
    """
    lines = str(segment or "").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if RELATION_LINK_LINE_RE.match(lines[i]):
            i += 1
            continue
        hm = HEADING_RE.match(lines[i])
        if hm and len(hm.group(1)) == 2:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            k = j
            saw_link = False
            while k < len(lines):
                if not lines[k].strip():
                    k += 1
                    continue
                if LINK_LINE_RE.match(lines[k]):
                    saw_link = True
                    k += 1
                    continue
                break
            if saw_link:
                i = k
                while out and not out[-1].strip():
                    out.pop()
                if i < len(lines) and lines[i].strip() and out:
                    out.append("")
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).strip()


def _render_relation_lines(edges: list[tuple[str, str, str]]) -> str:
    """Render canonical edge metadata using one relation per line."""
    seen = set()
    lines = []
    for relation, title, target in edges:
        key = (normalized_relation(relation), target)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{relation}::[{markdown_escape_label(title)}]({target})")
    return "\n".join(lines)


def _compose_segment_with_edges(segment: str, edges: list[tuple[str, str, str]]) -> str:
    """Insert canonical relationship lines after YAML/H1 and before prose."""
    clean = _strip_relation_edge_sections(segment)
    frontmatter, body = split_yaml_frontmatter(clean)
    body = body.strip("\n")
    lines = body.splitlines() if body else []
    title = ""
    rest = body
    if lines and (hm := HEADING_RE.match(lines[0])) and hm.group(1) == "#":
        title = lines[0].rstrip()
        rest = "\n".join(lines[1:]).strip("\n")
    edge_text = _render_relation_lines(edges).strip()
    parts = []
    if frontmatter:
        parts.append(frontmatter.strip())
    if title:
        parts.append(title)
    if edge_text:
        parts.append(edge_text)
    if rest:
        parts.append(rest)
    return "\n\n".join(parts).rstrip()

def remove_index_parent_edges() -> None:
    """Index nodes are roots: remove legacy Parent metadata from every Index."""
    for name in all_md_files():
        if not is_index_file(name):
            continue
        try:
            content=read_file(name); parent,_child=split_direction_content(content)
            clean=_strip_relation_edge_sections(parent).rstrip()
            desired=clean+"\n\n---\n"
            if content.rstrip()!=desired.rstrip(): write_file(name,desired)
        except Exception:
            continue


def parse_outgoing(content: str):
    # Only Parent-side relations are canonical outgoing edges. Child-side
    # relations below ``---`` are derived mirrors/backlinks.
    parent, _child = split_direction_content(content)
    return _parse_relation_links(parent)


def parse_child_edges(content: str):
    _parent, child = split_direction_content(content)
    return _parse_relation_links(child)


def all_md_files():
    ensure_vault()
    return sorted([p.name for p in VAULT.glob("*.md")], key=lambda n: (n != INDEX_FILE, n.lower()))


def migrate_existing_child_side_v41() -> None:
    """One-time migration for files that already used ``---`` + child links.

    Before v41 those links were display/data on the parent page. Preserve them
    by creating the matching canonical Parent edge in each child note before
    Child sides are rebuilt.
    """
    marker = VAULT / ".direction_v41_migrated"
    if marker.exists():
        return
    ensure_vault()
    files = all_md_files()
    contents = {f: read_file(f) for f in files}
    titles = {f: title_of(contents[f], f) for f in files}
    touched: dict[str, str] = {}
    for parent_file in files:
        for relation, _label, child_file in parse_child_edges(contents[parent_file]):
            if child_file not in contents or child_file == parent_file:
                continue
            child_content = touched.get(child_file, contents[child_file])
            exists = any(normalized_relation(rel) == normalized_relation(relation) and target == parent_file
                         for rel, _lab, target in parse_outgoing(child_content))
            if not exists:
                child_content = add_link_to_relation_side(child_content, relation, titles[parent_file], parent_file, "parent")
                touched[child_file] = child_content
    for name, content in touched.items():
        write_file(name, content)
    marker.write_text(datetime.now().isoformat(timespec="seconds") + "\n", encoding="utf-8")


def _render_child_side(edges: list[tuple[str, str, str]]) -> str:
    ordered = []
    seen = set()
    for relation, source_title, source_file in edges:
        key = (normalized_relation(relation), source_file)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((relation, source_title, source_file))
    ordered.sort(key=lambda x: (normalized_relation(x[0]), x[1].casefold(), x[2].casefold()))
    return _render_relation_lines(ordered).strip()


def _render_direction_document(parent: str, child_body: str, child_edges: list[tuple[str, str, str]]) -> str:
    """Preserve Parent/source text exactly and regenerate only derived Child metadata."""
    child_text = _render_child_side(child_edges).strip()
    new = parent.rstrip() + "\n\n---\n"
    child_parts = [x for x in (child_body.strip(), child_text) if x]
    if child_parts:
        new += "\n" + "\n\n".join(child_parts) + "\n"
    return new


def _sync_child_target(target: str, files: list[str] | None = None, contents: dict[str, str] | None = None) -> None:
    """Rebuild just one note's derived Child side from current Parent edges."""
    ensure_vault()
    files = files or all_md_files()
    if target not in files:
        return
    if contents is None:
        contents = {f: read_file(f) for f in files}
    titles = {f: title_of(contents[f], f) for f in files}
    incoming: list[tuple[str, str, str]] = []
    for source in files:
        if source == target:
            continue
        for relation, _label, edge_target in parse_outgoing(contents[source]):
            if edge_target == target:
                incoming.append((relation, titles[source], source))
    current = read_file(target)
    parent, old_child = split_direction_content(current)
    child_body = _strip_relation_edge_sections(old_child)
    new = _render_direction_document(parent, child_body, incoming)
    if new != strip_edge_block(current):
        write_file(target, new)


def sync_source_edges_diff(source: str) -> None:
    with _GRAPH_SYNC_LOCK:
        """Commit one source note's relation changes by updating only affected Child sides.

        Draft saves may already have replaced the source Parent text, so removed old
        relations are discovered from existing Child mirrors. This avoids needing to
        rewrite/canonicalize the source note and makes direct `relation::link` edits stable.
        """
        ensure_vault()
        files = all_md_files()
        if source not in files:
            return
        contents = {f: read_file(f) for f in files}
        affected = {source}
        for _relation, _label, target in parse_outgoing(contents[source]):
            if target in contents and target != source:
                affected.add(target)
        for target in files:
            if target == source:
                continue
            if any(child_source == source for _rel, _label, child_source in parse_child_edges(contents[target])):
                affected.add(target)
        for target in affected:
            _sync_child_target(target, files, contents)


def sync_edges() -> None:
    with _GRAPH_SYNC_LOCK:
        """Rebuild derived Child sides without canonicalizing/reordering Parent source."""
        ensure_vault()
        files = all_md_files()
        contents = {f: read_file(f) for f in files}
        for target in files:
            _sync_child_target(target, files, contents)


def inferred_created_iso(name: str) -> str:
    stem = Path(name).stem.split("__", 1)[-1]
    if re.fullmatch(r"\d{14}", stem):
        try:
            return datetime.strptime(stem, "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp((VAULT / name).stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


CREATOR_METADATA_RE = re.compile(r"^\s*creator::\s*(.*?)\s*$", re.IGNORECASE)


def inferred_creator_username(name: str) -> str:
    """Infer the public creator handle from the stable note filename.

    User-owned notes are named ``username__...md``. Numeric legacy names are
    resolved through the users table when possible. Plain legacy notes retain
    a neutral ``legacy`` creator marker.
    """
    base = Path(name).name
    if "__" in base:
        prefix = base.split("__", 1)[0].strip()
        m = re.fullmatch(r"u(\d+)", prefix, re.IGNORECASE)
        if m:
            try:
                return username_for_user_id(int(m.group(1)))
            except Exception:
                pass
        if prefix:
            return prefix
    return "legacy"


def ensure_creator_metadata(name: str, content: str) -> str:
    """Ensure ``creator::username`` lives inside the leading metadata block.

    Network Notes intentionally keeps the ``creator::`` syntax requested by the
    UI model even inside the frontmatter delimiters. Legacy v65 notes that have
    ``creator::`` immediately below YAML are migrated into the block.
    """
    text = str(content or "").replace("\r\n", "\n")
    frontmatter, body = split_yaml_frontmatter(text)
    creator = ""

    # Prefer an existing creator value inside the leading metadata block.
    fm_lines = frontmatter.splitlines() if frontmatter else []
    if fm_lines:
        for line in fm_lines[1:-1]:
            m = CREATOR_METADATA_RE.match(line)
            if m and m.group(1).strip():
                creator = m.group(1).strip()
                break

    # Migrate the old v65 body-level creator line when present near the top.
    body_lines = body.splitlines()
    first_content = 0
    while first_content < len(body_lines) and not body_lines[first_content].strip():
        first_content += 1
    for i in range(first_content, min(len(body_lines), first_content + 12)):
        line = body_lines[i]
        if not line.strip():
            continue
        m = CREATOR_METADATA_RE.match(line)
        if m and m.group(1).strip():
            if not creator:
                creator = m.group(1).strip()
            del body_lines[i]
            # Remove only the now-redundant leading blank lines around metadata.
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            break
        if HEADING_RE.match(line) or RELATION_LINK_LINE_RE.match(line) or DIRECTION_DIVIDER_RE.match(line):
            break

    inferred_creator = inferred_creator_username(name)
    # User-owned filenames are authoritative. Source editing, backup restore or
    # Local publishing must not be able to impersonate another creator by
    # changing frontmatter text. Plain legacy files may keep their existing tag.
    if inferred_creator != "legacy":
        creator = inferred_creator
    elif not creator:
        creator = inferred_creator

    # Build/normalize the block with creator first and created immediately after.
    created = yaml_created_value(text) or inferred_created_iso(name)
    other_meta = []
    if fm_lines:
        for line in fm_lines[1:-1]:
            if CREATOR_METADATA_RE.match(line):
                continue
            if re.match(r"^\s*created\s*:\s*", line, re.IGNORECASE):
                continue
            other_meta.append(line)
    meta = ["---", f"creator::{creator}", f"created: {created}"]
    meta.extend(other_meta)
    meta.append("---")
    normalized_body = "\n".join(body_lines).lstrip("\n")
    return "\n".join(meta) + ("\n\n" + normalized_body if normalized_body else "\n")


def ensure_creator_metadata_all_notes() -> None:
    ensure_vault()
    for name in all_md_files():
        content = read_file(name)
        updated = ensure_creator_metadata(name, content)
        if updated != content:
            # Direct write avoids recursively changing metadata while migrating.
            atomic_text_write(VAULT / name, updated)


def ensure_created_frontmatter(name: str, content: str) -> str:
    """Ensure each Markdown note has stable YAML ``created`` metadata.

    Existing values are preserved verbatim because changing their offset (or
    guessing one for legacy values) would discard information.
    """
    created = yaml_created_value(content)
    frontmatter, body = split_yaml_frontmatter(content)
    if frontmatter:
        lines = frontmatter.splitlines()
        for i in range(1, len(lines) - 1):
            if re.match(r"^\s*created\s*:\s*", lines[i], re.IGNORECASE):
                value = created or inferred_created_iso(name)
                lines[i] = f"created: {value}"
                normalized_body = body.lstrip("\n")
                return "\n".join(lines).rstrip() + "\n\n" + normalized_body
        value = inferred_created_iso(name)
        lines.insert(len(lines) - 1, f"created: {value}")
        normalized_body = body.lstrip("\n")
        return "\n".join(lines).rstrip() + "\n\n" + normalized_body
    value = inferred_created_iso(name)
    normalized_body = str(content or "").lstrip("\n")
    return f"---\ncreated: {value}\n---\n\n" + normalized_body


def ensure_created_frontmatter_all_notes() -> None:
    ensure_vault()
    for name in all_md_files():
        content = read_file(name)
        updated = ensure_created_frontmatter(name, content)
        if updated != content:
            write_file(name, updated)


def new_note_markdown(filename: str, title: str) -> str:
    created = local_now_iso()
    creator = inferred_creator_username(filename)
    return f"---\ncreator::{creator}\ncreated: {created}\nupdated: {created}\n---\n\n# {title}\n"


def new_timestamp_filename() -> str:
    dt = datetime.now()
    for i in range(120):
        candidate = (dt + timedelta(seconds=i)).strftime("%Y%m%d%H%M%S") + ".md"
        if not (VAULT / candidate).exists():
            return candidate
    raise RuntimeError("Could not allocate timestamp filename")


def _add_link_to_segment(segment: str, relation: str, title: str, target: str) -> str:
    edges = _parse_relation_links(segment)
    relation_norm = normalized_relation(relation)
    exists = any(normalized_relation(rel) == relation_norm and linked == target
                 for rel, _label, linked in edges)
    if not exists:
        edges.append((relation, title, target))
    body = _strip_relation_edge_sections(segment)
    return _compose_segment_with_edges(body, edges).rstrip() + "\n"


def add_link_to_relation_side(content: str, relation: str, title: str, target: str, side: str = "parent") -> str:
    parent, child = split_direction_content(content)
    if side == "parent":
        parent = _add_link_to_segment(parent, relation, title, target).rstrip()
    elif side == "child":
        child = _add_link_to_segment(child, relation, title, target).rstrip()
    else:
        raise ValueError("invalid edge side")
    out = parent.rstrip() + "\n\n---\n"
    if child:
        out += "\n" + child.rstrip() + "\n"
    return out


def add_link_to_relation(content: str, relation: str, title: str, target: str) -> str:
    return add_link_to_relation_side(content, relation, title, target, "parent")


def remove_empty_relation_section(content: str, relation: str) -> str:
    """Canonical `relation::link` metadata has no standalone empty heading.

    Legacy empty relation headings are removed when they contain no prose.
    """
    clean = strip_edge_block(content).rstrip()
    lines = clean.splitlines()
    relation_norm = normalized_relation(relation)
    i = 0
    while i < len(lines):
        hm = HEADING_RE.match(lines[i])
        if not (hm and len(hm.group(1)) == 2 and normalized_relation(hm.group(2).strip().rstrip("#").strip()) == relation_norm):
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not HEADING_RE.match(lines[j]):
            # A canonical relation line/prose means this is not an empty legacy heading.
            if lines[j].strip():
                break
            j += 1
        if j == len(lines) or (j > i + 1 and not any(x.strip() for x in lines[i + 1:j])):
            del lines[i:j]
            continue
        i += 1
    return "\n".join(lines).rstrip() + "\n"


def remove_link_from_relation(content: str, relation: str, target: str) -> str:
    parent, child = split_direction_content(content)
    relation_norm = normalized_relation(relation)
    edges = [
        (rel, label, linked)
        for rel, label, linked in _parse_relation_links(parent)
        if not (normalized_relation(rel) == relation_norm and linked == target)
    ]
    parent_body = _strip_relation_edge_sections(parent)
    parent = _compose_segment_with_edges(parent_body, edges)
    out = parent.rstrip() + "\n\n---\n"
    if child.strip():
        out += "\n" + child.strip() + "\n"
    return out


def remove_exact_edge(content: str, relation: str, target: str) -> str:
    """Remove an exact relation -> target edge and clean the relation heading if it becomes empty."""
    result = remove_link_from_relation(content, relation, target)
    return remove_empty_relation_section(result, relation)


def delete_edges_for_user(user_id: int, current_name: str, direction: str, edges: list[dict]) -> None:
    if not (VAULT / current_name).exists():
        raise ValueError("現在のノートが見つかりません")
    touched: dict[str, str] = {}
    for raw in edges:
        relation = str(raw.get("relation", "")).strip()[:80]
        other = safe_name(str(raw.get("file", "")))
        edge_id = int(raw.get("edge_id") or 0)
        if edge_id:
            with db_conn() as con:
                row=con.execute("SELECT creator_user_id FROM external_edges WHERE id=?",(edge_id,)).fetchone()
                if not row: continue
                if int(row["creator_user_id"])!=int(user_id): raise PermissionError("他のユーザーが追加した関係は削除できません")
                con.execute("DELETE FROM external_edges WHERE id=?",(edge_id,))
            continue
        if not relation or not (VAULT / other).exists():
            continue
        if direction == "outgoing":
            source, target = current_name, other
            if file_owner_id(source) != int(user_id):
                raise PermissionError("このノートのエッジ関係は所有者だけが削除できます")
        elif direction == "incoming":
            source, target = other, current_name
            if file_owner_id(source) != int(user_id):
                raise PermissionError("他のユーザーが作成したエッジ関係は削除できません")
        else:
            raise ValueError("invalid direction")
        content = touched.get(source, read_file(source))
        exists = any(normalized_relation(rel) == normalized_relation(relation) and t == target
                     for rel, _label, t in parse_outgoing(content))
        if not exists:
            continue
        touched[source] = remove_exact_edge(content, relation, target)
        if normalized_relation(relation) in {normalized_relation(x) for x in {"カテゴリー", "トピック", "topic", "topics", "分類"}}:
            remove_topic_rating(source, target)
    for name, content in touched.items():
        write_file(name, content)
    sync_edges()


def remove_topic_rating(source: str, target: str) -> None:
    ratings = load_topic_ratings()
    targets = ratings.get(source)
    if isinstance(targets, dict) and target in targets:
        targets.pop(target, None)
        if not targets:
            ratings.pop(source, None)
        save_topic_ratings(ratings)


def normalized_relation(name: str) -> str:
    return re.sub(r"\s+", "", name).casefold()


V70_RELATION_ALIASES = {
    normalized_relation("トピック"): "カテゴリー",
    normalized_relation("topic"): "カテゴリー",
    normalized_relation("topics"): "カテゴリー",
    normalized_relation("分類"): "カテゴリー",
    normalized_relation("下位カテゴリー"): "分類した",
    normalized_relation("補足"): "補足した",
    normalized_relation("関連"): "関連した",
    normalized_relation("質問"): "質問した",
    normalized_relation("回答"): "回答した",
    normalized_relation("賛成"): "賛成した",
    normalized_relation("肯定"): "賛成した",
    normalized_relation("賛同"): "賛成した",
    normalized_relation("支持"): "賛成した",
    normalized_relation("反対"): "反対した",
    normalized_relation("反論"): "反対した",
    normalized_relation("まとめ"): "まとめた",
}

def migrate_relation_vocabulary_v70() -> None:
    """Canonicalize the former default relation labels without touching custom relations.

    Only relation::Markdown-link lines are rewritten.  Inline prose links and YAML
    metadata are untouched.  The migration is idempotent and intentionally leaves
    legacy/custom relations such as 派生 available as custom vocabulary.
    """
    if not VAULT.exists():
        return
    for md in VAULT.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        changed = False
        out = []
        for line in text.splitlines():
            m = RELATION_LINK_LINE_RE.match(line)
            if m:
                canonical = V70_RELATION_ALIASES.get(normalized_relation(m.group(1)))
                if canonical and canonical != m.group(1).strip():
                    start, end = m.span(1)
                    line = line[:start] + canonical + line[end:]
                    changed = True
            out.append(line)
        if changed:
            atomic_text_write(md, "\n".join(out).rstrip() + "\n")


V72_RELATION_ALIASES = {
    normalized_relation("トピック"): "カテゴリー",
    normalized_relation("topic"): "カテゴリー",
    normalized_relation("topics"): "カテゴリー",
    normalized_relation("分類"): "カテゴリー",
    normalized_relation("下位カテゴリー"): "ノート",
    normalized_relation("分類した"): "ノート",
    normalized_relation("賛成した"): "賛同",
    normalized_relation("賛成"): "賛同",
    normalized_relation("肯定"): "賛同",
    normalized_relation("支持"): "賛同",
    normalized_relation("反対した"): "否定",
    normalized_relation("反対"): "否定",
    normalized_relation("反論"): "否定",
    normalized_relation("質問した"): "質問",
    normalized_relation("回答した"): "回答",
    normalized_relation("関連した"): "関連",
    normalized_relation("言及した"): "言及",
    normalized_relation("雑談した"): "雑談",
}

def migrate_relation_vocabulary_v72() -> None:
    """Move clear legacy synonyms to the v72 basic vocabulary.

    Relations without an unambiguous v72 equivalent (for example 補足した or
    まとめた) are intentionally preserved as custom relations rather than losing
    meaning.
    """
    if not VAULT.exists():
        return
    for md in VAULT.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        changed = False
        out = []
        for line in text.splitlines():
            m = RELATION_LINK_LINE_RE.match(line)
            if m:
                canonical = V72_RELATION_ALIASES.get(normalized_relation(m.group(1)))
                if canonical and canonical != m.group(1).strip():
                    start, end = m.span(1)
                    line = line[:start] + canonical + line[end:]
                    changed = True
            out.append(line)
        if changed:
            atomic_text_write(md, "\n".join(out).rstrip() + "\n")


def load_topic_ratings() -> dict:
    """Ratings are stored per note -> topic edge, not on the topic itself."""
    try:
        data = json.loads(RATING_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_topic_ratings(data: dict) -> None:
    VAULT.mkdir(parents=True, exist_ok=True)
    atomic_text_write(RATING_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def edge_rating_summary(ratings: dict, source: str, target: str, voter: str | None = None) -> dict:
    votes = ratings.get(source, {}).get(target, {})
    if not isinstance(votes, dict):
        votes = {}
    appropriate = sum(1 for v in votes.values() if v == "appropriate")
    inappropriate = sum(1 for v in votes.values() if v == "inappropriate")
    return {
        "appropriate": appropriate,
        "inappropriate": inappropriate,
        "score": appropriate - inappropriate,
        "current_vote": votes.get(voter) if voter else None,
    }

def build_metrics(contents: dict[str, str], ratings: dict | None = None):
    files = list(contents)
    connected = {f: set() for f in files}
    support = {f: set() for f in files}
    oppose = {f: set() for f in files}
    topic_sources = {f: set() for f in files}
    topic_norm = {normalized_relation(x) for x in {"カテゴリー", "トピック", "topic", "topics"}}
    ratings = ratings or {}
    support_norm = {normalized_relation(x) for x in {"賛成した", "肯定", "賛成", "賛同", "支持", "support", "supports"}}
    oppose_norm = {normalized_relation(x) for x in {"反対した", "反論", "反対", "oppose", "opposes", "objection"}}

    outgoing_cache = {source: parse_outgoing(contents[source]) for source in files}
    topic_nodes = {target for source in files for relation, _label, target in outgoing_cache[source]
                   if target in contents and normalized_relation(relation) in topic_norm}

    for source in files:
        for relation, _label, target in outgoing_cache[source]:
            if target not in contents or target == source:
                continue
            connected[source].add(target)
            connected[target].add(source)
            nr = normalized_relation(relation)
            if nr in support_norm:
                support[source].add(target)
                support[target].add(source)
            if nr in oppose_norm:
                oppose[source].add(target)
                oppose[target].add(source)
            # "Use count" means actual ordinary notes using a topic. Topic->topic links
            # define topic structure, but are not counted as a post using the topic.
            if nr in topic_norm and not is_index_file(source) and source not in topic_nodes:
                topic_sources[target].add(source)

    # Aggregate appropriate/inappropriate votes only for CURRENT ordinary-note -> topic edges.
    topic_appropriate = {f: 0 for f in files}
    topic_inappropriate = {f: 0 for f in files}
    valid_topic_targets_by_note = {}
    for source in files:
        if is_index_file(source) or source in topic_nodes:
            continue
        valid_topic_targets_by_note[source] = {
            target for relation, _label, target in outgoing_cache[source]
            if target in contents and normalized_relation(relation) in topic_norm
        }
    for source, targets in ratings.items():
        if source not in valid_topic_targets_by_note or not isinstance(targets, dict):
            continue
        for target, votes in targets.items():
            if target not in valid_topic_targets_by_note[source] or not isinstance(votes, dict):
                continue
            topic_appropriate[target] += sum(1 for v in votes.values() if v == "appropriate")
            topic_inappropriate[target] += sum(1 for v in votes.values() if v == "inappropriate")

    result = {}
    for f in files:
        stem = Path(f).stem
        if re.fullmatch(r"\d{14}", stem):
            created_key = stem
        else:
            created_key = datetime.fromtimestamp((VAULT / f).stat().st_mtime).strftime("%Y%m%d%H%M%S")
        app = topic_appropriate[f]
        inap = topic_inappropriate[f]
        result[f] = {
            "node_count": len(connected[f]),
            "support_count": len(support[f]),
            "oppose_count": len(oppose[f]),
            "created_key": created_key,
            "topic_use_count": len(topic_sources[f]),
            "topic_appropriate": app,
            "topic_inappropriate": inap,
            "topic_score": app - inap,
        }
    return result

def file_payload(name: str, voter: str | None = None):
    files = all_md_files()
    contents = {f: read_file(f) for f in files}
    ratings = load_topic_ratings()
    metrics = build_metrics(contents, ratings)
    content = contents[name]
    title = title_of(content, name)
    outgoing = []
    for relation, label, target in parse_outgoing(content):
        if target in contents:
            outgoing.append({"relation": relation, "title": title_of(contents[target], target) or label, "file": target, "edge_kind":"owner", "owner_set":True, "edge_creator_id":file_owner_id(name), "edge_creator_username":username_for_user_id(file_owner_id(name)) if file_owner_id(name) else ""})
    incoming = []
    for source in files:
        if source == name:
            continue
        for relation, _label, target in parse_outgoing(contents[source]):
            if target == name:
                incoming.append({"relation": relation, "title": title_of(contents[source], source), "file": source, "edge_kind":"owner", "owner_set":True, "edge_creator_id":file_owner_id(source), "edge_creator_username":username_for_user_id(file_owner_id(source)) if file_owner_id(source) else ""})
    topic_norm = {normalized_relation(x) for x in {"カテゴリー", "トピック", "topic", "topics"}}
    is_topic = any(normalized_relation(e["relation"]) in topic_norm for e in incoming)
    topic_edge_ratings = {}
    if not is_index_file(name) and not is_topic:
        for relation, _label, target in parse_outgoing(content):
            if target in contents and normalized_relation(relation) in topic_norm:
                topic_edge_ratings[target] = edge_rating_summary(ratings, name, target, voter)
    return {
        "name": name,
        "title": title,
        "content": content,
        "outgoing": outgoing,
        "incoming": incoming,
        "metrics": metrics,
        "is_topic": is_topic,
        "topic_edge_ratings": topic_edge_ratings,
    }


def files_payload():
    files = all_md_files()
    contents = {f: read_file(f) for f in files}
    items = []
    for f in files:
        # Timestamp filenames (YYYYMMDDHHMMSS.md) are the canonical node creation time.
        # For non-timestamp files, fall back to filesystem mtime.
        stem = Path(f).stem
        dt = None
        if re.fullmatch(r"\d{14}", stem):
            try:
                dt = datetime.strptime(stem, "%Y%m%d%H%M%S")
            except ValueError:
                dt = None
        if dt is None:
            try:
                dt = datetime.fromtimestamp((VAULT / f).stat().st_mtime)
            except OSError:
                dt = datetime.fromtimestamp(0)
        items.append({
            "name": f,
            "title": title_of(contents[f], f),
            "time": int(dt.timestamp()),
            "time_label": dt.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return {"files": items}


def graph_payload(center: str, limit: int = 18, depth: int = 2, viewer_user_id: int | None = None):
    """Return a small undirected neighborhood while preserving directed edge data."""
    files = all_md_files()
    if viewer_user_id is not None:
        files = [f for f in files if can_view_note(int(viewer_user_id), f)]
    if center not in files:
        raise ValueError("Unknown center node")
    limit = max(5, min(int(limit), 50))
    depth = max(1, min(int(depth), 4))
    contents = {f: read_file(f) for f in files}
    titles = {f: title_of(contents[f], f) for f in files}
    all_edges = []
    adjacency = {f: [] for f in files}
    for source in files:
        for relation, _label, target in parse_outgoing(contents[source]):
            if target not in contents or target == source:
                continue
            edge = {"source": source, "target": target, "relation": relation}
            all_edges.append(edge);adjacency[source].append(target);adjacency[target].append(source)
    if not LOCAL_MODE:
        for row in external_edge_rows():
            source,target=row["source_file"],row["target_file"]
            if source not in contents or target not in contents or source==target: continue
            if viewer_user_id is not None and not can_view_user(int(viewer_user_id),int(row["creator_user_id"])): continue
            edge={"source":source,"target":target,"relation":row["relation"],"external":True}
            all_edges.append(edge);adjacency[source].append(target);adjacency[target].append(source)

    chosen = []
    distance = {center: 0}
    queue = [center]
    seen = {center}
    while queue and len(chosen) < limit:
        node = queue.pop(0)
        chosen.append(node)
        d = distance[node]
        if d >= depth:
            continue
        # Keep deterministic order, but prefer neighbors with more local connections.
        neighbors = sorted(set(adjacency[node]), key=lambda x: (-len(set(adjacency[x])), titles[x].casefold(), x))
        for nxt in neighbors:
            if nxt in seen:
                continue
            seen.add(nxt)
            distance[nxt] = d + 1
            queue.append(nxt)
            if len(seen) >= limit * 3:
                break
    chosen = chosen[:limit]
    chosen_set = set(chosen)
    edges = [e for e in all_edges if e["source"] in chosen_set and e["target"] in chosen_set]
    nodes = [{"id": f, "title": titles[f], "distance": distance.get(f, depth)} for f in chosen]
    return {"center": center, "nodes": nodes, "edges": edges}



class AuthRequiredError(Exception):
    pass

def db_conn():
    con = sqlite3.connect(DB_FILE, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    with db_conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              password_hash TEXT NOT NULL,
              display_name TEXT NOT NULL DEFAULT '',
              bio TEXT NOT NULL DEFAULT '',
              avatar_url TEXT NOT NULL DEFAULT '',
              role TEXT NOT NULL DEFAULT 'user',
              status TEXT NOT NULL DEFAULT 'active',
              suspended_reason TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sessions(
              token_hash TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS likes(
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              note_file TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(user_id,note_file)
            );
            CREATE TABLE IF NOT EXISTS communities(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              index_markdown TEXT NOT NULL DEFAULT '# Index\n',
              owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS community_members(
              community_id INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(community_id,user_id)
            );
            CREATE TABLE IF NOT EXISTS community_moderators(
              community_id INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(community_id,user_id)
            );
            CREATE TABLE IF NOT EXISTS community_posts(
              community_id INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
              note_file TEXT NOT NULL,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(community_id,note_file)
            );
            CREATE TABLE IF NOT EXISTS dm_messages(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              recipient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              body TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS dm_pair_idx ON dm_messages(sender_user_id,recipient_user_id,id);
            CREATE TABLE IF NOT EXISTS follows(
              follower_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              followed_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(follower_user_id,followed_user_id)
            );
            CREATE TABLE IF NOT EXISTS dm_clears(
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              other_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              cleared_message_id INTEGER NOT NULL DEFAULT 0,
              cleared_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(user_id,other_user_id)
            );
            CREATE TABLE IF NOT EXISTS community_messages(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              community_id INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              body TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS community_messages_idx ON community_messages(community_id,id);
            CREATE TABLE IF NOT EXISTS blocks(
              blocker_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              blocked_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(blocker_user_id,blocked_user_id)
            );
            CREATE TABLE IF NOT EXISTS reports(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              reporter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              target_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
              note_file TEXT NOT NULL DEFAULT '',
              reason TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS reports_user_idx ON reports(target_user_id,status);
            CREATE INDEX IF NOT EXISTS reports_note_idx ON reports(note_file,status);
            CREATE TABLE IF NOT EXISTS moderation_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              actor_user_id INTEGER,
              actor_username TEXT NOT NULL DEFAULT '',
              action TEXT NOT NULL,
              target_user_id INTEGER,
              target_username TEXT NOT NULL DEFAULT '',
              target_note TEXT NOT NULL DEFAULT '',
              reason TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS local_sync_tokens(
              user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
              token_hash TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS local_published_notes(
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              note_file TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(user_id,note_file)
            );
            CREATE TABLE IF NOT EXISTS local_published_attachments(
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              rel_path TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(user_id,rel_path)
            );
            CREATE TABLE IF NOT EXISTS user_quotas(
              user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
              notes_limit INTEGER NOT NULL,
              note_bytes_limit INTEGER NOT NULL,
              media_bytes_limit INTEGER NOT NULL,
              relations_limit INTEGER NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS global_quotas(
              id INTEGER PRIMARY KEY CHECK(id=1),
              notes_limit INTEGER NOT NULL,
              note_bytes_limit INTEGER NOT NULL,
              media_bytes_limit INTEGER NOT NULL,
              relations_limit INTEGER NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS external_edges(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_file TEXT NOT NULL,
              target_file TEXT NOT NULL,
              relation TEXT NOT NULL,
              creator_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(source_file,target_file,relation,creator_user_id)
            );
            CREATE INDEX IF NOT EXISTS external_edges_source_idx ON external_edges(source_file);
            CREATE INDEX IF NOT EXISTS external_edges_target_idx ON external_edges(target_file);
            CREATE TABLE IF NOT EXISTS saved_searches(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name TEXT NOT NULL,
              query TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(user_id,name)
            );
            CREATE INDEX IF NOT EXISTS saved_searches_user_idx ON saved_searches(user_id,id);
            CREATE UNIQUE INDEX IF NOT EXISTS local_sync_token_hash_idx ON local_sync_tokens(token_hash);
            CREATE TABLE IF NOT EXISTS rate_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              event_type TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS rate_events_idx ON rate_events(user_id,event_type,created_at);
            CREATE TABLE IF NOT EXISTS registration_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ip_hash TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS registration_events_idx ON registration_events(ip_hash,created_at);
            """
        )
        # Safe migrations for databases created by older NetworkNotes builds.
        columns = {str(r[1]) for r in con.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        if "status" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        if "suspended_reason" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN suspended_reason TEXT NOT NULL DEFAULT ''")
        community_columns = {str(r[1]) for r in con.execute("PRAGMA table_info(communities)").fetchall()}
        if "index_markdown" not in community_columns:
            con.execute("ALTER TABLE communities ADD COLUMN index_markdown TEXT NOT NULL DEFAULT '# Index\n'")
        con.execute("""INSERT OR IGNORE INTO global_quotas(id,notes_limit,note_bytes_limit,media_bytes_limit,relations_limit)
                       VALUES(1,?,?,?,?)""", (MAX_NOTES_PER_USER,MAX_NOTE_STORAGE_BYTES,MAX_MEDIA_STORAGE_BYTES,MAX_RELATIONS_PER_USER))
        # There is exactly one immutable owner. Prefer the existing Yurii account
        # when present, otherwise preserve the oldest account as installation owner.
        owner = con.execute("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1").fetchone()
        if not owner:
            preferred = con.execute("SELECT id FROM users WHERE username='Yurii' COLLATE NOCASE ORDER BY id LIMIT 1").fetchone()
            fallback = preferred or con.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
            if fallback:
                con.execute("UPDATE users SET role='owner' WHERE id=?", (int(fallback[0]),))
    ensure_all_community_indexes()


def migrate_https_asset_urls() -> None:
    """Normalize legacy same-origin HTTP media URLs from older builds."""
    http_prefix = "http://network-notes.duckdns.org/"
    https_prefix = "https://network-notes.duckdns.org/"
    with db_conn() as con:
        rows = con.execute("SELECT id, avatar_url FROM users WHERE avatar_url <> ''").fetchall()
        for row in rows:
            old_url = str(row["avatar_url"] or "")
            new_url = normalize_same_origin_url(old_url)
            if new_url != old_url:
                con.execute("UPDATE users SET avatar_url=? WHERE id=?", (new_url, int(row["id"])))

    ensure_vault()
    for path in VAULT.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text = text.replace(http_prefix + "media/", "/media/")
        new_text = new_text.replace(https_prefix + "media/", "/media/")
        if new_text != text:
            atomic_text_write(path, new_text)


def validate_username(raw: str) -> str:
    """Return a stable public username suitable for links and filenames."""
    username = str(raw or "").strip()
    if not (2 <= len(username) <= 32):
        raise ValueError("ユーザー名は2〜32文字にしてください")
    if not username[0].isalnum():
        raise ValueError("ユーザー名は文字または数字で始めてください")
    if "__" in username:
        raise ValueError("ユーザー名に連続した __ は使えません")
    if re.fullmatch(r"u\d+", username, re.IGNORECASE):
        raise ValueError("u+数字 のユーザー名は予約されています")
    for ch in username:
        if not (ch.isalnum() or ch in "._-"):
            raise ValueError("ユーザー名に使えるのは文字・数字・. _ - です")
    return username


def username_for_user_id(user_id: int) -> str:
    with db_conn() as con:
        row = con.execute("SELECT username FROM users WHERE id=?", (int(user_id),)).fetchone()
    if not row:
        raise ValueError("ユーザーが見つかりません")
    return str(row["username"])


def community_index_filename(community_id: int) -> str:
    return f"community~{int(community_id)}__Index.md"


def community_index_id(name: str) -> int | None:
    m=re.fullmatch(r"community~(\d+)__Index\.md",Path(name).name)
    return int(m.group(1)) if m else None


def community_row(community_id: int):
    with db_conn() as con: return con.execute("SELECT * FROM communities WHERE id=?",(int(community_id),)).fetchone()


def is_community_member(user_id: int, community_id: int) -> bool:
    if not int(user_id or 0): return False
    with db_conn() as con: return bool(con.execute("SELECT 1 FROM community_members WHERE community_id=? AND user_id=?",(int(community_id),int(user_id))).fetchone())


def is_community_moderator(user_id: int, community_id: int) -> bool:
    if not int(user_id or 0): return False
    with db_conn() as con: return bool(con.execute("SELECT 1 FROM community_moderators WHERE community_id=? AND user_id=?",(int(community_id),int(user_id))).fetchone())


def can_manage_community(user_id: int, community_id: int) -> bool:
    row=community_row(community_id)
    if not row: return False
    return int(row["owner_user_id"])==int(user_id or 0) or is_moderator_user(int(user_id or 0)) or is_community_moderator(int(user_id or 0),community_id)


def can_manage_community_roles(user_id: int, community_id: int) -> bool:
    row=community_row(community_id)
    if not row: return False
    return int(row["owner_user_id"])==int(user_id or 0) or is_moderator_user(int(user_id or 0))


def ensure_community_index(community_id: int) -> str:
    row=community_row(community_id)
    if not row: raise ValueError("コミュニティが見つかりません")
    name=community_index_filename(community_id); path=VAULT/name
    if not path.exists():
        creator=username_for_user_id(int(row["owner_user_id"])); created=local_now_iso()
        legacy=str(row["index_markdown"] or "# Index\n").strip()
        if not re.search(r"(?m)^#\s+",legacy): legacy="# Index\n\n"+legacy
        atomic_text_write(path, f"---\ncreator::{creator}\ncreated: {created}\nupdated: {created}\n---\n\n{legacy.rstrip()}\n\n---\n")
    return name


def ensure_all_community_indexes() -> None:
    with db_conn() as con: ids=[int(r[0]) for r in con.execute("SELECT id FROM communities ORDER BY id").fetchall()]
    for cid in ids:
        try: ensure_community_index(cid)
        except Exception: pass


def can_edit_note(user_id: int, name: str) -> bool:
    cid=community_index_id(name)
    if cid is not None: return can_manage_community(int(user_id or 0),cid)
    return file_owner_id(name)==int(user_id or 0)


def can_create_child_from(user_id: int, source: str) -> bool:
    cid=community_index_id(source)
    if cid is not None: return is_community_member(int(user_id or 0),cid) or can_manage_community(int(user_id or 0),cid)
    return file_owner_id(source)==int(user_id or 0)


def is_index_file(name: str) -> bool:
    base = Path(name).name
    return base == INDEX_FILE or base.endswith("__Index.md")


def file_owner_id(name: str) -> int | None:
    base = Path(name).name
    cid=community_index_id(base)
    if cid is not None:
        row=community_row(cid); return int(row["owner_user_id"]) if row else None
    # Backward compatibility while old uN__ filenames are being migrated.
    m = re.match(r"^u(\d+)__", base)
    if m:
        return int(m.group(1))
    if "__" not in base:
        return None
    username = base.split("__", 1)[0]
    with db_conn() as con:
        row = con.execute("SELECT id FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
    return int(row["id"]) if row else None


def index_filename(user_id: int) -> str:
    return f"{username_for_user_id(user_id)}__Index.md"


def user_node_filename(user_id: int) -> str:
    username = username_for_user_id(user_id)
    dt = datetime.now()
    for i in range(120):
        stamp = (dt + timedelta(seconds=i)).strftime("%Y%m%d%H%M%S")
        candidate = f"{username}__{stamp}.md"
        if not (VAULT / candidate).exists():
            return candidate
    raise RuntimeError("Could not allocate timestamp filename")


def ensure_user_index(user_id: int) -> str:
    ensure_vault()
    name = index_filename(user_id)
    p = VAULT / name
    if not p.exists():
        created = local_now_iso()
        creator = username_for_user_id(user_id)
        atomic_text_write(p, f"---\ncreator::{creator}\ncreated: {created}\nupdated: {created}\n---\n\n# Index\n\n---\n")
    return name


def repair_index_titles() -> None:
    """Restore the required ``# Index`` heading if an existing Index is blank/malformed."""
    ensure_vault()
    for name in all_md_files():
        if not is_index_file(name):
            continue
        content = read_file(name)
        if any((m := HEADING_RE.match(line)) and m.group(1) == "#" for line in content.splitlines()):
            continue
        frontmatter, body = split_yaml_frontmatter(content)
        body = body.lstrip("\n")
        repaired_body = "# Index\n\n" + body
        repaired = (frontmatter.rstrip() + "\n\n" if frontmatter else "") + repaired_body
        write_file(name, repaired)


def user_from_id(user_id: int) -> dict | None:
    with db_conn() as con:
        row = con.execute("SELECT id,username,display_name,bio,avatar_url,role,status,suspended_reason,created_at FROM users WHERE id=?", (int(user_id),)).fetchone()
    return dict(row) if row else None


def public_user(user_id: int | None) -> dict:
    if not user_id:
        return {"id": None, "username": "legacy", "display_name": "Legacy", "bio": "", "avatar_url": "", "role": "user", "status": "active"}
    row = user_from_id(user_id)
    if not row:
        return {"id": user_id, "username": f"user{user_id}", "display_name": "", "bio": "", "avatar_url": "", "role": "user", "status": "active"}
    return row


def normalize_same_origin_url(url: str) -> str:
    """Return a relative URL for this site's own assets."""
    value = str(url or "").strip()
    for prefix in (
        "http://network-notes.duckdns.org/",
        "https://network-notes.duckdns.org/",
    ):
        if value.startswith(prefix):
            return "/" + value[len(prefix):]
    return value


def profile_for_user(user: dict) -> dict:
    out = public_user(int(user["id"]))
    out["avatar_url"] = normalize_same_origin_url(out.get("avatar_url", ""))
    out["index_file"] = ensure_user_index(int(user["id"]))
    out["local_mode"] = bool(LOCAL_MODE)
    if LOCAL_MODE:
        cfg = local_config()
        out["web_connected"] = bool(cfg.get("token") and cfg.get("remote_username"))
        out["remote_username"] = str(cfg.get("remote_username") or "")
        out["local_workspace"] = True
    out["quota"] = quota_usage(int(user["id"])) if int(user["id"]) else {}
    return out


def save_user_profile(user_id: int, data: dict) -> dict:
    # Username is the permanent public identity and can never be changed here.
    display_name = str(data.get("display_name", "")).strip()[:120]
    bio = str(data.get("bio", "")).strip()[:1000]
    with db_conn() as con:
        con.execute("UPDATE users SET display_name=?,bio=? WHERE id=?", (display_name, bio, int(user_id)))
    return profile_for_user({"id": int(user_id)})



# ------------------------- v68 safety / local-first helpers -------------------------

def user_role(user_id: int) -> str:
    with db_conn() as con:
        row = con.execute("SELECT role FROM users WHERE id=?", (int(user_id),)).fetchone()
    return str(row[0]) if row else "user"


def is_moderator_user(user_id: int) -> bool:
    return user_role(user_id) in {"owner", "moderator"}


def blocked_user_ids(viewer_user_id: int) -> set[int]:
    with db_conn() as con:
        return {int(r[0]) for r in con.execute(
            "SELECT blocked_user_id FROM blocks WHERE blocker_user_id=?", (int(viewer_user_id),)
        ).fetchall()}


def report_count_for_user(user_id: int) -> int:
    with db_conn() as con:
        return int(con.execute(
            "SELECT COUNT(DISTINCT reporter_user_id) FROM reports WHERE target_user_id=? AND note_file='' AND status='open'",
            (int(user_id),),
        ).fetchone()[0])


def report_count_for_note(note_file: str) -> int:
    with db_conn() as con:
        return int(con.execute(
            "SELECT COUNT(DISTINCT reporter_user_id) FROM reports WHERE note_file=? AND status='open'",
            (str(note_file),),
        ).fetchone()[0])


def user_globally_hidden(user_id: int | None) -> bool:
    if not user_id:
        return False
    with db_conn() as con:
        row = con.execute("SELECT status,role FROM users WHERE id=?", (int(user_id),)).fetchone()
    if not row:
        return True
    if str(row["role"]) == "owner":
        return False
    return str(row["status"]) != "active" or report_count_for_user(int(user_id)) >= REPORT_HIDE_THRESHOLD


def can_view_user(viewer_user_id: int, target_user_id: int | None) -> bool:
    if not target_user_id or int(target_user_id) == int(viewer_user_id):
        return True
    # Personal blocking always wins in normal browsing, including for Owner/Moderator.
    # The moderation dashboard intentionally bypasses this function so moderators
    # can still review and act on blocked accounts when needed.
    if int(target_user_id) in blocked_user_ids(int(viewer_user_id)):
        return False
    if is_moderator_user(int(viewer_user_id)):
        return True
    return not user_globally_hidden(int(target_user_id))


def can_view_note(viewer_user_id: int, note_file: str) -> bool:
    cid=community_index_id(note_file)
    if cid is not None: return community_row(cid) is not None
    owner = file_owner_id(note_file)
    if owner == int(viewer_user_id):
        return True
    if is_moderator_user(int(viewer_user_id)):
        return True
    if not can_view_user(int(viewer_user_id), owner):
        return False
    return report_count_for_note(note_file) < REPORT_HIDE_THRESHOLD


def moderation_log(actor_user_id: int, action: str, target_user_id: int | None = None,
                   target_note: str = "", reason: str = "") -> None:
    actor = public_user(actor_user_id)
    target = public_user(target_user_id) if target_user_id else {}
    with db_conn() as con:
        con.execute(
            """INSERT INTO moderation_log(actor_user_id,actor_username,action,target_user_id,target_username,target_note,reason)
               VALUES(?,?,?,?,?,?,?)""",
            (int(actor_user_id), str(actor.get("username", "")), str(action),
             int(target_user_id) if target_user_id else None, str(target.get("username", "")),
             str(target_note or ""), str(reason or "")[:1000]),
        )


def global_quota_limits() -> dict:
    defaults = {"notes_limit": MAX_NOTES_PER_USER, "note_bytes_limit": MAX_NOTE_STORAGE_BYTES,
                "media_bytes_limit": MAX_MEDIA_STORAGE_BYTES, "relations_limit": MAX_RELATIONS_PER_USER}
    if LOCAL_MODE:
        return defaults
    with db_conn() as con:
        row = con.execute("SELECT notes_limit,note_bytes_limit,media_bytes_limit,relations_limit FROM global_quotas WHERE id=1").fetchone()
    return {k: max(1, int(row[k])) for k in defaults} if row else defaults


def quota_limits(user_id: int) -> dict:
    defaults = global_quota_limits()
    if LOCAL_MODE:
        return defaults
    with db_conn() as con:
        row = con.execute("SELECT notes_limit,note_bytes_limit,media_bytes_limit,relations_limit FROM user_quotas WHERE user_id=?", (int(user_id),)).fetchone()
    if not row:
        return defaults
    return {k: max(1, int(row[k])) for k in defaults}


def set_global_quota_limits(actor_user_id: int, data: dict) -> dict:
    if user_role(int(actor_user_id)) != "owner":
        raise PermissionError("全体の使用可能量はOwnerだけが変更できます")
    def bounded(key, default, maximum):
        try: value=int(data.get(key,default))
        except Exception: value=default
        return max(1,min(value,maximum))
    vals={
      "notes_limit":bounded("notes_limit",MAX_NOTES_PER_USER,1000000),
      "note_bytes_limit":bounded("note_bytes_limit",MAX_NOTE_STORAGE_BYTES,100*1024*1024*1024),
      "media_bytes_limit":bounded("media_bytes_limit",MAX_MEDIA_STORAGE_BYTES,1000*1024*1024*1024),
      "relations_limit":bounded("relations_limit",MAX_RELATIONS_PER_USER,10000000),
    }
    with db_conn() as con:
        con.execute("""INSERT INTO global_quotas(id,notes_limit,note_bytes_limit,media_bytes_limit,relations_limit,updated_at)
                       VALUES(1,?,?,?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(id) DO UPDATE SET notes_limit=excluded.notes_limit,note_bytes_limit=excluded.note_bytes_limit,
                       media_bytes_limit=excluded.media_bytes_limit,relations_limit=excluded.relations_limit,updated_at=CURRENT_TIMESTAMP""",
                    (vals["notes_limit"],vals["note_bytes_limit"],vals["media_bytes_limit"],vals["relations_limit"]))
    moderation_log(int(actor_user_id),"set_global_quota",reason=json.dumps(vals,ensure_ascii=False))
    return vals


def external_edge_rows(*, source: str | None = None, target: str | None = None) -> list[dict]:
    where=[];args=[]
    if source is not None: where.append("e.source_file=?");args.append(str(source))
    if target is not None: where.append("e.target_file=?");args.append(str(target))
    sql="""SELECT e.id,e.source_file,e.target_file,e.relation,e.creator_user_id,e.created_at,u.username creator_username
           FROM external_edges e JOIN users u ON u.id=e.creator_user_id"""
    if where: sql += " WHERE "+" AND ".join(where)
    sql += " ORDER BY e.id"
    with db_conn() as con: return [dict(r) for r in con.execute(sql,args).fetchall()]


def add_external_edge(creator_user_id: int, source: str, target: str, relation: str) -> int:
    source=safe_name(source);target=safe_name(target);relation=str(relation).strip()[:80]
    if not relation or source==target: raise ValueError("関係を確認してください")
    if not (VAULT/source).exists() or not (VAULT/target).exists(): raise ValueError("ノートが見つかりません")
    limits=quota_limits(int(creator_user_id));usage=quota_usage(int(creator_user_id))
    with db_conn() as con:
        exists=con.execute("SELECT id FROM external_edges WHERE source_file=? AND target_file=? AND relation=? AND creator_user_id=?",(source,target,relation,int(creator_user_id))).fetchone()
        if exists: return int(exists[0])
        if usage["relations"]+1>limits["relations_limit"]: raise ValueError("関係数の上限に達しています")
        cur=con.execute("INSERT INTO external_edges(source_file,target_file,relation,creator_user_id) VALUES(?,?,?,?)",(source,target,relation,int(creator_user_id)))
        return int(cur.lastrowid)


def set_user_quota(actor_user_id: int, target_user_id: int, data: dict) -> dict:
    if not is_moderator_user(int(actor_user_id)):
        raise PermissionError("管理権限が必要です")
    target = user_from_id(int(target_user_id))
    if not target:
        raise ValueError("ユーザーが見つかりません")
    def bounded(key, default, maximum):
        try: value = int(data.get(key, default))
        except Exception: value = default
        return max(1, min(value, maximum))
    vals = {
        "notes_limit": bounded("notes_limit", MAX_NOTES_PER_USER, 1000000),
        "note_bytes_limit": bounded("note_bytes_limit", MAX_NOTE_STORAGE_BYTES, 100 * 1024 * 1024 * 1024),
        "media_bytes_limit": bounded("media_bytes_limit", MAX_MEDIA_STORAGE_BYTES, 1000 * 1024 * 1024 * 1024),
        "relations_limit": bounded("relations_limit", MAX_RELATIONS_PER_USER, 10000000),
    }
    with db_conn() as con:
        con.execute("""INSERT INTO user_quotas(user_id,notes_limit,note_bytes_limit,media_bytes_limit,relations_limit,updated_at)
                       VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET notes_limit=excluded.notes_limit,note_bytes_limit=excluded.note_bytes_limit,
                       media_bytes_limit=excluded.media_bytes_limit,relations_limit=excluded.relations_limit,updated_at=CURRENT_TIMESTAMP""",
                    (int(target_user_id), vals["notes_limit"], vals["note_bytes_limit"], vals["media_bytes_limit"], vals["relations_limit"]))
    moderation_log(int(actor_user_id), "set_quota", int(target_user_id), reason=json.dumps(vals, ensure_ascii=False))
    return quota_usage(int(target_user_id))


def quota_usage(user_id: int) -> dict:
    uid = int(user_id)
    files = user_files(uid) if user_from_id(uid) else []
    note_bytes = 0; relations = 0
    for name in files:
        p = VAULT / name
        try:
            note_bytes += p.stat().st_size; relations += len(parse_outgoing(read_file(name)))
        except OSError: pass
    if not LOCAL_MODE:
        with db_conn() as con:
            relations += int(con.execute("SELECT COUNT(*) FROM external_edges WHERE creator_user_id=?", (uid,)).fetchone()[0])
    media_bytes = 0; folder = MEDIA_DIR / f"u{uid}"
    if folder.exists():
        for p in folder.rglob("*"):
            if p.is_file():
                try: media_bytes += p.stat().st_size
                except OSError: pass
    limits = quota_limits(uid)
    return {"notes":len(files),"note_bytes":note_bytes,"media_bytes":media_bytes,"relations":relations,**limits}


def enforce_note_write_quota(user_id: int, name: str, content: str) -> None:
    if LOCAL_MODE: return
    raw = str(content or "").encode("utf-8")
    if len(raw) > MAX_NOTE_BYTES: raise ValueError("1ノートの上限は100KBです")
    usage = quota_usage(int(user_id)); p = VAULT / name; old_size = p.stat().st_size if p.exists() else 0
    if not p.exists() and usage["notes"] >= usage["notes_limit"]: raise ValueError("ノート数の上限に達しています")
    if usage["note_bytes"] - old_size + len(raw) > usage["note_bytes_limit"]: raise ValueError("ノート保存容量の上限に達しています")
    own_other = usage["relations"] - (len(parse_outgoing(read_file(name))) if p.exists() else 0)
    if own_other + len(parse_outgoing(content)) > usage["relations_limit"]: raise ValueError("関係数の上限に達しています")


def check_and_record_rate(user_id: int, event_type: str) -> None:
    if LOCAL_MODE or is_moderator_user(int(user_id)):
        return
    uid = int(user_id)
    with db_conn() as con:
        con.execute("DELETE FROM rate_events WHERE created_at < datetime('now','-2 days')")
        minute = int(con.execute(
            "SELECT COUNT(*) FROM rate_events WHERE user_id=? AND event_type=? AND created_at >= datetime('now','-1 minute')",
            (uid, event_type),
        ).fetchone()[0])
        day = int(con.execute(
            "SELECT COUNT(*) FROM rate_events WHERE user_id=? AND event_type=? AND created_at >= datetime('now','-1 day')",
            (uid, event_type),
        ).fetchone()[0])
        if event_type == "note_create" and minute >= MAX_NOTE_CREATES_PER_MINUTE:
            raise ValueError("短時間のノート作成数が上限に達しました。少し待ってください")
        if event_type == "note_create" and day >= MAX_NOTE_CREATES_PER_DAY:
            raise ValueError("本日のノート作成数が上限に達しました")
        con.execute("INSERT INTO rate_events(user_id,event_type) VALUES(?,?)", (uid, event_type))


def registration_ip_hash(ip: str) -> str:
    return hashlib.sha256((str(ip or "unknown") + "|networknotes-registration").encode("utf-8")).hexdigest()


def check_registration_rate(ip: str) -> None:
    if LOCAL_MODE:
        return
    h = registration_ip_hash(ip)
    with db_conn() as con:
        con.execute("DELETE FROM registration_events WHERE created_at < datetime('now','-2 days')")
        hour = int(con.execute(
            "SELECT COUNT(*) FROM registration_events WHERE ip_hash=? AND created_at >= datetime('now','-1 hour')", (h,)
        ).fetchone()[0])
        day = int(con.execute(
            "SELECT COUNT(*) FROM registration_events WHERE ip_hash=? AND created_at >= datetime('now','-1 day')", (h,)
        ).fetchone()[0])
        if hour >= 3 or day >= 10:
            raise ValueError("この接続元からのアカウント作成が多すぎます。時間を置いてください")
        con.execute("INSERT INTO registration_events(ip_hash) VALUES(?)", (h,))


def _frontmatter_directive_values(content: str, key: str) -> list[str]:
    fm, _ = split_yaml_frontmatter(content)
    if not fm:
        return []
    rx = re.compile(r"^\s*" + re.escape(key) + r"::\s*(.*?)\s*$", re.IGNORECASE)
    values = []
    for line in fm.splitlines()[1:-1]:
        m = rx.match(line)
        if m: values.append(m.group(1).strip())
    return values


def _set_frontmatter_directive(content: str, key: str, values: list[str]) -> str:
    fm, body = split_yaml_frontmatter(content)
    if not fm:
        content = ensure_created_frontmatter("note.md", content)
        fm, body = split_yaml_frontmatter(content)
    lines = fm.splitlines()
    rx = re.compile(r"^\s*" + re.escape(key) + r"::", re.IGNORECASE)
    kept = [lines[0]] + [line for line in lines[1:-1] if not rx.match(line)]
    for v in values:
        kept.append(f"{key}::{v}")
    kept.append("---")
    return "\n".join(kept).rstrip() + "\n\n" + body.lstrip("\n")


def note_upload_enabled(content: str) -> bool:
    values = _frontmatter_directive_values(content, "upload")
    if not values:
        return not LOCAL_MODE
    return str(values[-1]).strip().casefold() not in {"0", "false", "off", "no", "非公開"}


def set_note_upload_enabled(content: str, enabled: bool) -> str:
    return _set_frontmatter_directive(content, "upload", ["true" if enabled else "false"])


def note_private_targets(content: str) -> set[str]:
    return {Path(urllib.parse.unquote(v)).name for v in _frontmatter_directive_values(content, "private_link") if v}


def set_note_private_target(content: str, target: str, private: bool) -> str:
    target = Path(str(target)).name
    vals = list(note_private_targets(content))
    s = set(vals)
    if private: s.add(target)
    else: s.discard(target)
    return _set_frontmatter_directive(content, "private_link", sorted(s))


def strip_local_only_metadata(content: str) -> str:
    out = str(content or "")
    for key in ("upload", "private_link"):
        out = _set_frontmatter_directive(out, key, [])
    return out


def hard_delete_user(actor_user_id: int, target_user_id: int, reason: str = "") -> dict:
    actor_user_id = int(actor_user_id); target_user_id = int(target_user_id)
    if not is_moderator_user(actor_user_id):
        raise PermissionError("管理権限が必要です")
    target = user_from_id(target_user_id)
    if not target:
        raise ValueError("ユーザーが見つかりません")
    if str(target.get("role")) == "owner":
        raise PermissionError("Ownerは削除できません")
    if str(target.get("role")) == "moderator" and user_role(actor_user_id) != "owner":
        raise PermissionError("Moderatorを削除できるのはOwnerだけです")
    target_files = user_files(target_user_id)
    target_set = set(target_files)
    for md in list(VAULT.glob("*.md")):
        if md.name in target_set:
            continue
        try:
            text = md.read_text(encoding="utf-8")
            changed = remove_links_to_targets(text, target_set)
            if changed != text:
                atomic_text_write(md, changed)
        except OSError:
            pass
    for name in target_files:
        try: (VAULT / name).unlink()
        except FileNotFoundError: pass
    media_folder = MEDIA_DIR / f"u{target_user_id}"
    if media_folder.exists():
        import shutil
        shutil.rmtree(media_folder, ignore_errors=True)
    moderation_log(actor_user_id, "delete_user", target_user_id, reason=reason)
    with db_conn() as con:
        # note_file is not a foreign key, so remove references to deleted notes
        # explicitly before deleting the account.
        if target_files:
            marks = ",".join("?" for _ in target_files)
            con.execute(f"DELETE FROM likes WHERE note_file IN ({marks})", tuple(target_files))
            con.execute(f"DELETE FROM community_posts WHERE note_file IN ({marks})", tuple(target_files))
        con.execute("DELETE FROM users WHERE id=?", (target_user_id,))
    sync_edges()
    return {"deleted_user": target.get("username"), "deleted_notes": len(target_files)}


def backup_zip_bytes(user_id: int) -> bytes:
    uid = int(user_id); user = public_user(uid); files = user_files(uid)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        manifest = {
            "format": "networknotes-backup", "version": 1,
            "username": user.get("username", ""),
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": files,
        }
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name in files:
            z.writestr("notes/" + name, read_file(name))
        media_folder = MEDIA_DIR / f"u{uid}"
        if media_folder.exists():
            for p in media_folder.rglob("*"):
                if p.is_file():
                    z.write(p, "attachments/" + p.relative_to(media_folder).as_posix())
    return out.getvalue()


def import_backup_zip(user_id: int, raw: bytes, destination_mapping: dict[str,str] | None = None) -> dict:
    if len(raw) > 200 * 1024 * 1024:
        raise ValueError("バックアップが大きすぎます")
    uid = int(user_id); username = username_for_user_id(uid)
    try:
        z = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile:
        raise ValueError("有効なNetworkNotesバックアップZIPではありません")
    with z:
        try: manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        except Exception: raise ValueError("manifest.jsonが見つかりません")
        if manifest.get("format") != "networknotes-backup":
            raise ValueError("NetworkNotesバックアップではありません")
        note_entries = [n for n in z.namelist() if n.startswith("notes/") and n.endswith(".md") and ".." not in Path(n).parts]
        if len(note_entries) > quota_limits(uid)["notes_limit"] and not LOCAL_MODE:
            raise ValueError("ノート数が上限を超えています")
        declared_note_bytes = sum(int(z.getinfo(n).file_size) for n in note_entries)
        if not LOCAL_MODE and declared_note_bytes > quota_limits(uid)["note_bytes_limit"]:
            raise ValueError("バックアップのノート容量が上限を超えています")
        if LOCAL_MODE and declared_note_bytes > 200 * 1024 * 1024:
            raise ValueError("バックアップのノート容量が大きすぎます")
        old_username = str(manifest.get("username", "")).strip()
        mapping = {}
        contents = {}
        explicit_mapping = destination_mapping if isinstance(destination_mapping, dict) else {}
        for entry in note_entries:
            old = Path(entry).name
            if old in explicit_mapping:
                new = safe_name(str(explicit_mapping[old]))
            elif "__" in old:
                suffix = old.split("__", 1)[1]
                new = f"{username}__{suffix}"
            elif is_index_file(old):
                new = index_filename(uid)
            else:
                # Legacy portable files become timestamp-based owned notes.
                new = user_node_filename(uid)
            mapping[old] = new
            contents[old] = z.read(entry).decode("utf-8")
        imported_total = sum(len(v.encode("utf-8")) for v in contents.values())
        if not LOCAL_MODE and imported_total > quota_limits(uid)["note_bytes_limit"]:
            raise ValueError("バックアップのノート容量が上限を超えています")
        for old, content in list(contents.items()):
            for a, b in mapping.items():
                content = content.replace(a, b)
            content = re.sub(r"/media/u\d+/", f"/media/u{uid}/", content)
            # Imported material belongs to the account performing the restore.
            content = ensure_creator_metadata(mapping[old], content)
            enforce_note_write_quota(uid, mapping[old], content)
            write_file(mapping[old], content)
        folder = MEDIA_DIR / f"u{uid}"; folder.mkdir(parents=True, exist_ok=True)
        imported_media = 0
        attachment_entries = [entry for entry in z.namelist()
                              if entry.startswith("attachments/") and not entry.endswith("/") and ".." not in Path(entry).parts]
        declared_media_bytes = sum(int(z.getinfo(entry).file_size) for entry in attachment_entries)
        if not LOCAL_MODE and declared_media_bytes > quota_limits(uid)["media_bytes_limit"]:
            raise ValueError("添付ファイル容量の上限を超えています")
        if LOCAL_MODE and declared_media_bytes > 2 * 1024 * 1024 * 1024:
            raise ValueError("バックアップの添付容量が大きすぎます")
        for entry in attachment_entries:
            info = z.getinfo(entry)
            if int(info.file_size) > MAX_ATTACHMENT_BYTES:
                continue
            rel = Path(entry).relative_to("attachments")
            data = z.read(entry)
            if len(data) > MAX_ATTACHMENT_BYTES:
                continue
            dest = folder / rel
            old_size = dest.stat().st_size if dest.exists() else 0
            if not LOCAL_MODE and quota_usage(uid)["media_bytes"] - old_size + len(data) > quota_usage(uid)["media_bytes_limit"]:
                raise ValueError("添付ファイル容量の上限を超えています")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data); imported_media += 1
    ensure_created_frontmatter_all_notes(); ensure_creator_metadata_all_notes(); sync_edges()
    return {"notes": len(contents), "attachments": imported_media, "index_file": index_filename(uid)}


def save_attachment(user_id: int, data_url: str, original_name: str) -> dict:
    m = re.match(r"^data:([\w.+-]+/[\w.+-]+);base64,(.+)$", str(data_url or ""), re.DOTALL)
    if not m:
        raise ValueError("添付ファイルを読み込めません")
    declared_mime = m.group(1).lower()
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        raise ValueError("添付ファイルを読み込めません")
    if len(raw) > MAX_ATTACHMENT_BYTES:
        raise ValueError("1ファイルの上限は10MBです")
    uid = int(user_id)
    if not LOCAL_MODE and quota_usage(uid)["media_bytes"] + len(raw) > quota_usage(uid)["media_bytes_limit"]:
        raise ValueError("添付ファイル容量の上限に達しています")
    safe_original = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_name or "file").name)[:120] or "file"
    suffix = Path(safe_original).suffix.lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    text_exts = {".txt", ".md", ".markdown"}
    if suffix in image_exts or declared_mime.startswith("image/"):
        if declared_mime != "image/jpeg" or len(raw) > MAX_IMAGE_BYTES or not raw.startswith(b"\xff\xd8"):
            raise ValueError("画像はJPG・300KB以下に変換してアップロードしてください")
        suffix = ".jpg"; safe_original = Path(safe_original).stem + ".jpg"
        is_image = True
    elif suffix == ".pdf":
        if declared_mime not in {"application/pdf", "application/octet-stream"} or not raw.startswith(b"%PDF"):
            raise ValueError("PDF形式を確認してください")
        is_image = False
    elif suffix in text_exts:
        if not (declared_mime.startswith("text/") or declared_mime == "application/octet-stream"):
            raise ValueError("テキスト形式を確認してください")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("txt / md はUTF-8で保存してください")
        is_image = False
    else:
        raise ValueError("アップロードできるのは画像・PDF・txt・mdです")
    folder = MEDIA_DIR / f"u{uid}"; folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"{stamp}_{Path(safe_original).stem[:60]}{suffix}"
    (folder / filename).write_bytes(raw)
    url = f"/media/u{uid}/{filename}"
    label = re.sub(r"[\]\[\r\n]", "", Path(safe_original).name)[:100] or "file"
    markdown = f"![{label}]({url})" if is_image else f"[{label}]({url})"
    return {"url": url, "markdown": markdown, "name": label, "size": len(raw)}


def issue_local_sync_token(user_id: int) -> str:
    token = "nn_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with db_conn() as con:
        con.execute("""INSERT INTO local_sync_tokens(user_id,token_hash,created_at) VALUES(?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET token_hash=excluded.token_hash,created_at=CURRENT_TIMESTAMP""",
                    (int(user_id), digest))
    return token


def validate_local_sync_token_token(token: str) -> dict | None:
    digest = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    with db_conn() as con:
        row = con.execute("""SELECT u.* FROM users u JOIN local_sync_tokens t ON t.user_id=u.id
                             WHERE t.token_hash=? AND u.status='active'""", (digest,)).fetchone()
    return dict(row) if row else None


def validate_local_sync_token(username: str, token: str) -> dict | None:
    row = validate_local_sync_token_token(token)
    if not row: return None
    if username and str(row.get("username", "")).casefold() != str(username).strip().casefold(): return None
    return row


def local_config() -> dict:
    with _LOCAL_CONFIG_LOCK:
        if not LOCAL_CONFIG_FILE.exists():
            data = {}
        else:
            try: data = json.loads(LOCAL_CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception: data = {}
    hashes=data.get("sync_hashes") if isinstance(data.get("sync_hashes"),dict) else {}
    file_map=data.get("sync_file_map") if isinstance(data.get("sync_file_map"),dict) else {}
    return {"server_url": str(data.get("server_url") or PUBLIC_SERVER_DEFAULT).rstrip("/"),
            "token": str(data.get("token") or ""), "auto_upload": bool(data.get("auto_upload", False)),
            "remote_username": str(data.get("remote_username") or data.get("username") or ""),
            "remote_user_id": int(data.get("remote_user_id") or 0), "workspace_user_id": int(data.get("workspace_user_id") or 0),
            "last_pull_at": str(data.get("last_pull_at") or ""), "last_push_at": str(data.get("last_push_at") or ""),
            "sync_hashes": {str(k):str(v) for k,v in hashes.items() if isinstance(k,str) and isinstance(v,str)},
            "sync_file_map": {str(k):str(v) for k,v in file_map.items() if isinstance(k,str) and isinstance(v,str)}}

def write_local_config(cfg: dict) -> None:
    with _LOCAL_CONFIG_LOCK:
        atomic_text_write(LOCAL_CONFIG_FILE, json.dumps(cfg,ensure_ascii=False,indent=2))

def sync_content_hash(content: str) -> str:
    # Web publishing intentionally sends the parent/source side only. The child
    # side is reconstructed from backlinks and can differ locally because of
    # private/local-only notes. Do not treat those derived differences as a
    # Web/Local content conflict.
    publicish = strip_local_only_metadata(str(content or ""))
    parent, _child = split_direction_content(publicish)
    canonical = parent.replace("\r\n", "\n").strip() + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def remote_sync_identity(server_url: str, token: str) -> dict:
    payload = json.dumps({"token": str(token or "")}).encode("utf-8")
    req = urllib.request.Request(str(server_url).rstrip("/") + "/api/local-whoami", data=payload,
                                 headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try: detail=json.loads(e.read().decode("utf-8")).get("error",str(e))
        except Exception: detail=str(e)
        raise ValueError("同期キーで接続できません: "+detail)
    except Exception as e: raise ValueError("同期キーで接続できません: "+str(e))


def remote_account_login(server_url: str, username: str, password: str) -> dict:
    server = str(server_url or PUBLIC_SERVER_DEFAULT).strip().rstrip("/")
    if not server.startswith(("https://", "http://")):
        raise ValueError("サーバーURLを確認してください")
    parsed = urllib.parse.urlparse(server)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" and host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Webアカウントのパスワードを送るため、HTTPSのサーバーを指定してください")
    username = str(username or "").strip()
    password = str(password or "")
    if not username or not password:
        raise ValueError("Webのユーザー名とパスワードを入力してください")
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(server + "/api/local-login", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            result = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try: detail = json.loads(e.read().decode("utf-8")).get("error", str(e))
        except Exception: detail = str(e)
        raise ValueError("Webアカウントでログインできません: " + detail)
    except Exception as e:
        raise ValueError("Webアカウントでログインできません: " + str(e))
    if not str(result.get("token") or "").startswith("nn_") or not result.get("username"):
        raise ValueError("Webサーバーから同期情報を受け取れませんでした")
    return result


def remote_account_register(server_url: str, username: str, password: str) -> dict:
    server = str(server_url or PUBLIC_SERVER_DEFAULT).strip().rstrip("/")
    if not server.startswith(("https://", "http://")):
        raise ValueError("サーバーURLを確認してください")
    parsed = urllib.parse.urlparse(server)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" and host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Webアカウントのパスワードを送るため、HTTPSのサーバーを指定してください")
    username = str(username or "").strip(); password = str(password or "")
    if not username or len(password) < 8:
        raise ValueError("Webユーザー名と8文字以上のパスワードを入力してください")
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(server + "/api/local-register", data=payload, headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r: result = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try: detail=json.loads(e.read().decode("utf-8")).get("error",str(e))
        except Exception: detail=str(e)
        raise ValueError("Webアカウントを作成できません: "+detail)
    except Exception as e: raise ValueError("Webアカウントを作成できません: "+str(e))
    if not str(result.get("token") or "").startswith("nn_") or not result.get("username"):
        raise ValueError("Webサーバーから同期情報を受け取れませんでした")
    return result


def save_local_config(data: dict) -> dict:
    if not LOCAL_MODE: raise PermissionError("ローカル版でのみ使用できます")
    server = str(data.get("server_url") or PUBLIC_SERVER_DEFAULT).strip().rstrip("/")
    token = str(data.get("token") or "").strip()
    if not server.startswith(("https://","http://")): raise ValueError("サーバーURLを確認してください")
    old=local_config(); remote_username=""; remote_user_id=0
    if token:
        ident=remote_sync_identity(server,token); remote_username=str(ident.get("username") or ""); remote_user_id=int(ident.get("user_id") or 0)
        if not remote_username or not remote_user_id: raise ValueError("同期キーのWebアカウントを確認できません")
    same_remote=bool(token and remote_user_id and int(old.get("remote_user_id") or 0)==remote_user_id and str(old.get("server_url") or "").rstrip("/")==server)
    cfg={"server_url":server,"token":token,"auto_upload":False,
         "remote_username":remote_username,"remote_user_id":remote_user_id,"workspace_user_id":int(old.get("workspace_user_id") or 0),
         "last_pull_at":str(old.get("last_pull_at") or "") if same_remote else "",
         "last_push_at":str(old.get("last_push_at") or "") if same_remote else "",
         "sync_hashes":dict(old.get("sync_hashes") or {}) if same_remote else {},
         "sync_file_map":dict(old.get("sync_file_map") or {}) if same_remote else {}}
    write_local_config(cfg)
    return cfg


def _public_version_aliases(user_id: int, contents: dict[str, str]) -> dict[str, str]:
    aliases = {}
    for note, content in contents.items():
        if not note_upload_enabled(content):
            continue
        for rel, _lab, target in parse_outgoing(content):
            if normalized_relation(rel) == normalized_relation("公開版") and target in contents:
                aliases[target] = note
    return aliases


def _replace_or_strip_md_links(text: str, allowed: set[str], aliases: dict[str, str], private_targets: set[str], titles: dict[str, str]) -> str:
    def repl(m):
        label = m.group(1); raw_target = m.group(2); fixed = m.group(3)
        target = Path(urllib.parse.unquote(raw_target)).name
        if target in private_targets:
            return re.sub(r"\\([\[\]\\])", r"\1", label)
        mapped = aliases.get(target, target)
        # A local note not in the exported set must not leak via filename or title.
        if target in titles and mapped not in allowed:
            return re.sub(r"\\([\[\]\\])", r"\1", label)
        suffix = f' "{LINK_LABEL_FIXED}"' if fixed == LINK_LABEL_FIXED else ""
        return f"[{label}]({mapped}{suffix})"
    return MARKDOWN_LINK_RE.sub(repl, text)


def _selected_media_links_to_plain_text(text: str, allowed_attachments: set[str] | None) -> str:
    if allowed_attachments is None:
        return text
    # If the user explicitly excludes an attachment from a one-off export, do
    # not leave a broken /media/ URL in the public copy.
    rx = re.compile(r'(!?)\[([^\]]*)\]\(/media/u\d+/([^\s)]+)\)')
    def repl(m):
        rel = urllib.parse.unquote(m.group(3))
        if rel in allowed_attachments:
            return m.group(0)
        return m.group(2)
    return rx.sub(repl, text)


def _publish_filename_map(user_id: int, target_username: str, files: list[str]) -> dict[str,str]:
    local_username=username_for_user_id(int(user_id)); out={}
    if not LOCAL_MODE:
        for f in files:
            base=Path(f).name
            out[f]=f"{target_username}__{base.split('__',1)[1]}" if "__" in base else base
        return out
    cfg=local_config(); sync_map=dict(cfg.get("sync_file_map") or {})  # remote -> local
    reverse={local:remote for remote,local in sync_map.items()}
    used=set(sync_map)
    changed=False
    for f in files:
        base=Path(f).name
        if base in reverse:
            out[f]=reverse[base]; continue
        if is_index_file(base):
            candidate=f"{target_username}__Index.md"
        elif "__" in base:
            candidate=f"{target_username}__{base.split('__',1)[1]}"
        else:
            candidate=base
        if candidate in used:
            stem=Path(candidate).stem
            short=hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]
            candidate=f"{stem}-local-{short}.md"
            n=2
            while candidate in used:
                candidate=f"{stem}-local-{short}-{n}.md"; n+=1
        sync_map[candidate]=base; reverse[base]=candidate; used.add(candidate); out[f]=candidate; changed=True
    if changed:
        cfg["sync_file_map"]=sync_map; write_local_config(cfg)
    return out

def _replace_note_targets_for_publish(text: str, filename_map: dict[str,str]) -> str:
    def repl(m):
        label, raw_target, fixed=m.group(1),m.group(2),m.group(3)
        target=Path(urllib.parse.unquote(raw_target)).name; mapped=filename_map.get(target,target)
        suffix=f' "{LINK_LABEL_FIXED}"' if fixed==LINK_LABEL_FIXED else ""
        return f"[{label}]({mapped}{suffix})"
    return MARKDOWN_LINK_RE.sub(repl,text)


def build_publish_bundle(user_id: int, selected_notes: set[str] | None = None,
                         selected_attachments: set[str] | None = None, target_username: str | None = None,
                         include_all: bool = False) -> bytes:
    uid=int(user_id); local_username=username_for_user_id(uid); publish_username=str(target_username or local_username).strip() or local_username
    files=user_files(uid); contents={f:read_file(f) for f in files}; titles={f:title_of(c,f) for f,c in contents.items()}
    aliases=_public_version_aliases(uid,contents); eligible=set(files) if include_all else {f for f,c in contents.items() if note_upload_enabled(c)}
    filename_map=_publish_filename_map(uid,publish_username,sorted(eligible))
    for source,public in list(aliases.items()):
        if not include_all and source in eligible and not note_upload_enabled(contents[source]): eligible.discard(source)
        if public not in eligible: aliases.pop(source,None)
    requested=set(eligible) if selected_notes is None else {safe_name(x) for x in selected_notes if x in eligible}
    rendered={}
    for name in sorted(requested):
        content=contents[name]; private_targets=note_private_targets(content); edges=list(parse_outgoing(content))
        original=next((src for src,pub in aliases.items() if pub==name),None)
        if original:
            private_targets |= note_private_targets(contents[original]); edges=list(parse_outgoing(contents[original]))+edges
        out_edges=[]; seen=set()
        for rel,label,target in edges:
            if normalized_relation(rel)==normalized_relation("公開版") or target in private_targets: continue
            mapped_local=aliases.get(target,target)
            if target in contents and mapped_local not in eligible: continue
            mapped_target=filename_map.get(mapped_local,mapped_local)
            key=(normalized_relation(rel),mapped_target)
            if key in seen: continue
            seen.add(key); out_edges.append((rel,titles.get(mapped_local,label),mapped_target))
        parent,_child=split_direction_content(content); clean_parent=_strip_relation_edge_sections(parent); clean_parent=strip_local_only_metadata(clean_parent)
        fm,body=split_yaml_frontmatter(clean_parent)
        body=_replace_or_strip_md_links(body,eligible,aliases,private_targets,titles)
        body=_replace_note_targets_for_publish(body,filename_map)
        body=_selected_media_links_to_plain_text(body,selected_attachments)
        # Web identity is authoritative even when Local was created under a different handle.
        created=yaml_created_value(clean_parent) or inferred_created_iso(name)
        other=[]
        for line in (fm.splitlines()[1:-1] if fm else []):
            if CREATOR_METADATA_RE.match(line) or re.match(r"^\s*created\s*:",line,re.I): continue
            other.append(line)
        public_fm="\n".join(["---",f"creator::{publish_username}",f"created: {created}",*other,"---"])
        base=public_fm.rstrip()+"\n\n"+body.lstrip("\n")
        public_text=_compose_segment_with_edges(base,out_edges).rstrip()+"\n---\n"
        rendered[filename_map.get(name,name)]=public_text
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
        manifest={"format":"networknotes-publish","version":3,"username":publish_username,"local_username":local_username,
                  "published_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"files":sorted(rendered)}
        z.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
        for name,text in rendered.items(): z.writestr("notes/"+name,text)
        folder=MEDIA_DIR/f"u{uid}"; referenced_media=set(); media_rx=re.compile(r"/media/u\d+/([^\s)\]]+)")
        for text in rendered.values():
            for m in media_rx.finditer(text):
                rel=Path(urllib.parse.unquote(m.group(1)))
                if not rel.is_absolute() and ".." not in rel.parts: referenced_media.add(rel.as_posix())
        if include_all and folder.exists():
            referenced_media |= {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
        if selected_attachments is not None: referenced_media &= {Path(x).as_posix() for x in selected_attachments if ".." not in Path(x).parts}
        if folder.exists():
            for rel_s in sorted(referenced_media):
                p=folder/Path(rel_s)
                if p.is_file(): z.write(p,"attachments/"+rel_s)
    return out.getvalue()


def local_export_candidates(user_id: int) -> dict:
    uid=int(user_id)
    files=user_files(uid); contents={f:read_file(f) for f in files}
    eligible=[f for f in files if note_upload_enabled(contents[f])]
    notes=[{"file":f,"title":title_of(contents[f],f),"bytes":len(contents[f].encode("utf-8"))} for f in eligible]
    cfg=local_config(); raw=build_publish_bundle(uid,target_username=cfg.get("remote_username") or username_for_user_id(uid))
    attachments=[]
    with zipfile.ZipFile(io.BytesIO(raw),"r") as z:
        for entry in z.infolist():
            if entry.filename.startswith("attachments/") and not entry.is_dir():
                rel=Path(entry.filename).relative_to("attachments").as_posix()
                attachments.append({"path":rel,"bytes":int(entry.file_size)})
    return {"notes":notes,"attachments":attachments}


def apply_publish_bundle(user_id: int, raw: bytes, replace: bool = True) -> dict:
    uid = int(user_id); username = username_for_user_id(uid)
    if len(raw) > 200 * 1024 * 1024:
        raise ValueError("公開データが大きすぎます")
    try: z = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile: raise ValueError("公開データZIPが壊れています")
    with z:
        try: manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        except Exception: raise ValueError("公開データのmanifestがありません")
        if manifest.get("format") != "networknotes-publish" or str(manifest.get("username", "")).casefold() != username.casefold():
            raise PermissionError("このアカウント用の公開データではありません")
        entries = [n for n in z.namelist() if n.startswith("notes/") and n.endswith(".md") and ".." not in Path(n).parts]
        limits = quota_limits(uid)
        if len(entries) > limits["notes_limit"]:
            raise ValueError("公開ノート数が上限を超えています")
        if sum(int(z.getinfo(n).file_size) for n in entries) > limits["note_bytes_limit"]:
            raise ValueError("公開ノート容量が上限を超えています")
        incoming = {}
        for entry in entries:
            if int(z.getinfo(entry).file_size) > MAX_NOTE_BYTES:
                raise ValueError("1ノートの上限は100KBです")
            name = safe_name(Path(entry).name)
            if file_owner_id(name) != uid:
                raise PermissionError("他ユーザー名のノートは公開できません")
            content = z.read(entry).decode("utf-8")
            content = re.sub(r"/media/u\d+/", f"/media/u{uid}/", content)
            enforce_note_write_quota(uid, name, content)
            incoming[name] = content
        with db_conn() as con:
            previous = {str(r[0]) for r in con.execute("SELECT note_file FROM local_published_notes WHERE user_id=?", (uid,)).fetchall()}
        if replace:
            # A manual Local -> Network transfer is a snapshot replacement, not
            # a merge with notes that happen not to have been published before.
            previous |= set(user_files(uid))
        current = set(incoming)
        remove = (previous - current) if replace else set()
        if remove:
            for md in list(VAULT.glob("*.md")):
                if md.name in remove: continue
                text = md.read_text(encoding="utf-8"); changed = remove_links_to_targets(text, remove)
                if changed != text: atomic_text_write(md, changed)
            for name in remove:
                try: (VAULT / name).unlink()
                except FileNotFoundError: pass
        for name, content in incoming.items():
            write_file(name, content)
        folder = MEDIA_DIR / f"u{uid}"; folder.mkdir(parents=True, exist_ok=True)
        attachment_entries = [entry for entry in z.namelist()
                              if entry.startswith("attachments/") and not entry.endswith("/") and ".." not in Path(entry).parts]
        if any(int(z.getinfo(entry).file_size) > MAX_ATTACHMENT_BYTES for entry in attachment_entries):
            raise ValueError("1ファイルの上限は10MBです")
        if sum(int(z.getinfo(entry).file_size) for entry in attachment_entries) > quota_limits(uid)["media_bytes_limit"]:
            raise ValueError("添付容量上限を超えています")
        incoming_attachments = {Path(entry).relative_to("attachments").as_posix() for entry in attachment_entries}
        with db_conn() as con:
            previous_attachments = {str(r[0]) for r in con.execute(
                "SELECT rel_path FROM local_published_attachments WHERE user_id=?", (uid,)
            ).fetchall()}
        if replace:
            for dest in sorted(folder.rglob("*"), reverse=True) if folder.exists() else []:
                if dest.is_file() and dest.relative_to(folder).as_posix() not in incoming_attachments:
                    dest.unlink()
        for entry in attachment_entries:
            data = z.read(entry)
            if len(data) > MAX_ATTACHMENT_BYTES:
                raise ValueError("1ファイルの上限は10MBです")
            rel = Path(entry).relative_to("attachments"); dest = folder / rel
            old_size = dest.stat().st_size if dest.exists() else 0
            if quota_usage(uid)["media_bytes"] - old_size + len(data) > quota_usage(uid)["media_bytes_limit"]:
                raise ValueError("添付容量上限を超えています")
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
        with db_conn() as con:
            note_state = current if replace else (previous | current)
            attachment_state = incoming_attachments if replace else (previous_attachments | incoming_attachments)
            con.execute("DELETE FROM local_published_notes WHERE user_id=?", (uid,))
            con.executemany("INSERT INTO local_published_notes(user_id,note_file) VALUES(?,?)", [(uid, n) for n in sorted(note_state)])
            con.execute("DELETE FROM local_published_attachments WHERE user_id=?", (uid,))
            con.executemany("INSERT INTO local_published_attachments(user_id,rel_path) VALUES(?,?)",
                            [(uid, rel_s) for rel_s in sorted(attachment_state)])
    sync_edges()
    return {"published": len(incoming), "removed": len(remove), "attachments": len(incoming_attachments), "mode": "replace" if replace else "merge"}


_LOCAL_PUBLISH_TIMERS: dict[int, threading.Timer] = {}
_LOCAL_PUBLISH_LOCK = threading.Lock()


def update_local_sync_stamp(field: str, hash_updates: dict[str,str] | None = None) -> None:
    if not LOCAL_MODE or field not in {"last_pull_at","last_push_at"}: return
    with _LOCAL_CONFIG_LOCK:
        cfg=local_config(); cfg[field]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if hash_updates:
            hashes=dict(cfg.get("sync_hashes") or {}); hashes.update({str(k):str(v) for k,v in hash_updates.items()}); cfg["sync_hashes"]=hashes
        write_local_config(cfg)


def save_local_safety_backup(user_id: int, reason: str = "before-sync") -> str:
    if not LOCAL_MODE: return ""
    folder=DATA_DIR / "backups"; folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime("%Y%m%d-%H%M%S")
    path=folder / f"networknotes-local-{reason}-{stamp}.zip"
    path.write_bytes(backup_zip_bytes(int(user_id)))
    return str(path)


def publish_local_now(user_id: int) -> dict:
    if not LOCAL_MODE: raise PermissionError("ローカル版でのみ使用できます")
    cfg=local_config(); uid=int(user_id)
    if not cfg.get("token") or not cfg.get("remote_username"): raise ValueError("Webアカウントへログインしてください")
    bundle=build_publish_bundle(uid,target_username=cfg["remote_username"],include_all=True)
    payload=json.dumps({"token":cfg["token"],"mode":"replace","bundle_base64":base64.b64encode(bundle).decode("ascii")}).encode("utf-8")
    req=urllib.request.Request(cfg["server_url"].rstrip("/")+"/api/local-publish",data=payload,headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=30) as r: result=json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try: detail=json.loads(e.read().decode("utf-8")).get("error",str(e))
        except Exception: detail=str(e)
        raise ValueError("ネットへのアップロードに失敗しました: "+detail)
    except Exception as e: raise ValueError("ネットへのアップロードに失敗しました: "+str(e))
    hash_updates={f:sync_content_hash(read_file(f)) for f in user_files(uid)}
    update_local_sync_stamp("last_push_at",hash_updates)
    return result


def export_selected_local_now(user_id: int, notes: list[str], attachments: list[str]) -> dict:
    if not LOCAL_MODE:
        raise PermissionError("ローカル版でのみ使用できます")
    cfg = local_config(); uid = int(user_id)
    if not cfg.get("token") or not cfg.get("remote_username"):
        raise ValueError("Webアカウントでログインして同期してください")
    candidates = local_export_candidates(uid)
    allowed_notes = {n["file"] for n in candidates.get("notes", [])}
    allowed_attachments = {a["path"] for a in candidates.get("attachments", [])}
    selected_notes = {safe_name(x) for x in notes if str(x) in allowed_notes}
    selected_attachments = {Path(x).as_posix() for x in attachments if str(x) in allowed_attachments}
    if not selected_notes and not selected_attachments:
        raise ValueError("エクスポート対象が選択されていません")
    bundle = build_publish_bundle(uid, selected_notes=selected_notes, selected_attachments=selected_attachments, target_username=cfg["remote_username"])
    payload = json.dumps({
        "token": cfg["token"], "mode": "merge",
        "bundle_base64": base64.b64encode(bundle).decode("ascii"),
    }).encode("utf-8")
    req = urllib.request.Request(cfg["server_url"].rstrip("/") + "/api/local-publish", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result=json.loads(r.read().decode("utf-8"))
        hash_updates={f:sync_content_hash(read_file(f)) for f in selected_notes if (VAULT/f).exists()}
        update_local_sync_stamp("last_push_at",hash_updates)
        return result
    except urllib.error.HTTPError as e:
        try: detail = json.loads(e.read().decode("utf-8")).get("error", str(e))
        except Exception: detail = str(e)
        raise ValueError("Webエクスポートに失敗しました: " + detail)
    except Exception as e:
        raise ValueError("Webエクスポートに失敗しました: " + str(e))


def _backup_destination_mapping(user_id: int, raw: bytes) -> tuple[dict[str,str],dict[str,str]]:
    """Map remote filenames to Local filenames without ever clobbering an unrelated Local-only note."""
    uid=int(user_id); username=username_for_user_id(uid); cfg=local_config()
    sync_map=dict(cfg.get("sync_file_map") or {})  # remote -> local
    reverse={local:remote for remote,local in sync_map.items()}
    reserved=set(reverse)
    result={}
    with zipfile.ZipFile(io.BytesIO(raw),"r") as z:
        entries=[Path(e).name for e in z.namelist() if e.startswith("notes/") and e.endswith(".md") and ".." not in Path(e).parts]
    for remote in entries:
        if remote in sync_map:
            local=safe_name(sync_map[remote]); result[remote]=local; reserved.add(local); continue
        if is_index_file(remote):
            local=index_filename(uid)
        elif "__" in remote:
            suffix=remote.split("__",1)[1]; candidate=f"{username}__{suffix}"; local=candidate
            if candidate in reserved and reverse.get(candidate)!=remote:
                local=""
            elif (VAULT/candidate).exists() and reverse.get(candidate)!=remote:
                # v83/v84 migration: an upload-enabled note with the expected
                # suffix was already associated with Web even before a filename
                # map existed. Local-only notes stay protected and get no reuse.
                try: reusable=note_upload_enabled(read_file(candidate))
                except Exception: reusable=False
                if not reusable: local=""
            if not local:
                base=Path(suffix).stem; short=hashlib.sha256(remote.encode("utf-8")).hexdigest()[:8]
                local=f"{username}__{base}-web-{short}.md"; n=2
                while local in reserved or (VAULT/local).exists():
                    local=f"{username}__{base}-web-{short}-{n}.md"; n+=1
        else:
            local=user_node_filename(uid)
            while local in reserved: local=user_node_filename(uid)
        # One Local filename must belong to only one remote filename.
        prior=reverse.get(local)
        if prior and prior!=remote:
            stem=Path(local).stem; short=hashlib.sha256(remote.encode("utf-8")).hexdigest()[:8]
            local=f"{stem}-web-{short}.md"; n=2
            while local in reserved or (VAULT/local).exists():
                local=f"{stem}-web-{short}-{n}.md"; n+=1
        sync_map[remote]=local; reverse[local]=remote; reserved.add(local); result[remote]=local
    return result,sync_map


def _save_sync_conflict_copy(name: str, content: str, side: str = "web-incoming") -> str:
    folder=DATA_DIR/"backups"/"sync-conflicts"; folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_side=re.sub(r"[^A-Za-z0-9_-]+","-",str(side or "conflict"))[:40]
    path=folder/f"{stamp}-{Path(name).stem}-{safe_side}.md"
    atomic_text_write(path,content)
    return str(path)


def pull_web_backup_now(user_id: int) -> dict:
    if not LOCAL_MODE:
        raise PermissionError("ローカル版でのみ使用できます")
    cfg = local_config(); uid = int(user_id)
    if not cfg.get("token") or not cfg.get("remote_username"):
        raise ValueError("Webアカウントへログインしてください")
    payload = json.dumps({"token": cfg["token"]}).encode("utf-8")
    req = urllib.request.Request(cfg["server_url"].rstrip("/") + "/api/local-backup", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read().decode("utf-8"))
        raw = base64.b64decode(str(result.get("backup_base64", "")), validate=True)
    except urllib.error.HTTPError as e:
        try: detail = json.loads(e.read().decode("utf-8")).get("error", str(e))
        except Exception: detail = str(e)
        raise ValueError("ネットからのダウンロードに失敗しました: " + detail)
    except Exception as e:
        raise ValueError("ネットからのダウンロードに失敗しました: " + str(e))

    safety=save_local_safety_backup(uid,"before-web-pull")
    destination_map,new_sync_map=_backup_destination_mapping(uid,raw)
    destinations=list(destination_map.values())
    # The user explicitly selected Network -> Local. Replace the workspace
    # snapshot in full; do not perform change detection, merging, or conflicts.
    for name in user_files(uid):
        try: (VAULT/name).unlink()
        except FileNotFoundError: pass
    media_folder=MEDIA_DIR/f"u{uid}"
    if media_folder.exists(): shutil.rmtree(media_folder)
    restored=import_backup_zip(uid,raw,destination_mapping=destination_map)
    hash_updates={}
    for name in destinations:
        if not (VAULT/name).exists(): continue
        incoming=set_note_upload_enabled(read_file(name),True)
        write_file(name,incoming)
        hash_updates[name]=sync_content_hash(read_file(name))
    ensure_created_frontmatter_all_notes();ensure_creator_metadata_all_notes();sync_edges()
    latest=local_config(); latest["sync_file_map"]=new_sync_map; write_local_config(latest)
    restored["downloaded_bytes"]=len(raw);restored["safety_backup"]=safety
    restored["mode"]="network-replaces-local"
    update_local_sync_stamp("last_pull_at",hash_updates)
    return restored


def schedule_local_publish(user_id: int, delay: float = 1.2) -> None:
    # Network transfer is always an explicit user action.
    return


def bootstrap_local_from_sync_key(server_url: str, token: str) -> tuple[dict,str,str]:
    if not LOCAL_MODE: raise PermissionError("ローカル版でのみ使用できます")
    server=str(server_url or PUBLIC_SERVER_DEFAULT).strip().rstrip("/")
    if not server.startswith(("https://","http://")): raise ValueError("サーバーURLを確認してください")
    ident=remote_sync_identity(server,str(token or "").strip()); remote_username=str(ident.get("username") or "").strip()
    if not remote_username: raise ValueError("同期キーのWebアカウントを確認できません")
    workspace=local_workspace_user(); uid=int(workspace["id"])
    old_cfg=local_config(); remote_user_id=int(ident.get("user_id") or 0)
    same_remote=bool(remote_user_id and int(old_cfg.get("remote_user_id") or 0)==remote_user_id and str(old_cfg.get("server_url") or "").rstrip("/")==server)
    cfg={"server_url":server,"token":str(token).strip(),"auto_upload":False,
         "remote_username":remote_username,"remote_user_id":remote_user_id,"workspace_user_id":uid,
         "last_pull_at":str(old_cfg.get("last_pull_at") or "") if same_remote else "",
         "last_push_at":str(old_cfg.get("last_push_at") or "") if same_remote else "",
         "sync_hashes":dict(old_cfg.get("sync_hashes") or {}) if same_remote else {},
         "sync_file_map":dict(old_cfg.get("sync_file_map") or {}) if same_remote else {}}
    write_local_config(cfg)
    ensure_user_index(uid); session=make_session(uid); return profile_for_user({"id":uid}),session,remote_username


def bootstrap_local_from_web_account(server_url: str, username: str, password: str) -> tuple[dict,str,str]:
    if not LOCAL_MODE:
        raise PermissionError("ローカル版でのみ使用できます")
    login = remote_account_login(server_url, username, password)
    return bootstrap_local_from_sync_key(server_url, str(login.get("token") or ""))


def bootstrap_local_from_web_registration(server_url: str, username: str, password: str) -> tuple[dict,str,str]:
    if not LOCAL_MODE: raise PermissionError("ローカル版でのみ使用できます")
    created=remote_account_register(server_url,username,password)
    return bootstrap_local_from_sync_key(server_url,str(created.get("token") or ""))


def moderation_dashboard(viewer_user_id: int) -> dict:
    if not is_moderator_user(int(viewer_user_id)):
        raise PermissionError("管理権限が必要です")
    with db_conn() as con:
        users = [dict(r) for r in con.execute(
            "SELECT id,username,display_name,role,status,suspended_reason,created_at FROM users ORDER BY id"
        ).fetchall()]
        reports = [dict(r) for r in con.execute(
            """SELECT r.*,ru.username reporter_username,tu.username target_username
               FROM reports r JOIN users ru ON ru.id=r.reporter_user_id
               LEFT JOIN users tu ON tu.id=r.target_user_id
               WHERE r.status='open' ORDER BY r.created_at DESC LIMIT 300"""
        ).fetchall()]
        logs = [dict(r) for r in con.execute("SELECT * FROM moderation_log ORDER BY id DESC LIMIT 200").fetchall()]
    with db_conn() as con:
        override_ids={int(r[0]) for r in con.execute("SELECT user_id FROM user_quotas").fetchall()}
    for u in users:
        u["quota"] = quota_usage(int(u["id"]));u["quota_override"]=int(u["id"]) in override_ids
        u["report_count"] = report_count_for_user(int(u["id"]))
    return {"users": users, "reports": reports, "logs": logs, "hide_threshold": REPORT_HIDE_THRESHOLD, "global_quota":global_quota_limits()}



def password_hash(password: str) -> str:
    if len(password) < 8:
        raise ValueError("パスワードは8文字以上にしてください")
    salt = secrets.token_bytes(16)
    iterations = 180000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def password_ok(password: str, encoded: str) -> bool:
    try:
        scheme, it, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(it))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


def make_session(user_id: int) -> str:
    token = secrets.token_urlsafe(36)
    expires = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    with db_conn() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
        con.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)", (session_token_hash(token), int(user_id), expires))
    return token


def user_for_session(token: str | None) -> dict | None:
    if not token:
        return None
    with db_conn() as con:
        row = con.execute(
            """SELECT u.id,u.username,u.display_name,u.bio,u.avatar_url,u.role,u.status,u.suspended_reason,u.created_at
               FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.expires_at >= datetime('now')""",
            (session_token_hash(token),),
        ).fetchone()
    return dict(row) if row else None


def migrate_legacy_vault(user_id: int) -> None:
    """Move pre-SNS single-user Markdown into the first registered user's namespace."""
    ensure_vault()
    legacy = [p for p in VAULT.glob("*.md") if file_owner_id(p.name) is None]
    if not legacy:
        ensure_user_index(user_id)
        return
    # Only auto-migrate for the first account, otherwise leave legacy material untouched.
    with db_conn() as con:
        count = int(con.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    if count != 1:
        ensure_user_index(user_id)
        return
    mapping = {}
    username = username_for_user_id(user_id)
    for p in legacy:
        if p.name == INDEX_FILE:
            new = index_filename(user_id)
        else:
            new = f"{username}__{p.name}"
        mapping[p.name] = new
    for old, new in mapping.items():
        text = (VAULT / old).read_text(encoding="utf-8")
        for src, dst in mapping.items():
            text = text.replace(f"]({src})", f"]({dst})")
        atomic_text_write(VAULT / new, text)
    for old in mapping:
        try:
            (VAULT / old).unlink()
        except FileNotFoundError:
            pass
    ensure_user_index(user_id)


def migrate_numeric_user_filenames() -> None:
    """Migrate old public note names such as u1__... to username__....

    Usernames are immutable from this version onward, so they are stable public
    identifiers. The migration is idempotent and updates Markdown links and DB
    references without touching media files.
    """
    ensure_vault()
    with db_conn() as con:
        users = [dict(r) for r in con.execute("SELECT id,username FROM users ORDER BY id").fetchall()]
    mapping: dict[str, str] = {}
    for user in users:
        uid = int(user["id"])
        username = str(user["username"])
        old_prefix = f"u{uid}__"
        new_prefix = f"{username}__"
        for p in list(VAULT.glob(f"{old_prefix}*.md")):
            new_name = new_prefix + p.name[len(old_prefix):]
            dest = VAULT / new_name
            if dest.exists():
                # Never overwrite user content. Keep the legacy file if there
                # is an unexpected collision; it remains readable via fallback.
                continue
            mapping[p.name] = new_name

    if not mapping:
        return

    # Rename first; then rewrite every Markdown link globally, including links
    # from other users to the migrated notes.
    for old, new in mapping.items():
        (VAULT / old).rename(VAULT / new)

    for md in VAULT.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        changed = text
        for old, new in mapping.items():
            changed = changed.replace(f"]({old})", f"]({new})")
            changed = changed.replace(f"]({urllib.parse.quote(old)})", f"]({urllib.parse.quote(new)})")
        if changed != text:
            atomic_text_write(md, changed)

    # References stored outside Markdown must follow the renamed note files.
    with db_conn() as con:
        for old, new in mapping.items():
            con.execute(
                "INSERT OR IGNORE INTO likes(user_id,note_file,created_at) SELECT user_id,?,created_at FROM likes WHERE note_file=?",
                (new, old),
            )
            con.execute("DELETE FROM likes WHERE note_file=?", (old,))
            con.execute(
                "INSERT OR IGNORE INTO community_posts(community_id,note_file,user_id,created_at) SELECT community_id,?,user_id,created_at FROM community_posts WHERE note_file=?",
                (new, old),
            )
            con.execute("DELETE FROM community_posts WHERE note_file=?", (old,))

    ratings = load_topic_ratings()
    if isinstance(ratings, dict):
        changed_ratings = False
        for old, new in list(mapping.items()):
            if old in ratings and new not in ratings:
                ratings[new] = ratings.pop(old)
                changed_ratings = True
        for source, targets in list(ratings.items()):
            if isinstance(targets, dict):
                for old, new in list(mapping.items()):
                    if old in targets and new not in targets:
                        targets[new] = targets.pop(old)
                        changed_ratings = True
        if changed_ratings:
            save_topic_ratings(ratings)


def decode_data_url(data_url: str, max_bytes: int = 8 * 1024 * 1024) -> tuple[bytes, str]:
    m = re.match(r"^data:([\w.+-]+/[\w.+-]+);base64,(.+)$", data_url or "", re.DOTALL)
    if not m:
        raise ValueError("invalid image data")
    mime = m.group(1).lower()
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}
    if mime not in allowed:
        raise ValueError("JPEG / PNG / GIF / WebP のみ対応しています")
    raw = base64.b64decode(m.group(2), validate=True)
    if len(raw) > max_bytes:
        raise ValueError("画像が大きすぎます")
    return raw, allowed[mime]


def decode_jpeg_data_url(data_url: str, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    m = re.match(r"^data:image/jpeg;base64,(.+)$", str(data_url or ""), re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("画像はJPGへ変換してアップロードしてください")
    try:
        raw = base64.b64decode(m.group(1), validate=True)
    except Exception:
        raise ValueError("画像を読み込めません")
    if len(raw) > int(max_bytes):
        raise ValueError("画像は300KB以下にしてください")
    if not raw.startswith(b"\xff\xd8"):
        raise ValueError("JPG形式を確認してください")
    return raw


def save_avatar(user_id: int, data_url: str) -> dict:
    raw = decode_jpeg_data_url(data_url)
    ext = ".jpg"
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    # Remove previous avatar variants for this user.
    for p in AVATAR_DIR.glob(f"u{user_id}.*"):
        try:
            p.unlink()
        except OSError:
            pass
    filename = f"u{user_id}{ext}"
    (AVATAR_DIR / filename).write_bytes(raw)
    url = f"/media/avatars/{filename}"
    with db_conn() as con:
        con.execute("UPDATE users SET avatar_url=? WHERE id=?", (url, int(user_id)))
    return profile_for_user({"id": int(user_id)})


def save_inline_image(user_id: int, data_url: str, original_name: str = "image") -> dict:
    raw = decode_jpeg_data_url(data_url)
    ext = ".jpg"
    if not LOCAL_MODE and quota_usage(int(user_id))["media_bytes"] + len(raw) > quota_usage(int(user_id))["media_bytes_limit"]:
        raise ValueError("添付ファイル容量の上限に達しています")
    folder = MEDIA_DIR / f"u{user_id}"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"{stamp}{ext}"
    (folder / filename).write_bytes(raw)
    safe_label = re.sub(r"[\]\[\r\n]", "", Path(original_name).stem)[:100] or "image"
    return {"url": f"/media/u{user_id}/{filename}", "markdown": f"![{safe_label}](/media/u{user_id}/{filename})"}


def user_files(user_id: int) -> list[str]:
    ensure_user_index(user_id)
    prefix = f"{username_for_user_id(user_id)}__"
    legacy_prefix = f"u{int(user_id)}__"
    names = {p.name for p in VAULT.glob(f"{prefix}*.md")}
    # Safety fallback for a rare migration collision; legacy files remain usable.
    names.update(p.name for p in VAULT.glob(f"{legacy_prefix}*.md"))
    return sorted(names, key=lambda n: (not is_index_file(n), n.lower()))


def author_map_for_files(files: list[str]) -> dict:
    ids = sorted({x for x in (file_owner_id(f) for f in files) if x})
    users = {uid: public_user(uid) for uid in ids}
    return {f: users.get(file_owner_id(f), public_user(None)) for f in files}


def sns_file_payload(name: str, viewer_user_id: int, voter: str | None = None):
    if not can_view_note(int(viewer_user_id), name):
        raise PermissionError("このノートは非表示です")
    payload = file_payload(name, voter)
    owner_id = file_owner_id(name)
    payload["author"] = public_user(owner_id)
    cid=community_index_id(name)
    payload["can_edit"] = can_manage_community(int(viewer_user_id),cid) if cid is not None else owner_id == int(viewer_user_id)
    payload["is_index"] = is_index_file(name)
    payload["community_id"] = cid or 0
    payload["is_community_index"] = cid is not None
    if not LOCAL_MODE:
        for row in external_edge_rows(source=name):
            if can_view_user(int(viewer_user_id), int(row["creator_user_id"])) and can_view_note(int(viewer_user_id), row["target_file"]):
                payload["outgoing"].append({"relation":row["relation"],"title":title_of(read_file(row["target_file"]),row["target_file"]),"file":row["target_file"],"edge_kind":"external","edge_id":int(row["id"]),"owner_set":False,"edge_creator_id":int(row["creator_user_id"]),"edge_creator_username":row["creator_username"]})
        for row in external_edge_rows(target=name):
            if can_view_user(int(viewer_user_id), int(row["creator_user_id"])) and can_view_note(int(viewer_user_id), row["source_file"]):
                payload["incoming"].append({"relation":row["relation"],"title":title_of(read_file(row["source_file"]),row["source_file"]),"file":row["source_file"],"edge_kind":"external","edge_id":int(row["id"]),"owner_set":False,"edge_creator_id":int(row["creator_user_id"]),"edge_creator_username":row["creator_username"]})
    payload["outgoing"] = [e for e in payload.get("outgoing", []) if can_view_note(int(viewer_user_id), e.get("file", ""))]
    payload["incoming"] = [e for e in payload.get("incoming", []) if can_view_note(int(viewer_user_id), e.get("file", ""))]
    topic_norm = {normalized_relation(x) for x in {"カテゴリー","トピック","topic","topics","分類"}}
    payload["is_topic"] = any(normalized_relation(e.get("relation","")) in topic_norm for e in payload["incoming"])
    for e in payload["incoming"]:
        e["can_move"] = (e.get("edge_kind") == "external" and int(e.get("edge_creator_id") or 0)==int(viewer_user_id)) or (e.get("edge_kind") != "external" and file_owner_id(e.get("file", ""))==int(viewer_user_id))
    for e in payload["outgoing"]:
        e["can_move"] = (e.get("edge_kind") == "external" and int(e.get("edge_creator_id") or 0)==int(viewer_user_id)) or (e.get("edge_kind") != "external" and owner_id==int(viewer_user_id))
    own_private = note_private_targets(payload.get("content", ""))
    for e in payload["outgoing"]:
        e["private"] = e.get("file", "") in own_private
    for e in payload["incoming"]:
        try: e["private"] = name in note_private_targets(read_file(e.get("file", "")))
        except Exception: e["private"] = False
    visible_metric_files = [f for f in payload.get("metrics", {}) if can_view_note(int(viewer_user_id), f)]
    payload["metrics"] = {f: payload["metrics"][f] for f in visible_metric_files}
    payload["authors"] = author_map_for_files(visible_metric_files)
    payload["upload_enabled"] = note_upload_enabled(payload.get("content", ""))
    payload["private_targets"] = sorted(note_private_targets(payload.get("content", "")))
    payload["local_mode"] = bool(LOCAL_MODE)
    payload["report_count"] = report_count_for_note(name)
    with db_conn() as con:
        payload["like_count"] = int(con.execute("SELECT COUNT(*) FROM likes WHERE note_file=?", (name,)).fetchone()[0])
        payload["liked"] = bool(con.execute("SELECT 1 FROM likes WHERE note_file=? AND user_id=?", (name, int(viewer_user_id))).fetchone())
        payload["communities"] = [dict(r) for r in con.execute(
            """SELECT c.id,c.name FROM community_posts cp JOIN communities c ON c.id=cp.community_id
               WHERE cp.note_file=? ORDER BY c.name COLLATE NOCASE""", (name,)
        ).fetchall()]
    return payload


def guest_files_payload(viewer_user_id: int = 0, limit: int = 250):
    """Recent public nodes for the guest sidebar; never creates a user Index."""
    items = []
    for f in all_md_files():
        try:
            if is_index_file(f):
                continue
            if not can_view_note(int(viewer_user_id), f):
                continue
            content = read_file(f)
            created = note_created_iso(f)
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                ts = int(dt.timestamp())
                label = created.replace("T", " ")[:19]
            except Exception:
                ts = int((VAULT / f).stat().st_mtime)
                label = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            items.append({"name": f, "title": title_of(content, f), "time": ts, "time_label": label, "is_index": is_index_file(f)})
        except (OSError, ValueError):
            continue
    items.sort(key=lambda x: (int(x.get("time", 0)), str(x.get("title", "")).casefold()), reverse=True)
    return {"files": items[:max(1, min(int(limit), 500))], "index_file": None, "guest": True}


def sns_files_payload(user_id: int):
    files = user_files(user_id)
    contents = {f: read_file(f) for f in files}
    items = []
    for f in files:
        stem = Path(f).stem.split("__", 1)[-1]
        dt = None
        if re.fullmatch(r"\d{14}", stem):
            try:
                dt = datetime.strptime(stem, "%Y%m%d%H%M%S")
            except ValueError:
                dt = None
        if dt is None:
            try:
                dt = datetime.fromtimestamp((VAULT / f).stat().st_mtime)
            except OSError:
                dt = datetime.fromtimestamp(0)
        items.append({
            "name": f,
            "title": title_of(contents[f], f),
            "time": int(dt.timestamp()),
            "time_label": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "is_index": is_index_file(f),
        })
    return {"files": items, "index_file": index_filename(user_id)}


def note_created_iso(name: str) -> str:
    try:
        created = yaml_created_value(read_file(name))
        if created:
            return created
    except OSError:
        pass
    return inferred_created_iso(name)


def ordinary_note_files() -> list[str]:
    files = all_md_files()
    contents = {f: read_file(f) for f in files}
    topic_norm = {normalized_relation(x) for x in {"カテゴリー", "トピック", "topic", "topics", "分類"}}
    topic_nodes = {
        target for source in files for relation, _label, target in parse_outgoing(contents[source])
        if target in contents and normalized_relation(relation) in topic_norm
    }
    return [f for f in files if not is_index_file(f) and f not in topic_nodes and file_owner_id(f)]



def parse_search_scope(viewer_user_id: int, query: str) -> tuple[str,int,int,str,str]:
    try: tokens=shlex.split(str(query or ""))
    except ValueError: tokens=str(query or "").split()
    scope="mine" if int(viewer_user_id) else "all"; community_id=0; user_id=0; clean=[]; label="自分の投稿" if scope=="mine" else "全体"
    with db_conn() as con:
        for raw in tokens:
            low=raw.casefold()
            if low=="my": scope="mine"; community_id=user_id=0; label="自分の投稿"; continue
            if low=="all": scope="all"; community_id=user_id=0; label="全体"; continue
            if low.startswith("person="):
                value=raw.split("=",1)[1].strip().lstrip("@"); row=con.execute("SELECT id,username FROM users WHERE username=? COLLATE NOCASE OR display_name=? COLLATE NOCASE ORDER BY id LIMIT 1",(value,value)).fetchone()
                if row: scope="user"; user_id=int(row["id"]); community_id=0; label="@"+str(row["username"])
                else: scope="user"; user_id=-1; label="人物: "+value
                continue
            if low.startswith("community="):
                value=raw.split("=",1)[1].strip(); row=None
                if value.isdigit(): row=con.execute("SELECT id,name FROM communities WHERE id=?",(int(value),)).fetchone()
                if not row: row=con.execute("SELECT id,name FROM communities WHERE name=? COLLATE NOCASE ORDER BY id LIMIT 1",(value,)).fetchone()
                if row: scope="community"; community_id=int(row["id"]); user_id=0; label="コミュニティ: "+str(row["name"])
                else: scope="community"; community_id=-1; label="コミュニティ: "+value
                continue
            clean.append(raw)
    return scope,community_id,user_id," ".join(shlex.quote(x) if any(c.isspace() for c in x) else x for x in clean),label


def _search_token_groups(query: str):
    try:
        tokens = shlex.split(str(query or ""))
    except ValueError:
        tokens = str(query or "").split()
    groups = [[]]
    for raw in tokens:
        if raw.upper() == "OR":
            if groups[-1]:
                groups.append([])
            continue
        neg = raw.startswith("-") and len(raw) > 1
        token = raw[1:] if neg else raw
        field, value = "any", token
        if ":" in token:
            maybe, rest = token.split(":", 1)
            if maybe.casefold() in {"title","body","user","author","relation","to","from","community","file","regex"}:
                field, value = maybe.casefold(), rest
        if value:
            groups[-1].append((neg, field, value))
    return [g for g in groups if g] or [[]]


def _search_markdown_plain(content: str) -> str:
    text = strip_yaml_frontmatter(strip_edge_block(content))
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = MARKDOWN_LINK_RE.sub(lambda m: re.sub(r"\\([\[\]\\])", r"\1", m.group(1)), text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[`*_>~]", "", text)
    return text.strip()


def _search_snippet(text: str, needles: list[str], width: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    low = compact.casefold(); positions = [low.find(n.casefold()) for n in needles if n and low.find(n.casefold()) >= 0]
    pos = min(positions) if positions else 0
    start = max(0, pos - 70); end = min(len(compact), start + width)
    if end - start < width and start > 0: start = max(0, end - width)
    return ("…" if start else "") + compact[start:end] + ("…" if end < len(compact) else "")


def search_payload(viewer_user_id: int, query: str = "", scope: str = "auto", community_id: int = 0, limit: int = 100, user_id: int = 0) -> dict:
    context_label = ""
    if scope == "auto": scope, community_id, user_id, query, context_label = parse_search_scope(int(viewer_user_id), query)
    files = all_md_files(); contents = {f: read_file(f) for f in files}; titles = {f: title_of(contents[f], f) for f in files}
    incoming_map = {f: [] for f in files}
    outgoing_map = {f: parse_outgoing(contents[f]) for f in files}
    for source, edges in outgoing_map.items():
        for rel, _lab, target in edges:
            if target in incoming_map and target != source:
                incoming_map[target].append((rel, source))
    community_by_file = {f: [] for f in files}
    with db_conn() as con:
        for r in con.execute("SELECT cp.note_file,c.id,c.name FROM community_posts cp JOIN communities c ON c.id=cp.community_id").fetchall():
            if r["note_file"] in community_by_file:
                community_by_file[r["note_file"]].append({"id": int(r["id"]), "name": str(r["name"])})
    if scope == "mine":
        candidates = [f for f in files if file_owner_id(f) == int(viewer_user_id)]
    elif scope == "user":
        target_uid = int(user_id or 0); candidates = [f for f in files if file_owner_id(f) == target_uid]
    elif scope == "community":
        cid = int(community_id or 0); candidates = [f for f in files if any(c["id"] == cid for c in community_by_file.get(f, []))]
    else:
        candidates = list(files)
    candidates = [f for f in candidates if can_view_note(int(viewer_user_id), f)]
    groups = _search_token_groups(query)
    positive_needles = [v for g in groups for neg,field,v in g if not neg and field in {"any","title","body"} and field != "regex"]
    def one_match(f, clause):
        neg, field, value = clause; needle = value.casefold(); owner = public_user(file_owner_id(f)); clean = strip_edge_block(contents[f]); plain = _search_markdown_plain(clean)
        rels = outgoing_map[f]; incoming = incoming_map[f]; comms = community_by_file.get(f, [])
        hay = {
            "title": titles[f], "body": plain, "file": f,
            "user": " ".join([str(owner.get("username", "")), str(owner.get("display_name", ""))]),
            "author": " ".join([str(owner.get("username", "")), str(owner.get("display_name", ""))]),
            "relation": " ".join(rel for rel,_l,_t in rels),
            "to": " ".join(" ".join([target, titles.get(target, "")]) for _rel,_l,target in rels),
            "from": " ".join(" ".join([source, titles.get(source, "")]) for _rel,source in incoming),
            "community": " ".join(c["name"] for c in comms),
        }
        if field == "regex":
            try: ok = bool(re.search(value, "\n".join([titles[f], plain, hay["user"], hay["relation"]]), re.IGNORECASE))
            except re.error: ok = False
        elif field == "any":
            ok = needle in "\n".join([titles[f], plain, hay["user"], hay["relation"], hay["to"], hay["from"], hay["community"], f]).casefold()
        else:
            ok = needle in hay.get(field, "").casefold()
        return (not ok) if neg else ok
    results=[]
    for f in candidates:
        if is_index_file(f) and not query.strip():
            continue
        if groups and not any(all(one_match(f,c) for c in g) for g in groups):
            continue
        owner=public_user(file_owner_id(f)); plain=_search_markdown_plain(contents[f]); low_title=titles[f].casefold(); score=0
        for n in positive_needles:
            nn=n.casefold();
            if low_title == nn: score += 80
            elif nn in low_title: score += 35
            score += min(15, plain.casefold().count(nn)*3)
        if not query.strip(): score=0
        created=note_created_iso(f)
        results.append({"file":f,"title":titles[f],"author":owner,"snippet":_search_snippet(plain,positive_needles),"created_at":created,"communities":community_by_file.get(f,[]),"score":score,"match_terms":positive_needles[:12]})
    def result_time(item):
        try: return datetime_sort_key(item["created_at"])
        except (ValueError, TypeError): return 0.0
    results.sort(key=lambda x: (x["score"], result_time(x), x["title"].casefold()), reverse=True)
    lim=max(1,min(int(limit or 100),200));return {"count":len(results),"results":results[:lim],"scope":scope,"context_label":context_label or scope}


def resolve_note_reference(value: str) -> str:
    raw = urllib.parse.unquote(str(value or "").strip())
    m = MARKDOWN_LINK_RE.search(raw)
    if m:
        candidate = Path(urllib.parse.unquote(m.group(2))).name
        if (VAULT / candidate).exists(): return candidate
    # direct filename or filename embedded in a URL/text
    direct = Path(urllib.parse.urlparse(raw).path).name if raw else ""
    if direct.endswith(".md") and (VAULT / direct).exists(): return direct
    ms = re.findall(r"[A-Za-z0-9_.-]+__[^\s/)]+\.md|[^\s/)]+\.md", raw)
    for x in reversed(ms):
        candidate = Path(x).name
        if (VAULT / candidate).exists(): return candidate
    exact=[]
    for f in all_md_files():
        if title_of(read_file(f),f).casefold() == raw.casefold(): exact.append(f)
    if len(exact)==1:return exact[0]
    raise ValueError("貼り付けたリンクからノートを特定できません")

def feed_payload(viewer_user_id: int, mode: str = "latest", community_id: int | None = None, author_user_id: int | None = None) -> dict:
    files = [f for f in ordinary_note_files() if can_view_note(int(viewer_user_id), f)]
    if author_user_id is not None:
        files = [f for f in files if file_owner_id(f) == int(author_user_id)]
    shared_at = {}
    if community_id is not None:
        with db_conn() as con:
            rows = con.execute("SELECT note_file,created_at FROM community_posts WHERE community_id=?", (int(community_id),)).fetchall()
            allowed = {r["note_file"] for r in rows}; shared_at = {r["note_file"]: str(r["created_at"]) for r in rows}
        files = [f for f in files if f in allowed]
    contents = {f: read_file(f) for f in files}
    ratings = load_topic_ratings()
    all_contents = {f: read_file(f) for f in all_md_files()}
    metrics = build_metrics(all_contents, ratings)
    with db_conn() as con:
        like_counts = {r[0]: int(r[1]) for r in con.execute("SELECT note_file,COUNT(*) FROM likes GROUP BY note_file").fetchall()}
        liked = {r[0] for r in con.execute("SELECT note_file FROM likes WHERE user_id=?", (int(viewer_user_id),)).fetchall()}
    cards = []
    for f in files:
        author = public_user(file_owner_id(f))
        text = strip_yaml_frontmatter(strip_edge_block(contents[f]))
        # Brief excerpt without headings/standalone md links.
        excerpt_lines = []
        for line in text.splitlines():
            if HEADING_RE.match(line) or LINK_LINE_RE.match(line) or re.match(r"^\s*!\[[^\]]*\]\(/media/[^)]+\)\s*$", line) or not line.strip():
                continue
            excerpt_lines.append(line.strip())
            if len(" ".join(excerpt_lines)) > 260:
                break
        excerpt = " ".join(excerpt_lines)[:280]
        image_match = re.search(r"!\[[^\]]*\]\((/media/[^)]+)\)", text)
        image_url = image_match.group(1) if image_match else ""
        m = metrics.get(f, {})
        created_at = note_created_iso(f)
        interactions = like_counts.get(f, 0) * 4 + int(m.get("node_count", 0)) + int(m.get("support_count", 0)) * 2
        try:
            created_dt = parse_note_datetime(created_at)
            if created_dt.tzinfo is None:
                created_dt = created_dt.astimezone()
            age_hours = max(0.0, (datetime.now(timezone.utc) - created_dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
        except (ValueError, TypeError):
            age_hours = 0.0
        # "Popular now": interaction strength with a gentle time decay.
        score = (interactions + 1.0) / ((1.0 + age_hours / 24.0) ** 1.25)
        cards.append({
            "file": f,
            "title": title_of(contents[f], f),
            "excerpt": excerpt,
            "image_url": image_url,
            "author": author,
            "created_at": created_at,
            "like_count": like_counts.get(f, 0),
            "liked": f in liked,
            "node_count": int(m.get("node_count", 0)),
            "score": round(score, 6),
        })
    if mode == "popular":
        cards.sort(key=lambda x: (x["score"], datetime_sort_key(x["created_at"])), reverse=True)
    elif mode == "shared" and community_id is not None:
        cards.sort(key=lambda x: shared_at.get(x["file"], ""), reverse=True)
    else:
        cards.sort(key=lambda x: datetime_sort_key(x["created_at"]), reverse=True)
    return {"posts": cards[:100], "mode": mode}


def community_payload(row: sqlite3.Row | dict, viewer_user_id: int) -> dict:
    d = dict(row)
    cid = int(d["id"])
    with db_conn() as con:
        d["member_count"] = int(con.execute("SELECT COUNT(*) FROM community_members WHERE community_id=?", (cid,)).fetchone()[0])
        d["post_count"] = int(con.execute("SELECT COUNT(*) FROM community_posts WHERE community_id=?", (cid,)).fetchone()[0])
        d["joined"] = bool(con.execute("SELECT 1 FROM community_members WHERE community_id=? AND user_id=?", (cid, int(viewer_user_id))).fetchone())
    d["owner"] = public_user(int(d["owner_user_id"]))
    d["index_file"] = ensure_community_index(cid)
    try: d["index_markdown"] = split_yaml_frontmatter(read_file(d["index_file"]))[1]
    except Exception: d["index_markdown"] = str(d.get("index_markdown") or "# Index\n")
    d["can_edit_index"] = can_manage_community(int(viewer_user_id or 0),cid)
    d["can_manage"] = can_manage_community(int(viewer_user_id or 0),cid)
    d["can_manage_roles"] = can_manage_community_roles(int(viewer_user_id or 0),cid)
    return d


def local_distribution_filename(platform: str) -> str:
    if platform not in LOCAL_RELEASE_PLATFORMS:
        raise ValueError("配布プラットフォームが不正です")
    return f"NetworkNotes-Local-v{LOCAL_RELEASE_VERSION}-{platform}.zip"


def build_local_distribution(platform: str) -> bytes:
    """Build a data-free Local ZIP from the running application on demand."""
    local_distribution_filename(platform)  # validate before building
    root=f"NetworkNotes-Local-v{LOCAL_RELEASE_VERSION}/"
    readme=f"""NetworkNotes Local v{LOCAL_RELEASE_VERSION}

Folder layout:
  app/   application code
  data/  your local database, notes, media, connection settings and backups

Local use is fully available without an account or Internet connection.
Login or registration is requested only for an explicit Network transfer.
Network -> Local and Local -> Network both completely replace the destination.
No automatic upload, download, merge, or synchronization is performed.
Updating/replacing app/ does not replace data/.
"""
    shell='''#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/data"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$ROOT/app/app.py" --local
fi
echo "Python 3.10+ is required." >&2
exit 1
'''
    batch='''@echo off
cd /d "%~dp0"
if not exist data mkdir data
py -3 app\\app.py --local
if errorlevel 1 python app\\app.py --local
'''
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        def add(name: str, data: bytes | str, mode: int = 0o644):
            info=zipfile.ZipInfo(root+name,(2026,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(mode & 0xFFFF)<<16
            z.writestr(info,data.encode("utf-8") if isinstance(data,str) else data)
        add("README.txt",readme)
        add(".networknotes-local","NetworkNotes Local package\n")
        add("data/",b"",0o755)
        add("app/app.py",Path(__file__).read_bytes())
        for asset in sorted((APP_DIR/"static").iterdir()):
            if asset.is_file(): add("app/static/"+asset.name,asset.read_bytes())
        if platform in {"Linux","macOS","Portable"}: add("Start-NetworkNotes.sh",shell,0o755)
        if platform in {"Windows","Portable"}: add("Start-NetworkNotes.bat",batch)
    return out.getvalue()


def download_page_html() -> bytes:
    latest=LOCAL_RELEASE_VERSION
    order = {"Windows": 0, "macOS": 1, "Linux": 2, "Portable": 3}
    files = []
    for platform in sorted(LOCAL_RELEASE_PLATFORMS,key=lambda x:order[x]):
        raw=build_local_distribution(platform)
        files.append((platform,local_distribution_filename(platform),len(raw),hashlib.sha256(raw).hexdigest()))
    cards = "".join(
        f'<div class="card"><h3>{platform}</h3><p>{name}<br>{size/1024/1024:.1f} MB</p>'
        f'<a class="download" href="/downloads/{urllib.parse.quote(name)}">最新版をダウンロード</a>'
        f'<code>SHA256 {digest}</code></div>'
        for platform, name, size, digest in files
    ) or '<div class="card"><p>最新版の配布ファイルは準備中です。</p></div>'
    version_label = f"v{latest}" if latest is not None else ""
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NetworkNotes Local</title><style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:42px 24px;color:#111}}a{{color:#1670b8}}.top{{display:flex;justify-content:space-between;align-items:center}}.cards{{display:grid;gap:14px;margin-top:24px}}.card{{border:1px solid #ddd;border-radius:12px;padding:18px}}.download{{display:inline-block;border:1px solid #aaa;border-radius:8px;padding:9px 14px;text-decoration:none;margin:6px 0 12px}}code{{display:block;word-break:break-all;font-size:11px;color:#555}}li{{margin:.45em 0}}</style></head><body>
<div class="top"><h1>NetworkNotes Local {version_label}</h1><a href="/">Web版へ戻る</a></div>
<p>このページには現在の最新版だけを表示します。Localはアカウントもネット接続も不要で、そのまますべてのローカル機能を使えます。ログインまたは新規登録が必要なのは、明示的にネットとのデータ転送を選んだときだけです。</p>
<ul><li>Localアカウント不要・完全オフラインで編集可能</li><li>Markdown・添付ファイルをローカル保存</li><li>自動アップロード・自動ダウンロードなし</li><li>「ネットからダウンロード」で NETWORK → LOCAL を完全上書き</li><li>「ネットへアップロード」で LOCAL → NETWORK を完全上書き</li><li>チェックボックス・Markdownテーブル・Vim操作</li><li>画像はJPG・300KB以下へ自動変換</li><li>バックアップZIPの書き出し・復元</li></ul>
<div class="cards">{cards}</div></body></html>"""
    return html.encode("utf-8")


def local_workspace_user(preferred_session_user: dict | None = None) -> dict:
    """Implicit Local workspace identity used only for storage ownership; no login is required."""
    if not LOCAL_MODE:
        raise PermissionError("ローカル版でのみ使用できます")
    cfg=local_config(); chosen=None
    wid=int(cfg.get("workspace_user_id") or 0)
    if wid: chosen=user_from_id(wid)
    if chosen is None and preferred_session_user:
        chosen=user_from_id(int(preferred_session_user.get("id") or 0))
    if chosen is None and cfg.get("remote_username"):
        with db_conn() as con:
            row=con.execute("SELECT id FROM users WHERE username=? COLLATE NOCASE",(str(cfg.get("remote_username")),)).fetchone()
        if row: chosen=user_from_id(int(row["id"]))
    if chosen is None:
        with db_conn() as con: rows=[dict(r) for r in con.execute("SELECT id,username FROM users ORDER BY id").fetchall()]
        if len(rows)==1: chosen=user_from_id(int(rows[0]["id"]))
        elif rows:
            counts=[]
            for r in rows:
                uid=int(r["id"])
                try: count=len(user_files(uid))
                except Exception: count=0
                counts.append((count,-uid,uid))
            chosen=user_from_id(max(counts)[2])
    if chosen is None:
        username="local"
        with db_conn() as con:
            n=1
            while con.execute("SELECT 1 FROM users WHERE username=? COLLATE NOCASE",(username,)).fetchone():
                n+=1; username=f"local{n}"
            cur=con.execute("INSERT INTO users(username,password_hash,display_name) VALUES(?,?,?)",(username,password_hash(secrets.token_urlsafe(32)),"Local")); uid=int(cur.lastrowid)
        chosen=user_from_id(uid); migrate_legacy_vault(uid)
    ensure_user_index(int(chosen["id"]))
    cfg["workspace_user_id"]=int(chosen["id"])
    write_local_config(cfg)
    return chosen


class Handler(BaseHTTPRequestHandler):
    server_version = "NetworkNotesSNS/1.0-v86"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def json_response(self, obj, status=200, set_cookie: str | None = None):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(data)

    def text_response(self, data: bytes, content_type="text/html; charset=utf-8", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def file_response(self, data: bytes, filename: str, content_type="application/octet-stream", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", 'attachment; filename="' + filename.replace('"','') + '"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def client_ip(self) -> str:
        # nginx should set X-Real-IP to the immediate public client.  If only
        # X-Forwarded-For is available, use the right-most hop so a client-
        # supplied fake first entry cannot trivially bypass registration limits.
        real = (self.headers.get("X-Real-IP", "") or "").strip()
        if real:
            return real
        forwarded = [x.strip() for x in (self.headers.get("X-Forwarded-For", "") or "").split(",") if x.strip()]
        if forwarded:
            return forwarded[-1]
        return self.client_address[0] if self.client_address else "unknown"

    def cookie_token(self) -> str | None:
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            if "=" not in part:
                continue
            k, v = part.strip().split("=", 1)
            if k == SESSION_COOKIE:
                return urllib.parse.unquote(v)
        return None

    def current_user(self, required=True) -> dict | None:
        session_user = user_for_session(self.cookie_token())
        if session_user and str(session_user.get("status", "active")) != "active":
            session_user = None
        if LOCAL_MODE:
            return local_workspace_user(session_user)
        user = session_user
        if required and not user:
            raise AuthRequiredError("ログインが必要です")
        return user

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _forwarded_proto(self) -> str:
        for header in ("X-Forwarded-Proto", "X-Forwarded-Scheme", "X-Scheme"):
            value = (self.headers.get(header, "") or "").split(",", 1)[0].strip().lower()
            if value:
                return value
        forwarded = self.headers.get("Forwarded", "") or ""
        m = re.search(r"(?:^|[;,]\s*)proto=(?:\"([^\"]+)\"|([^;,\s]+))", forwarded, re.IGNORECASE)
        if m:
            return (m.group(1) or m.group(2) or "").strip().lower()
        return ""

    def _public_host(self) -> str:
        # Prefer the host supplied by the reverse proxy, but only use it for
        # comparing against our fixed public hostname. The redirect target is
        # hard-coded below, so Host header injection cannot alter Location.
        raw = (self.headers.get("X-Forwarded-Host", "") or self.headers.get("Host", "") or "")
        raw = raw.split(",", 1)[0].strip().lower()
        if raw.startswith("["):
            # IPv6 literal; not our public hostname.
            return raw
        return raw.split(":", 1)[0]

    def redirect_public_http_to_https(self) -> bool:
        if LOCAL_MODE:
            return False
        # Prefer the reverse proxy's original scheme. Some nginx configurations
        # proxy with Host=127.0.0.1, so do not require the backend Host header to
        # equal the public DuckDNS name when the proxy explicitly says HTTP.
        proto = self._forwarded_proto()
        host = self._public_host()
        if proto == "https":
            return False
        should_redirect = (host == "network-notes.duckdns.org") or (proto == "http")
        if not should_redirect:
            return False
        target = "https://network-notes.duckdns.org" + (self.path or "/")
        self.send_response(308)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return True

    def _cookie_secure_suffix(self) -> str:
        # nginx sets X-Forwarded-Proto. Keep direct LAN HTTP usable, but make
        # Internet/domain sessions Secure when the request arrived over HTTPS.
        return "; Secure" if self._forwarded_proto() == "https" else ""

    def auth_cookie(self, token: str) -> str:
        return f"{SESSION_COOKIE}={urllib.parse.quote(token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age={30*24*3600}{self._cookie_secure_suffix()}"

    def clear_auth_cookie(self) -> str:
        return f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{self._cookie_secure_suffix()}"

    def serve_media(self, url_path: str):
        rel = urllib.parse.unquote(url_path[len("/media/"):])
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            return self.text_response(b"Not found", "text/plain", 404)
        path = MEDIA_DIR / rel_path
        if not path.is_file():
            return self.text_response(b"Not found", "text/plain", 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return self.text_response(path.read_bytes(), ctype)

    def do_GET(self):
        if self.redirect_public_http_to_https():
            return
        try:
            u = urllib.parse.urlparse(self.path)
            if u.path == "/download":
                return self.text_response(download_page_html())
            if u.path.startswith("/downloads/"):
                name = Path(urllib.parse.unquote(u.path[len("/downloads/"):])).name
                for platform in LOCAL_RELEASE_PLATFORMS:
                    if name == local_distribution_filename(platform):
                        return self.file_response(build_local_distribution(platform),name,"application/zip")
                path = DOWNLOADS_DIR / name
                if not path.is_file():
                    return self.text_response(b"Not found", "text/plain", 404)
                return self.file_response(path.read_bytes(), path.name, mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            if u.path == "/":
                return self.text_response(HTML.encode("utf-8"))
            if u.path.startswith("/static/"):
                name = Path(u.path).name
                static_dir = APP_DIR / "static"
                allowed = {
                    "codemirror.js": "application/javascript; charset=utf-8",
                    "codemirror.css": "text/css; charset=utf-8",
                    "markdown.js": "application/javascript; charset=utf-8",
                    "xml.js": "application/javascript; charset=utf-8",
                    "meta.js": "application/javascript; charset=utf-8",
                    "continuelist.js": "application/javascript; charset=utf-8",
                    "active-line.js": "application/javascript; charset=utf-8",
                }
                if name not in allowed:
                    return self.text_response(b"Not found", "text/plain", 404)
                path = static_dir / name
                if not path.exists():
                    return self.text_response(b"Not found", "text/plain", 404)
                return self.text_response(path.read_bytes(), allowed[name])
            if u.path.startswith("/media/"):
                return self.serve_media(u.path)
            if u.path == "/api/session":
                user = self.current_user(required=False)
                return self.json_response({"authenticated": bool(user), "profile": profile_for_user(user) if user else None, "local_mode": bool(LOCAL_MODE)})

            user = self.current_user(required=False)
            uid = int(user["id"]) if user else 0
            if u.path == "/api/profile":
                if not user: raise AuthRequiredError("プロフィールを開くにはログインが必要です")
                return self.json_response(profile_for_user(user))
            if u.path == "/api/quota":
                if not user: raise AuthRequiredError("データ管理にはログインが必要です")
                return self.json_response(quota_usage(uid))
            if u.path == "/api/saved-searches":
                if not user: raise AuthRequiredError("検索条件の保存にはログインが必要です")
                with db_conn() as con: rows=[dict(r) for r in con.execute("SELECT id,name,query,created_at FROM saved_searches WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall()]
                return self.json_response({"searches":rows})
            if u.path == "/api/blocks":
                if not user: raise AuthRequiredError("ブロック管理にはログインが必要です")
                with db_conn() as con:
                    ids = [int(r[0]) for r in con.execute("SELECT blocked_user_id FROM blocks WHERE blocker_user_id=? ORDER BY created_at DESC", (uid,)).fetchall()]
                return self.json_response({"users": [public_user(x) for x in ids if user_from_id(x)]})
            if u.path == "/api/backup-export":
                if not user: raise AuthRequiredError("バックアップにはログインが必要です")
                data = backup_zip_bytes(uid)
                filename = f"networknotes-{user['username']}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
                return self.file_response(data, filename, "application/zip")
            if u.path == "/api/moderation":
                if not user: raise AuthRequiredError("管理画面にはログインが必要です")
                return self.json_response(moderation_dashboard(uid))
            if u.path == "/api/local-settings":
                if not user: raise AuthRequiredError("ローカル設定にはログインが必要です")
                if not LOCAL_MODE: raise PermissionError("ローカル版でのみ使用できます")
                cfg = local_config().copy(); cfg["token"] = cfg.get("token", "")
                return self.json_response(cfg)
            if u.path == "/api/files":
                return self.json_response(sns_files_payload(uid) if user else guest_files_payload(uid))
            if u.path == "/api/link-targets":
                targets = []
                for name in all_md_files():
                    try:
                        owner = file_owner_id(name)
                        if not can_view_note(uid, name):
                            continue
                        targets.append({"file": name, "title": title_of(read_file(name), name), "author": public_user(owner)})
                    except (OSError, ValueError):
                        continue
                targets.sort(key=lambda x: (str(x["title"]).casefold(), str(x["author"].get("username", "")).casefold(), x["file"]))
                return self.json_response({"targets": targets})
            if u.path == "/api/search":
                q = urllib.parse.parse_qs(u.query)
                query = q.get("q", [""])[0]
                scope = q.get("scope", ["auto"])[0]
                if scope not in {"auto","all","mine","community","user"}: scope = "auto"
                community_id = int(q.get("community_id", [0])[0] or 0)
                user_id = int(q.get("user_id", [0])[0] or 0)
                limit = int(q.get("limit", [100])[0] or 100)
                return self.json_response(search_payload(uid, query, scope, community_id, limit, user_id))
            if u.path == "/api/file":
                q = urllib.parse.parse_qs(u.query)
                raw_name = q.get("name", [None])[0]
                if not raw_name:
                    if not user: raise ValueError("ノートを指定してください")
                    raw_name = index_filename(uid)
                name = safe_name(raw_name)
                voter = f"user:{uid}" if user else None
                if not (VAULT / name).exists():
                    raise ValueError("ノートが見つかりません")
                return self.json_response(sns_file_payload(name, uid, voter))
            if u.path == "/api/graph":
                q = urllib.parse.parse_qs(u.query)
                raw_center = q.get("center", [None])[0]
                if not raw_center:
                    if not user: raise ValueError("中心ノートを指定してください")
                    raw_center = index_filename(uid)
                center = safe_name(raw_center)
                limit = int(q.get("limit", [18])[0])
                depth = int(q.get("depth", [2])[0])
                return self.json_response(graph_payload(center, limit, depth, uid))
            if u.path == "/api/feed":
                q = urllib.parse.parse_qs(u.query)
                mode = q.get("mode", ["latest"])[0]
                if mode not in {"latest", "popular", "shared"}: mode = "latest"
                cid = int(q.get("community_id", [0])[0] or 0)
                author_id = int(q.get("user_id", [0])[0] or 0)
                return self.json_response(feed_payload(uid, mode, cid if cid else None, author_id if author_id else None))
            if u.path == "/api/user":
                q = urllib.parse.parse_qs(u.query); other = int(q.get("id", [0])[0] or 0); pu = public_user(other)
                if not pu.get("id"): raise ValueError("ユーザーが見つかりません")
                if other != uid and not can_view_user(uid, other):
                    raise PermissionError("このユーザーは非表示です")
                with db_conn() as con:
                    following = bool(user and other != uid and con.execute("SELECT 1 FROM follows WHERE follower_user_id=? AND followed_user_id=?", (uid, other)).fetchone())
                    blocked = bool(user and other != uid and con.execute("SELECT 1 FROM blocks WHERE blocker_user_id=? AND blocked_user_id=?", (uid, other)).fetchone())
                    reported = bool(user and other != uid and con.execute("SELECT 1 FROM reports WHERE reporter_user_id=? AND target_user_id=? AND status='open'", (uid, other)).fetchone())
                return self.json_response({"user": pu, "index_file": index_filename(other), "following": following, "blocked": blocked, "reported": reported, "report_count": report_count_for_user(other)})
            if u.path == "/api/dm-contacts":
                if not user: raise AuthRequiredError("DMにはログインが必要です")
                with db_conn() as con:
                    followed = {int(r[0]) for r in con.execute("SELECT followed_user_id FROM follows WHERE follower_user_id=?", (uid,)).fetchall()}
                    chatted = {int(r[0]) for r in con.execute("SELECT CASE WHEN sender_user_id=? THEN recipient_user_id ELSE sender_user_id END AS other FROM dm_messages WHERE sender_user_id=? OR recipient_user_id=? GROUP BY other", (uid,uid,uid)).fetchall()}
                ids = sorted((followed|chatted)-{uid}); users=[]
                for oid in ids:
                    if not can_view_user(uid, oid):
                        continue
                    pu=public_user(oid); pu["following"]=oid in followed; pu["chatted"]=oid in chatted; users.append(pu)
                return self.json_response({"users":users})
            if u.path == "/api/users":
                with db_conn() as con:
                    rows = con.execute("SELECT id,username,display_name,bio,avatar_url,role,status,created_at FROM users ORDER BY username COLLATE NOCASE").fetchall()
                users = [dict(r) for r in rows if int(r["id"]) == uid or can_view_user(uid, int(r["id"]))]
                return self.json_response({"users": users})
            if u.path == "/api/communities":
                with db_conn() as con:
                    rows = con.execute("SELECT * FROM communities ORDER BY created_at DESC,id DESC").fetchall()
                return self.json_response({"communities": [community_payload(r, uid) for r in rows]})
            if u.path == "/api/community":
                q = urllib.parse.parse_qs(u.query)
                cid = int(q.get("id", [0])[0])
                with db_conn() as con:
                    row = con.execute("SELECT * FROM communities WHERE id=?", (cid,)).fetchone()
                if not row:
                    raise ValueError("コミュニティが見つかりません")
                return self.json_response({"community": community_payload(row, uid), "feed": feed_payload(uid, "latest", cid)})
            if u.path == "/api/community-admin":
                if not user: raise AuthRequiredError("コミュニティ管理にはログインが必要です")
                q=urllib.parse.parse_qs(u.query);cid=int(q.get("id",[0])[0] or 0)
                if not can_manage_community(uid,cid): raise PermissionError("コミュニティ管理権限が必要です")
                with db_conn() as con:
                    row=con.execute("SELECT * FROM communities WHERE id=?",(cid,)).fetchone()
                    members=con.execute("""SELECT u.id,u.username,u.display_name,u.role,u.status,cm.joined_at,
                        CASE WHEN cmod.user_id IS NULL THEN 0 ELSE 1 END AS community_moderator
                        FROM community_members cm JOIN users u ON u.id=cm.user_id
                        LEFT JOIN community_moderators cmod ON cmod.community_id=cm.community_id AND cmod.user_id=cm.user_id
                        WHERE cm.community_id=? ORDER BY u.username COLLATE NOCASE""",(cid,)).fetchall()
                if not row: raise ValueError("コミュニティが見つかりません")
                return self.json_response({"community":community_payload(row,uid),"members":[dict(x) for x in members]})
            if u.path == "/api/community-messages":
                if not user: raise AuthRequiredError("コミュニティDMにはログインが必要です")
                q = urllib.parse.parse_qs(u.query)
                cid = int(q.get("id", [0])[0])
                with db_conn() as con:
                    member = con.execute("SELECT 1 FROM community_members WHERE community_id=? AND user_id=?", (cid, uid)).fetchone()
                    if not member:
                        raise PermissionError("コミュニティ参加者のみチャットを閲覧できます")
                    rows = con.execute("SELECT id,user_id,body,created_at FROM community_messages WHERE community_id=? ORDER BY id DESC LIMIT 100", (cid,)).fetchall()
                messages = []
                for r in reversed(rows):
                    author_id = int(r["user_id"])
                    if not can_view_user(uid, author_id):
                        continue
                    d = dict(r); d["author"] = public_user(author_id); messages.append(d)
                return self.json_response({"messages": messages})
            if u.path == "/api/dm":
                if not user: raise AuthRequiredError("DMにはログインが必要です")
                q = urllib.parse.parse_qs(u.query)
                other = int(q.get("user_id", [0])[0])
                if not user_from_id(other):
                    raise ValueError("ユーザーが見つかりません")
                if not can_view_user(uid, other):
                    raise PermissionError("このユーザーとのDMは非表示です")
                with db_conn() as con:
                    clear = con.execute("SELECT cleared_message_id FROM dm_clears WHERE user_id=? AND other_user_id=?", (uid, other)).fetchone()
                    cleared = int(clear[0]) if clear else 0
                    rows = con.execute(
                        """SELECT id,sender_user_id,recipient_user_id,body,created_at FROM dm_messages
                           WHERE id>? AND ((sender_user_id=? AND recipient_user_id=?) OR (sender_user_id=? AND recipient_user_id=?))
                           ORDER BY id DESC LIMIT 150""", (cleared, uid, other, other, uid)
                    ).fetchall()
                messages = []
                for r in reversed(rows):
                    d = dict(r); d["author"] = public_user(int(r["sender_user_id"])); messages.append(d)
                return self.json_response({"other": public_user(other), "messages": messages})
            return self.text_response(b"Not found", "text/plain", 404)
        except AuthRequiredError as e:
            return self.json_response({"error": str(e), "auth_required": True}, 401)
        except PermissionError as e:
            return self.json_response({"error": str(e)}, 403)
        except Exception as e:
            return self.json_response({"error": str(e)}, 400)

    def do_POST(self):
        if self.redirect_public_http_to_https():
            return
        try:
            body = self.read_json()
            u = urllib.parse.urlparse(self.path)
            if u.path == "/api/local-login":
                if LOCAL_MODE:
                    raise PermissionError("このログインAPIはWeb版でのみ使用できます")
                username = str(body.get("username", "")).strip()
                password = str(body.get("password", ""))
                with db_conn() as con:
                    row = con.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
                if not row or not password_ok(password, row["password_hash"]):
                    raise PermissionError("ユーザー名またはパスワードが違います")
                row = dict(row)
                if str(row.get("status") or "active") != "active":
                    raise PermissionError("このアカウントは停止されています")
                token = issue_local_sync_token(int(row["id"]))
                return self.json_response({"token": token, "user_id": int(row["id"]),
                                           "username": str(row["username"]),
                                           "display_name": str(row.get("display_name") or row["username"])})
            if u.path == "/api/local-register":
                if LOCAL_MODE: raise PermissionError("Web版でのみ使用できます")
                check_registration_rate(self.client_ip())
                username=validate_username(body.get("username","")); password=str(body.get("password","")); ph=password_hash(password)
                with db_conn() as con:
                    try: cur=con.execute("INSERT INTO users(username,password_hash,display_name) VALUES(?,?,?)",(username,ph,username))
                    except sqlite3.IntegrityError: raise ValueError("そのユーザー名は既に使われています")
                    uid=int(cur.lastrowid); owner=con.execute("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1").fetchone()
                    if not owner: con.execute("UPDATE users SET role='owner' WHERE id=?",(uid,))
                migrate_legacy_vault(uid); token=issue_local_sync_token(uid)
                return self.json_response({"token":token,"user_id":uid,"username":username,"display_name":username})
            if u.path == "/api/local-whoami":
                sync_user=validate_local_sync_token_token(str(body.get("token", "")))
                if not sync_user: raise PermissionError("同期キーが無効です")
                return self.json_response({"user_id":int(sync_user["id"]),"username":str(sync_user["username"]),"display_name":str(sync_user.get("display_name") or sync_user["username"])})
            if u.path == "/api/local-publish":
                sync_user = validate_local_sync_token_token(str(body.get("token", "")))
                if not sync_user:
                    raise PermissionError("同期キーが無効です")
                try:
                    raw = base64.b64decode(str(body.get("bundle_base64", "")), validate=True)
                except Exception:
                    raise ValueError("公開データを読み込めません")
                return self.json_response(apply_publish_bundle(int(sync_user["id"]), raw, replace=str(body.get("mode", "replace")).lower() != "merge"))
            if u.path == "/api/local-backup":
                sync_user = validate_local_sync_token_token(str(body.get("token", "")))
                if not sync_user:
                    raise PermissionError("同期キーが無効です")
                raw = backup_zip_bytes(int(sync_user["id"]))
                return self.json_response({"backup_base64": base64.b64encode(raw).decode("ascii"), "size": len(raw)})
            if u.path == "/api/local-resume":
                if not LOCAL_MODE:
                    raise PermissionError("ローカル版でのみ使用できます")
                cfg=local_config()
                if not cfg.get("token"):
                    raise PermissionError("Webアカウントへの接続情報がありません")
                profile_data,session_token,remote_username=bootstrap_local_from_sync_key(
                    str(cfg.get("server_url") or PUBLIC_SERVER_DEFAULT),str(cfg.get("token") or ""))
                sync_result=None
                if bool(body.get("pull",True)):
                    sync_result=pull_web_backup_now(int(profile_data["id"]))
                    profile_data=profile_for_user({"id":int(profile_data["id"])})
                return self.json_response({"authenticated":True,"profile":profile_data,"remote_username":remote_username,"sync":sync_result},set_cookie=self.auth_cookie(session_token))
            if u.path == "/api/local-account-bootstrap":
                profile_data,session_token,remote_username=bootstrap_local_from_web_account(
                    str(body.get("server_url",PUBLIC_SERVER_DEFAULT)),
                    str(body.get("username","")),str(body.get("password","")))
                sync_result=None
                if bool(body.get("pull",True)):
                    sync_result=pull_web_backup_now(int(profile_data["id"]))
                    profile_data=profile_for_user({"id":int(profile_data["id"])})
                return self.json_response({"authenticated":True,"profile":profile_data,"remote_username":remote_username,"sync":sync_result},set_cookie=self.auth_cookie(session_token))
            if u.path == "/api/local-account-register":
                profile_data,session_token,remote_username=bootstrap_local_from_web_registration(str(body.get("server_url",PUBLIC_SERVER_DEFAULT)),str(body.get("username","")),str(body.get("password","")))
                sync_result=None
                if bool(body.get("pull",False)):
                    sync_result=pull_web_backup_now(int(profile_data["id"])); profile_data=profile_for_user({"id":int(profile_data["id"])})
                return self.json_response({"authenticated":True,"profile":profile_data,"remote_username":remote_username,"sync":sync_result},set_cookie=self.auth_cookie(session_token))
            if u.path == "/api/local-bootstrap":
                profile_data,session_token,remote_username=bootstrap_local_from_sync_key(str(body.get("server_url",PUBLIC_SERVER_DEFAULT)),str(body.get("token","")))
                sync_result=None
                if bool(body.get("pull",True)):
                    sync_result=pull_web_backup_now(int(profile_data["id"]))
                    profile_data=profile_for_user({"id":int(profile_data["id"])})
                return self.json_response({"authenticated":True,"profile":profile_data,"remote_username":remote_username,"sync":sync_result},set_cookie=self.auth_cookie(session_token))
            if u.path == "/api/register":
                check_registration_rate(self.client_ip())
                username = validate_username(body.get("username", ""))
                password = str(body.get("password", ""))
                ph = password_hash(password)
                with db_conn() as con:
                    try:
                        cur = con.execute("INSERT INTO users(username,password_hash,display_name) VALUES(?,?,?)", (username, ph, username))
                    except sqlite3.IntegrityError:
                        raise ValueError("そのユーザー名は既に使われています")
                    uid = int(cur.lastrowid)
                    owner = con.execute("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1").fetchone()
                    if not owner:
                        con.execute("UPDATE users SET role='owner' WHERE id=?", (uid,))
                migrate_legacy_vault(uid)
                token = make_session(uid)
                user = user_from_id(uid)
                return self.json_response({"authenticated": True, "profile": profile_for_user(user)}, set_cookie=self.auth_cookie(token))
            if u.path == "/api/login":
                username = str(body.get("username", "")).strip()
                password = str(body.get("password", ""))
                with db_conn() as con:
                    row = con.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
                if not row or not password_ok(password, row["password_hash"]):
                    raise PermissionError("ユーザー名またはパスワードが違います")
                if str(row["status"] if "status" in row.keys() else "active") != "active":
                    raise PermissionError("このアカウントは停止されています")
                token = make_session(int(row["id"]))
                return self.json_response({"authenticated": True, "profile": profile_for_user(dict(row))}, set_cookie=self.auth_cookie(token))
            if u.path == "/api/logout":
                token = self.cookie_token()
                if token:
                    with db_conn() as con:
                        con.execute("DELETE FROM sessions WHERE token_hash=?", (session_token_hash(token),))
                return self.json_response({"ok": True}, set_cookie=self.clear_auth_cookie())

            user = self.current_user()
            uid = int(user["id"])
            if u.path == "/api/profile":
                return self.json_response(save_user_profile(uid, body))
            if u.path == "/api/saved-searches":
                name=str(body.get("name","")).strip()[:80]; query=str(body.get("query","")).strip()[:1000]
                if not name or not query: raise ValueError("名前と検索条件を入力してください")
                with db_conn() as con: con.execute("INSERT INTO saved_searches(user_id,name,query) VALUES(?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET query=excluded.query,created_at=CURRENT_TIMESTAMP",(uid,name,query))
                return self.json_response({"ok":True})
            if u.path == "/api/saved-search-delete":
                with db_conn() as con: con.execute("DELETE FROM saved_searches WHERE id=? AND user_id=?",(int(body.get("id",0)),uid))
                return self.json_response({"ok":True})
            if u.path == "/api/mod-quota":
                note_mb=max(1,int(body.get("note_mb",1))); media_mb=max(1,int(body.get("media_mb",1)))
                payload={"notes_limit":body.get("notes_limit"),"note_bytes_limit":note_mb*1024*1024,"media_bytes_limit":media_mb*1024*1024,"relations_limit":body.get("relations_limit")}
                return self.json_response(set_user_quota(uid,int(body.get("user_id",0)),payload))
            if u.path == "/api/mod-global-quota":
                note_mb=max(1,int(body.get("note_mb",1))); media_mb=max(1,int(body.get("media_mb",1)))
                payload={"notes_limit":body.get("notes_limit"),"note_bytes_limit":note_mb*1024*1024,"media_bytes_limit":media_mb*1024*1024,"relations_limit":body.get("relations_limit")}
                return self.json_response(set_global_quota_limits(uid,payload))
            if u.path == "/api/backup-import":
                try:
                    raw = base64.b64decode(str(body.get("data_base64", "")), validate=True)
                except Exception:
                    raise ValueError("バックアップZIPを読み込めません")
                return self.json_response(import_backup_zip(uid, raw))
            if u.path == "/api/sync-token":
                if LOCAL_MODE:
                    raise PermissionError("同期キーはWeb版で発行してください")
                return self.json_response({"token": issue_local_sync_token(uid), "username": username_for_user_id(uid)})
            if u.path == "/api/local-settings":
                return self.json_response(save_local_config(body))
            if u.path == "/api/local-disconnect":
                if not LOCAL_MODE: raise PermissionError("ローカル版でのみ使用できます")
                cfg=local_config(); cfg.update({"token":"","remote_username":"","remote_user_id":0,
                                                "auto_upload":False,"last_pull_at":"","last_push_at":"",
                                                "sync_hashes":{},"sync_file_map":{}})
                write_local_config(cfg)
                return self.json_response({"ok":True})
            if u.path == "/api/local-publish-now":
                return self.json_response(publish_local_now(uid))
            if u.path == "/api/local-export-preview":
                if not LOCAL_MODE: raise PermissionError("ローカル版でのみ使用できます")
                return self.json_response(local_export_candidates(uid))
            if u.path == "/api/local-export-selected":
                notes = body.get("notes") if isinstance(body.get("notes"), list) else []
                attachments = body.get("attachments") if isinstance(body.get("attachments"), list) else []
                return self.json_response(export_selected_local_now(uid, notes, attachments))
            if u.path == "/api/local-pull":
                return self.json_response(pull_web_backup_now(uid))
            if u.path == "/api/note-publish-settings":
                name = safe_name(body.get("name", ""))
                if file_owner_id(name) != uid:
                    raise PermissionError("自分のノートだけ設定できます")
                content = read_file(name)
                if "upload_enabled" in body:
                    content = set_note_upload_enabled(content, bool(body.get("upload_enabled")))
                if body.get("target"):
                    target = safe_name(str(body.get("target")))
                    content = set_note_private_target(content, target, bool(body.get("private", False)))
                write_file(name, content)
                schedule_local_publish(uid)
                return self.json_response(sns_file_payload(name, uid, f"user:{uid}"))
            if u.path == "/api/block":
                other = int(body.get("user_id", 0))
                if other == uid or not user_from_id(other):
                    raise ValueError("ユーザーが見つかりません")
                with db_conn() as con:
                    exists = con.execute("SELECT 1 FROM blocks WHERE blocker_user_id=? AND blocked_user_id=?", (uid, other)).fetchone()
                    if exists:
                        con.execute("DELETE FROM blocks WHERE blocker_user_id=? AND blocked_user_id=?", (uid, other)); blocked = False
                    else:
                        con.execute("INSERT INTO blocks(blocker_user_id,blocked_user_id) VALUES(?,?)", (uid, other)); blocked = True
                return self.json_response({"blocked": blocked})
            if u.path == "/api/report":
                target_user = int(body.get("user_id", 0) or 0)
                note = str(body.get("note", "") or "")
                reason = str(body.get("reason", "") or "")[:1000]
                if note:
                    note = safe_name(note)
                    if not (VAULT / note).exists():
                        raise ValueError("ノートが見つかりません")
                    target_user = int(file_owner_id(note) or 0)
                if not target_user or target_user == uid:
                    raise ValueError("通報対象を確認してください")
                with db_conn() as con:
                    duplicate = con.execute("""SELECT 1 FROM reports WHERE reporter_user_id=? AND status='open'
                                               AND COALESCE(target_user_id,0)=? AND note_file=?""", (uid, target_user, note)).fetchone()
                    if not duplicate:
                        con.execute("INSERT INTO reports(reporter_user_id,target_user_id,note_file,reason) VALUES(?,?,?,?)", (uid,target_user,note,reason))
                return self.json_response({"ok": True, "user_report_count": report_count_for_user(target_user), "note_report_count": report_count_for_note(note) if note else 0})
            if u.path == "/api/mod-role":
                if user_role(uid) != "owner":
                    raise PermissionError("OwnerだけがModerator権限を変更できます")
                other = int(body.get("user_id", 0)); role = str(body.get("role", "user"))
                if role not in {"user","moderator"}:
                    raise ValueError("roleが不正です")
                target = user_from_id(other)
                if not target or str(target.get("role")) == "owner":
                    raise PermissionError("Ownerは変更できません")
                with db_conn() as con:
                    con.execute("UPDATE users SET role=? WHERE id=?", (role,other))
                moderation_log(uid, "set_role:"+role, other, reason=str(body.get("reason", "")))
                return self.json_response({"ok": True})
            if u.path == "/api/mod-status":
                if not is_moderator_user(uid):
                    raise PermissionError("管理権限が必要です")
                other = int(body.get("user_id", 0)); status_value = str(body.get("status", "suspended"))
                if status_value not in {"active","suspended"}:
                    raise ValueError("statusが不正です")
                target = user_from_id(other)
                if not target or str(target.get("role")) == "owner":
                    raise PermissionError("Ownerは停止できません")
                if str(target.get("role")) == "moderator" and user_role(uid) != "owner":
                    raise PermissionError("Moderatorを停止できるのはOwnerだけです")
                reason = str(body.get("reason", ""))[:1000]
                with db_conn() as con:
                    con.execute("UPDATE users SET status=?,suspended_reason=? WHERE id=?", (status_value, reason if status_value=='suspended' else '', other))
                    if status_value == 'suspended':
                        con.execute("DELETE FROM sessions WHERE user_id=?", (other,))
                moderation_log(uid, "set_status:"+status_value, other, reason=reason)
                return self.json_response({"ok": True})
            if u.path == "/api/mod-delete":
                return self.json_response(hard_delete_user(uid, int(body.get("user_id", 0)), str(body.get("reason", ""))))
            if u.path == "/api/mod-report-resolve":
                if not is_moderator_user(uid):
                    raise PermissionError("管理権限が必要です")
                rid = int(body.get("report_id", 0)); action = str(body.get("action", "resolved"))
                with db_conn() as con:
                    row = con.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
                    if not row:
                        raise ValueError("通報が見つかりません")
                    con.execute("UPDATE reports SET status='resolved' WHERE id=?", (rid,))
                moderation_log(uid, "resolve_report:"+action, int(row["target_user_id"] or 0) or None, str(row["note_file"] or ""), str(row["reason"] or ""))
                return self.json_response({"ok": True})
            if u.path == "/api/upload-avatar":
                return self.json_response(save_avatar(uid, str(body.get("data_url", ""))))
            if u.path == "/api/upload-image":
                return self.json_response(save_inline_image(uid, str(body.get("data_url", "")), str(body.get("name", "image"))))
            if u.path == "/api/upload-attachment":
                return self.json_response(save_attachment(uid, str(body.get("data_url", "")), str(body.get("name", "file"))))
            if u.path == "/api/file":
                name = safe_name(body["name"])
                if not can_edit_note(uid,name):
                    raise PermissionError("このノートを編集する権限がありません")
                try: client_seq=int(body.get("client_seq",-1))
                except Exception: client_seq=-1
                client_session=str(body.get("client_save_session","") or "")
                new_content = body.get("content", "")
                commit_relations = bool(body.get("commit_relations", True))
                save_result=save_client_note(uid,name,new_content,commit_relations,client_session,client_seq)
                if save_result.get("stale"):
                    payload=sns_file_payload(name,uid,f"user:{uid}"); payload["stale_save_ignored"]=True
                    return self.json_response(payload)
                old_title=str(save_result.get("old_title") or "")
                new_title=str(save_result.get("title") or title_of(read_file(name),name))
                # Auto-upload is debounced server-side. Body-only edits must sync too;
                # previously they could remain Local forever unless a relation changed.
                schedule_local_publish(uid)
                if bool(body.get("draft_response",False)) and not commit_relations:
                    saved=read_file(name)
                    return self.json_response({"name":name,"title":title_of(saved,name),"content":saved,
                                               "relations_committed":False,"draft_saved":True})
                payload = sns_file_payload(name, uid, f"user:{uid}")
                payload["relations_committed"] = commit_relations
                return self.json_response(payload)
            if u.path == "/api/new-linked":
                title = str(body.get("title", "")).strip()[:160]
                if not title:
                    raise ValueError("タイトルを入力してください")
                check_and_record_rate(uid, "note_create")
                filename = user_node_filename(uid)
                new_content = new_note_markdown(filename, title) + "\n"
                enforce_note_write_quota(uid, filename, new_content)
                write_file(filename, new_content)
                sync_edges(); schedule_local_publish(uid)
                return self.json_response({"file": filename, "title": title})
            if u.path == "/api/delete-notes":
                raw_files = body.get("files", [])
                if not isinstance(raw_files, list):
                    raise ValueError("files must be a list")
                deleted = delete_owned_notes(uid, [str(x) for x in raw_files])
                schedule_local_publish(uid)
                return self.json_response({"deleted": deleted, "index_file": index_filename(uid)})
            if u.path == "/api/new":
                source = safe_name(body.get("source", index_filename(uid)))
                if not can_create_child_from(uid,source):
                    raise PermissionError("このノートから新規ノードを作成できません")
                title = str(body["title"]).strip()
                relation = str(body["relation"]).strip()
                if not title or not relation:
                    raise ValueError("title and relation are required")
                check_and_record_rate(uid, "note_create")
                filename = user_node_filename(uid)
                source_title = title_of(read_file(source), source)
                # New nodes are children of the page they were created from.
                # Canonical Parent edge lives above ``---`` in the new node;
                # the source page's Child side is rebuilt automatically.
                new_content = add_link_to_relation_side(new_note_markdown(filename, title), relation, source_title, source, "parent")
                enforce_note_write_quota(uid, filename, new_content)
                write_file(filename, new_content)
                sync_edges(); schedule_local_publish(uid)
                return self.json_response({"file": filename})
            if u.path == "/api/edge-new":
                direction = str(body.get("direction", "outgoing")); current_name = safe_name(body.get("current", index_filename(uid)))
                relation = str(body.get("relation", "")).strip()[:80]
                title = str(body.get("title", "")).strip()[:160]
                if not relation or not title:
                    raise ValueError("関係名とタイトルを入力してください")
                if not (VAULT / current_name).exists():
                    raise ValueError("現在のノートが見つかりません")
                check_and_record_rate(uid, "note_create")
                filename = user_node_filename(uid)
                if direction == "outgoing":
                    if is_index_file(current_name): raise ValueError("IndexにはParentを追加しません")
                    new_content = new_note_markdown(filename, title) + "\n---\n"
                    enforce_note_write_quota(uid, filename, new_content);write_file(filename,new_content)
                    if file_owner_id(current_name) == uid:
                        current_content = add_link_to_relation(read_file(current_name), relation, title, filename)
                        enforce_note_write_quota(uid, current_name, current_content);write_file(current_name,current_content)
                    else:
                        add_external_edge(uid,current_name,filename,relation)
                elif direction == "incoming":
                    current_title = title_of(read_file(current_name), current_name)
                    new_content = add_link_to_relation(new_note_markdown(filename, title), relation, current_title, current_name)
                    enforce_note_write_quota(uid, filename, new_content)
                    write_file(filename, new_content)
                else:
                    raise ValueError("invalid direction")
                sync_edges(); schedule_local_publish(uid)
                return self.json_response({"file": filename, "current": sns_file_payload(current_name, uid, f"user:{uid}")})
            if u.path == "/api/edge-delete":
                direction = str(body.get("direction", "outgoing"))
                current_name = safe_name(body.get("current", index_filename(uid)))
                raw_edges = body.get("edges", [])
                if not isinstance(raw_edges, list):
                    raise ValueError("edges must be a list")
                delete_edges_for_user(uid, current_name, direction, [x for x in raw_edges if isinstance(x, dict)])
                schedule_local_publish(uid)
                return self.json_response(sns_file_payload(current_name, uid, f"user:{uid}"))
            if u.path == "/api/edge-add":
                direction = str(body.get("direction", "outgoing")); current_name = safe_name(body.get("current", index_filename(uid)))
                relation = str(body.get("relation", "")).strip()[:80]
                if not relation: raise ValueError("関係名を入力してください")
                chosen = str(body.get("file", "")).strip(); reference = str(body.get("reference", "")).strip()
                other = resolve_note_reference(reference) if reference else safe_name(chosen)
                if not (VAULT / other).exists(): raise ValueError("ノートが見つかりません")
                if direction == "outgoing":
                    source, target = current_name, other
                    if is_index_file(source): raise ValueError("IndexにはParentを追加しません")
                    if not can_edit_note(uid,source):
                        add_external_edge(uid,source,target,relation);schedule_local_publish(uid)
                        return self.json_response(sns_file_payload(current_name,uid,f"user:{uid}"))
                elif direction == "incoming":
                    source, target = other, current_name
                    if file_owner_id(source) != uid: raise PermissionError("バックリンク追加には自分のノートをリンク元として選んでください")
                else: raise ValueError("invalid direction")
                if source == target: raise ValueError("同じノート自身にはリンクできません")
                target_title = title_of(read_file(target), target)
                updated = add_link_to_relation(read_file(source), relation, target_title, target)
                enforce_note_write_quota(uid, source, updated)
                write_file(source, updated)
                sync_edges(); schedule_local_publish(uid)
                return self.json_response(sns_file_payload(current_name, uid, f"user:{uid}"))
            if u.path == "/api/organize-link":
                container=safe_name(body.get("container",index_filename(uid)));item=safe_name(body.get("item",""));category_raw=str(body.get("category","")).strip();new_category=str(body.get("new_category","")).strip()[:160]
                action=str(body.get("action","add"));relation=str(body.get("relation","ノート")).strip()[:80] or "ノート";original_relation=str(body.get("original_relation",relation)).strip()[:80] or relation;requested_edge_id=int(body.get("edge_id") or 0)
                if action not in {"move","add"}: raise ValueError("処理を確認してください")
                if not (VAULT/container).exists() or not (VAULT/item).exists(): raise ValueError("対象ノートが見つかりません")
                # Locate the actual Child -> current relation the user selected, including collaborative external edges.
                canonical=[]
                for rel,_lab,t in parse_outgoing(read_file(item)):
                    if t==container: canonical.append((rel,"owner",0,file_owner_id(item)))
                ext=[r for r in external_edge_rows(source=item,target=container)] if not LOCAL_MODE else []
                matches=canonical+[(r["relation"],"external",int(r["id"]),int(r["creator_user_id"])) for r in ext]
                if not matches: raise ValueError("現在のページへのリンクが見つかりません")
                chosen=None
                if requested_edge_id: chosen=next((x for x in matches if x[1]=="external" and x[2]==requested_edge_id),None)
                if chosen is None: chosen=next((x for x in matches if normalized_relation(x[0])==normalized_relation(original_relation)),matches[0])
                source_rel,kind,edge_id,creator_id=chosen
                movable=(kind=="owner" and file_owner_id(item)==uid) or (kind=="external" and creator_id==uid)
                if action=="move" and not movable: raise PermissionError("他の人が作ったリンクは移動できません。追加を使用してください")
                if new_category:
                    check_and_record_rate(uid,"note_create");category=user_node_filename(uid);cat_content=new_note_markdown(category,new_category)
                    container_title=title_of(read_file(container),container)
                    cat_content=add_link_to_relation(cat_content,"カテゴリー",container_title,container);enforce_note_write_quota(uid,category,cat_content);write_file(category,cat_content)
                else:
                    category=safe_name(category_raw)
                    if not category or not (VAULT/category).exists(): raise ValueError("カテゴリーを選択してください")
                if category in {item,container}: raise ValueError("移動先カテゴリーを確認してください")
                category_title=title_of(read_file(category),category)
                if file_owner_id(item)==uid:
                    item_content=read_file(item)
                    if action=="move": item_content=remove_exact_edge(item_content,source_rel,container)
                    item_content=add_link_to_relation(item_content,relation,category_title,category);enforce_note_write_quota(uid,item,item_content);write_file(item,item_content)
                else:
                    add_external_edge(uid,item,category,relation)
                    if action=="move" and kind=="external" and edge_id:
                        with db_conn() as con: con.execute("DELETE FROM external_edges WHERE id=? AND creator_user_id=?",(edge_id,uid))
                sync_edges();schedule_local_publish(uid)
                return self.json_response({"current":sns_file_payload(container,uid,f"user:{uid}"),"category":category,"item":item})
            if u.path == "/api/topic-edge-vote":
                source = safe_name(body["source"]); target = safe_name(body["target"])
                if file_owner_id(source) == uid:
                    raise PermissionError("自分のノートには適切・不適切を入力できません")
                voter = f"user:{uid}"; vote = body.get("vote")
                if vote not in (None, "appropriate", "inappropriate"):
                    raise ValueError("invalid vote")
                contents = {f: read_file(f) for f in all_md_files()}
                topic_norm = {normalized_relation(x) for x in {"カテゴリー", "トピック", "topic", "topics"}}
                has_edge = any(t == target and normalized_relation(rel) in topic_norm for rel, _lab, t in parse_outgoing(contents[source]))
                if is_index_file(source) or not has_edge:
                    raise ValueError("ratings are only for topic links inside ordinary notes")
                ratings = load_topic_ratings(); targets = ratings.setdefault(source, {}); votes = targets.setdefault(target, {})
                if vote is None: votes.pop(voter, None)
                else: votes[voter] = vote
                if not votes: targets.pop(target, None)
                if not targets: ratings.pop(source, None)
                save_topic_ratings(ratings)
                return self.json_response(sns_file_payload(source, uid, voter))
            if u.path == "/api/like":
                note = safe_name(body["file"])
                if not (VAULT / note).exists() or is_index_file(note):
                    raise ValueError("invalid post")
                with db_conn() as con:
                    exists = con.execute("SELECT 1 FROM likes WHERE user_id=? AND note_file=?", (uid, note)).fetchone()
                    if exists: con.execute("DELETE FROM likes WHERE user_id=? AND note_file=?", (uid, note)); liked = False
                    else: con.execute("INSERT INTO likes(user_id,note_file) VALUES(?,?)", (uid, note)); liked = True
                    count = int(con.execute("SELECT COUNT(*) FROM likes WHERE note_file=?", (note,)).fetchone()[0])
                return self.json_response({"liked": liked, "like_count": count})
            if u.path == "/api/community-admin-save":
                cid=int(body.get("community_id",0));name=str(body.get("name","")).strip()[:120];description=str(body.get("description","")).strip()[:1000]
                if not can_manage_community(uid,cid): raise PermissionError("コミュニティ管理権限が必要です")
                if len(name)<2: raise ValueError("コミュニティ名は2文字以上にしてください")
                with db_conn() as con: con.execute("UPDATE communities SET name=?,description=? WHERE id=?",(name,description,cid))
                return self.json_response({"ok":True})
            if u.path == "/api/community-moderator":
                cid=int(body.get("community_id",0));target=int(body.get("user_id",0));enabled=bool(body.get("enabled"))
                if not can_manage_community_roles(uid,cid): raise PermissionError("モデレーター権限を変更できません")
                row=community_row(cid)
                if not row: raise ValueError("コミュニティが見つかりません")
                if target==int(row["owner_user_id"]): raise ValueError("作成者の権限は変更できません")
                with db_conn() as con:
                    if enabled: con.execute("INSERT OR IGNORE INTO community_moderators(community_id,user_id) VALUES(?,?)",(cid,target))
                    else: con.execute("DELETE FROM community_moderators WHERE community_id=? AND user_id=?",(cid,target))
                return self.json_response({"ok":True})
            if u.path == "/api/community-member-remove":
                cid=int(body.get("community_id",0));target=int(body.get("user_id",0))
                if not can_manage_community(uid,cid): raise PermissionError("コミュニティ管理権限が必要です")
                row=community_row(cid)
                if not row: raise ValueError("コミュニティが見つかりません")
                if target==int(row["owner_user_id"]): raise ValueError("作成者は退出させられません")
                with db_conn() as con:
                    con.execute("DELETE FROM community_moderators WHERE community_id=? AND user_id=?",(cid,target))
                    con.execute("DELETE FROM community_members WHERE community_id=? AND user_id=?",(cid,target))
                return self.json_response({"ok":True})
            if u.path == "/api/community-index":
                cid = int(body.get("community_id", 0)); markdown = str(body.get("markdown", ""))[:200000]
                if not can_manage_community(uid,cid): raise PermissionError("コミュニティ管理者だけがIndexを編集できます")
                name=ensure_community_index(cid); old=read_file(name); fm,_=split_yaml_frontmatter(old); content=(fm.rstrip()+"\n\n" if fm else "")+(markdown or "# Index\n").lstrip("\n")
                if not content.rstrip().endswith("---"): content=content.rstrip()+"\n\n---\n"
                write_file(name,content);sync_edges()
                return self.json_response({"ok": True,"index_file":name})
            if u.path == "/api/community-create":
                name = str(body.get("name", "")).strip()[:120]; description = str(body.get("description", "")).strip()[:1000]
                if len(name) < 2: raise ValueError("コミュニティ名は2文字以上にしてください")
                with db_conn() as con:
                    cur = con.execute("INSERT INTO communities(name,description,owner_user_id) VALUES(?,?,?)", (name, description, uid)); cid = int(cur.lastrowid)
                    con.execute("INSERT INTO community_members(community_id,user_id) VALUES(?,?)", (cid, uid))
                    row = con.execute("SELECT * FROM communities WHERE id=?", (cid,)).fetchone()
                ensure_community_index(cid)
                return self.json_response({"community": community_payload(row, uid)})
            if u.path == "/api/community-join":
                cid = int(body.get("community_id", 0))
                with db_conn() as con:
                    exists = con.execute("SELECT 1 FROM community_members WHERE community_id=? AND user_id=?", (cid, uid)).fetchone()
                    if exists:
                        crow=con.execute("SELECT owner_user_id FROM communities WHERE id=?",(cid,)).fetchone()
                        if crow and int(crow[0])==uid: raise ValueError("コミュニティ作成者は退出できません")
                        con.execute("DELETE FROM community_moderators WHERE community_id=? AND user_id=?",(cid,uid))
                        con.execute("DELETE FROM community_members WHERE community_id=? AND user_id=?", (cid, uid)); joined = False
                    else: con.execute("INSERT INTO community_members(community_id,user_id) VALUES(?,?)", (cid, uid)); joined = True
                return self.json_response({"joined": joined})
            if u.path == "/api/community-share":
                cid = int(body.get("community_id", 0)); note = safe_name(body["file"])
                if file_owner_id(note) != uid: raise PermissionError("自分のノートのみ共有できます")
                with db_conn() as con:
                    member = con.execute("SELECT 1 FROM community_members WHERE community_id=? AND user_id=?", (cid, uid)).fetchone()
                    if not member: raise PermissionError("先にコミュニティへ参加してください")
                    con.execute("INSERT OR IGNORE INTO community_posts(community_id,note_file,user_id) VALUES(?,?,?)", (cid, note, uid))
                return self.json_response({"ok": True})
            if u.path == "/api/community-message":
                cid = int(body.get("community_id", 0)); text = str(body.get("body", "")).strip()[:4000]
                if not text: raise ValueError("メッセージを入力してください")
                with db_conn() as con:
                    member = con.execute("SELECT 1 FROM community_members WHERE community_id=? AND user_id=?", (cid, uid)).fetchone()
                    if not member: raise PermissionError("コミュニティ参加者のみ送信できます")
                    con.execute("INSERT INTO community_messages(community_id,user_id,body) VALUES(?,?,?)", (cid, uid, text))
                return self.json_response({"ok": True})
            if u.path == "/api/follow":
                other = int(body.get("user_id", 0))
                if other == uid or not user_from_id(other): raise ValueError("ユーザーが見つかりません")
                if not can_view_user(uid, other): raise PermissionError("このユーザーは非表示です")
                with db_conn() as con:
                    exists = con.execute("SELECT 1 FROM follows WHERE follower_user_id=? AND followed_user_id=?", (uid,other)).fetchone()
                    if exists: con.execute("DELETE FROM follows WHERE follower_user_id=? AND followed_user_id=?", (uid,other)); following=False
                    else: con.execute("INSERT INTO follows(follower_user_id,followed_user_id) VALUES(?,?)", (uid,other)); following=True
                return self.json_response({"following":following})
            if u.path == "/api/dm-clear":
                other = int(body.get("user_id", 0))
                if other == uid or not user_from_id(other): raise ValueError("ユーザーが見つかりません")
                with db_conn() as con:
                    row=con.execute("SELECT COALESCE(MAX(id),0) FROM dm_messages WHERE (sender_user_id=? AND recipient_user_id=?) OR (sender_user_id=? AND recipient_user_id=?)", (uid,other,other,uid)).fetchone(); max_id=int(row[0] or 0)
                    con.execute("INSERT INTO dm_clears(user_id,other_user_id,cleared_message_id) VALUES(?,?,?) ON CONFLICT(user_id,other_user_id) DO UPDATE SET cleared_message_id=excluded.cleared_message_id,cleared_at=CURRENT_TIMESTAMP", (uid,other,max_id))
                return self.json_response({"ok":True})
            if u.path == "/api/dm":
                other = int(body.get("user_id", 0)); text = str(body.get("body", "")).strip()[:4000]
                if other == uid: raise ValueError("自分自身には送信できません")
                if not user_from_id(other): raise ValueError("ユーザーが見つかりません")
                if not can_view_user(uid, other): raise PermissionError("このユーザーとのDMは利用できません")
                if not text: raise ValueError("メッセージを入力してください")
                with db_conn() as con:
                    con.execute("INSERT INTO dm_messages(sender_user_id,recipient_user_id,body) VALUES(?,?,?)", (uid, other, text))
                return self.json_response({"ok": True})
            if u.path == "/api/sync":
                sync_edges(); return self.json_response({"ok": True})
            return self.text_response(b"Not found", "text/plain", 404)
        except AuthRequiredError as e:
            return self.json_response({"error": str(e), "auth_required": True}, 401)
        except PermissionError as e:
            return self.json_response({"error": str(e)}, 403)
        except Exception as e:
            return self.json_response({"error": str(e)}, 400)


def main():
    global LOCAL_MODE
    parser = argparse.ArgumentParser(description="Local-first Markdown network SNS")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--local", action="store_true", help="run as the offline/local desktop edition")
    args = parser.parse_args()
    # Generated Local packages carry a marker so running app/app.py directly
    # remains account-free even when the launcher is bypassed.
    LOCAL_MODE = bool(args.local or LOCAL_PACKAGE_MARKER.is_file())
    init_db()
    ensure_vault()
    migrate_https_asset_urls()
    migrate_numeric_user_filenames()
    migrate_existing_child_side_v41()
    repair_index_titles()
    ensure_created_frontmatter_all_notes()
    ensure_creator_metadata_all_notes()
    migrate_relation_vocabulary_v70()
    migrate_relation_vocabulary_v72()
    remove_index_parent_edges()
    sync_edges()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Network Notes{' Local' if LOCAL_MODE else ''}: {url}")
    print(f"Vault: {VAULT}")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
