## ============================================================
## Lessons in Love — LLM Translation Layer
## Drop-in file. Delete to restore original game.
## ============================================================

init -100 python:
    import json as _json
    import os as _os
    import re as _re
    import threading as _threading
    import renpy.store as store

    try:
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError, URLError
    except ImportError:
        from urllib2 import Request, urlopen, HTTPError, URLError
    import ssl
    try:
        _TL_SSL_CTX = ssl._create_unverified_context()
    except Exception:
        _TL_SSL_CTX = None

    def _tl_urlopen(req, timeout=30):
        if _TL_SSL_CTX is not None:
            return urlopen(req, timeout=timeout, context=_TL_SSL_CTX)
        else:
            return urlopen(req, timeout=timeout)

    # -- paths ------------------------------------------------------------------
    _TL_DIR = _os.path.join(renpy.config.gamedir, "translator")
    _TL_CFG   = _os.path.join(_TL_DIR, "config.json")
    _TL_CACHE = _os.path.join(_TL_DIR, "cache.json")
    _TL_STATE = _os.path.join(_TL_DIR, "state.json")
    _TL_GLOSS = _os.path.join(_TL_DIR, "glossary.json")
    _os.makedirs(_TL_DIR, exist_ok=True)

    # -- json helpers -----------------------------------------------------------
    def _tl_load_json(path, default=None):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return _json.load(f)
        except Exception:
            return default if default is not None else {}

    def _tl_save_json(path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # -- load persistent state --------------------------------------------------
    _tl_cfg   = _tl_load_json(_TL_CFG, {})
    _tl_cache = _tl_load_json(_TL_CACHE, {})
    _tl_state = _tl_load_json(_TL_STATE, {"enabled": True})

    # -- build system prompt ----------------------------------------------------
    _tl_system_prompt = _tl_cfg.get("system_prompt", "")
    _tl_glossary = _tl_load_json(_TL_GLOSS, {})
    if _tl_glossary:
        lines = ["\n\n## TERMINOLOGY GLOSSARY\nUse these translations for the following terms:\n"]
        for category, terms in _tl_glossary.items():
            if category.startswith("_"):
                continue
            cat_name = category.replace("_", " ").title()
            lines.append("\n### {}\n".format(cat_name))
            for en, entry in terms.items():
                zh = entry.get("zh", "")
                note = entry.get("note", "")
                if zh:
                    line = "- {} -> {}".format(en, zh)
                    if note:
                        line += " ({})".format(note)
                    lines.append(line)
        _tl_system_prompt += "\n".join(lines)

    _tl_api = _tl_cfg.get("api", {})
    _tl_api_key = _tl_api.get("api_key", "")
    _tl_api_ok = bool(_tl_api_key) and _tl_api_key != "YOUR_DEEPSEEK_API_KEY_HERE"

    # -- request queue (Python 2/3 compat) --------------------------------------
    try:
        from queue import Queue
    except ImportError:
        from Queue import Queue
    _TL_QUEUE_SIZE = _tl_api.get("queue_size", 20)


init -99 python:
    class TranslatorEngine:
        """Translation lifecycle: cache, serial request queue, background worker."""

        def __init__(self):
            self._lock = _threading.Lock()
            self._pending = {}    # key -> True (in queue or processing)
            self._done = {}       # key -> translated text
            self._queue = Queue(maxsize=_TL_QUEUE_SIZE)
            self._start_worker()

        # -- enable / disable ---------------------------------------------------
        @property
        def enabled(self):
            return _tl_state.get("enabled", True) and _tl_api_ok

        @enabled.setter
        def enabled(self, val):
            _tl_state["enabled"] = val
            _tl_save_json(_TL_STATE, _tl_state)

        # -- cache key ----------------------------------------------------------
        def _key(self, speaker, text):
            clean = text.replace("{i}", "").replace("{/i}", "")\
                        .replace("{b}", "").replace("{/b}", "").strip()
            return "{}|||{}".format(speaker or "(Narrator)", clean)

        # -- main entry ---------------------------------------------------------
        def get(self, speaker, text):
            if not self.enabled:
                return ""
            if not text or not isinstance(text, str) or not text.strip():
                return ""
            stripped = text.replace("{i}", "").replace("{/i}", "")\
                           .replace("{b}", "").replace("{/b}", "").strip()
            if len(stripped) <= 1:
                return ""
            key = self._key(speaker, text)
            if key in _tl_cache:
                return _tl_cache[key]
            if _os.path.exists(_TL_CACHE):
                fresh = _tl_load_json(_TL_CACHE, {})
                if key in fresh:
                    _tl_cache.clear()
                    _tl_cache.update(fresh)
                    return _tl_cache[key]
            
            with self._lock:
                if key in self._done:
                    result = self._done.pop(key)
                    _tl_cache[key] = result
                    _tl_save_json(_TL_CACHE, _tl_cache)
                    return result
                if key in self._pending:
                    return "..."
                self._pending[key] = True
            try:
                self._queue.put_nowait((speaker, text))
            except Exception:
                with self._lock:
                    self._pending.pop(key, None)
            return "..."

        # -- refresh ------------------------------------------------------------
        def refresh(self, speaker, text):
            key = self._key(speaker, text)
            _tl_cache.pop(key, None)
            with self._lock:
                self._pending.pop(key, None)
                self._done.pop(key, None)
            _tl_save_json(_TL_CACHE, _tl_cache)
            return self.get(speaker, text)

        def _start_worker(self):
            t = _threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
        
        def _worker_loop(self):
            while True:
                speaker, text = self._queue.get()
                result = self._call_api(speaker, text)
                key = self._key(speaker, text)
                with self._lock:
                    self._done[key] = result
                self._queue.task_done()
        
        def _build_user_msg(self, speaker, text):
            return "Speaker: {}\n\nTranslate:\n{}".format(
                speaker or "(Narrator)", text)

        def _call_api(self, speaker, text):
            """Call API and return translation."""
            api = _tl_cfg.get("api", {})
            base = api.get("base_url", "https://api.deepseek.com/v1").rstrip("/")
            body = _json.dumps({
                "model": api.get("model", "deepseek-chat"),
                "messages": [
                    {"role": "system", "content": _tl_system_prompt},
                    {"role": "user", "content": self._build_user_msg(speaker, text)},
                ],
                "max_tokens": api.get("max_tokens", 1024),
                "temperature": api.get("temperature", 0.3),
                "stream": False,
            }).encode("utf-8")

            req = Request(base + "/chat/completions", data=body)
            req.add_header("Authorization", "Bearer {}".format(api.get("api_key", "")))
            req.add_header("Content-Type", "application/json")

            try:
                resp = _tl_urlopen(req, timeout=30)
                raw = resp.read().decode("utf-8")
                data = _json.loads(raw)
                result = data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                return "[Error: {}]".format(str(e)[:80])

            return self._post_process(result, text, speaker)

        def _post_process(self, result, text, speaker=None):
            import re as _tl_re
            # Strip various speaker-name prefixes the LLM may add
            if speaker:
                for sep in (": ", ":", "：", "： ", "\n", "\uff1a\n"):
                    if result.startswith(speaker + sep):
                        result = result[len(speaker + sep):].strip()
                        break
            # Parenthetical speaker tags
            result = _tl_re.sub(
                r'^\((?:Narrator|旁白|Speaker|说话人)\)[:\uff1a]?\s*\n?',
                '', result
            ).strip()
            # Bare speaker name with colon at start
            result = _tl_re.sub(
                r'^[A-Z][a-z]+[:\uff1a]\s*',
                '', result
            ).strip()
            wrappers = [('"', '"'), ("'", "'"), ("\u201c", "\u201d"), ("\u300c", "\u300d")]
            for left, right in wrappers:
                if len(result) >= 2 and result.startswith(left) and result.endswith(right):
                    inner = result[1:-1].strip()
                    if inner:
                        result = inner
                        break
            result = _re.sub(
                r'^(Translation|译文|翻译)\s*[:：]\s*',
                '', result, flags=_re.IGNORECASE
            ).strip()
            result = _re.sub(r'  +', ' ', result)
            result = _re.sub(r'\n\n+', '\n', result)
            cr = result.replace("{i}", "").replace("{/i}", "")\
                       .replace("{b}", "").replace("{/b}", "").strip()
            co = text.replace("{i}", "").replace("{/i}", "")\
                     .replace("{b}", "").replace("{/b}", "").strip()
            if cr.lower() == co.lower() and len(co) > 3:
                return "[Same as original]"
            return result.strip()

    tl_engine = TranslatorEngine()


# ================================================================
# Dialogue interception
# ================================================================

init -98 python:
    _say_orig = renpy.exports.say

    def _say_hook(who, what, *a, **kw):
        if who is None:
            sp = "(Narrator)"
        elif hasattr(who, "name"):
            sp = who.name or "(Narrator)"
        else:
            sp = str(who) if who else "(Narrator)"
        store._tl_sp = sp
        store._tl_tx = what
        return _say_orig(who, what, *a, **kw)

    renpy.exports.say = _say_hook


# ================================================================
# Translation overlay
# ================================================================

init -97 python:
    def _tl_overlay_func(st, at):
        text = getattr(store, "_tl_tx", None)
        speaker = getattr(store, "_tl_sp", None)

        if not text or not tl_engine.enabled:
            return renpy.text.text.Text("", substitute=False), None

        result = tl_engine.get(speaker, text)

        if not result:
            return renpy.text.text.Text("", substitute=False), None

            txt = renpy.text.text.Text(result, style="tl_overlay_style", substitute=False)
            return txt, 0.08
        if result == "...":
            return renpy.text.text.Text("", substitute=False), 0.3

        if result.startswith("[Error") or result == "[Same as original]":
            return renpy.text.text.Text("", substitute=False), None

        txt = renpy.text.text.Text(result, style="tl_overlay_style", substitute=False)
        return txt, None


screen tl_overlay():
    if tl_engine.enabled:
        fixed:
            xpos 402
            ypos 745
            xmaximum 1116
            add DynamicDisplayable(_tl_overlay_func)


init -96 python:
    config.overlay_screens.append("tl_overlay")
    config.overlay_screens.append("tl_buttons")

    style.tl_overlay_style = Style(style.default)
    style.tl_overlay_style.size = 36
    style.tl_overlay_style.color = "#ffffff"
    style.tl_overlay_style.font = "translator/SourceHanSansCN-Regular.otf"
    style.tl_overlay_style.line_spacing = 4
    style.tl_overlay_style.outlines = [(2, "#000000aa", 0, 0)]

    def _tl_toggle():
        tl_engine.enabled = not tl_engine.enabled
        renpy.restart_interaction()

    def _tl_retranslate():
        sp = getattr(store, "_tl_sp", None)
        tx = getattr(store, "_tl_tx", None)
        if sp and tx:
            tl_engine.refresh(sp, tx)
            renpy.restart_interaction()


# ================================================================
# Toolbar buttons
# ================================================================

screen tl_buttons():
    if _tl_api_ok:
        fixed:
            xpos 1600
            ypos 1020
            hbox:
                spacing 6
                if tl_engine.enabled:
                    textbutton "隐藏译文" action Function(store._tl_toggle):
                        text_style "tl_btn_text"
                        style "tl_btn"
                else:
                    textbutton "显示译文" action Function(store._tl_toggle):
                        text_style "tl_btn_text"
                        style "tl_btn"
                if tl_engine.enabled:
                    textbutton "重新翻译" action Function(store._tl_retranslate):
                        text_style "tl_btn_text"
                        style "tl_btn"


init -95 python:
    style.tl_btn = Style(style.empty)
    style.tl_btn.xpadding = 10
    style.tl_btn.ypadding = 7
    style.tl_btn.xmargin = 0
    style.tl_btn.ymargin = 0

    style.tl_btn_text = Style(style.default)
    style.tl_btn_text.size = 24
    style.tl_btn_text.color = "#ffffff"
    style.tl_btn_text.hover_color = "#ffffff"
    style.tl_btn_text.selected_color = "#ffffff"
    style.tl_btn_text.insensitive_color = "#444444"
    style.tl_btn_text.outlines = [(1, "#000000cc", 0, 0)]
    style.tl_btn_text.font = "translator/SourceHanSansCN-Regular.otf"


# ================================================================
# History screen
# ================================================================

screen history():
    tag menu
    predict False

    use game_menu(_("History"), scroll=("vpgrid" if gui.history_height else "viewport"), yinitial=1.0):
        style_prefix "history"

        for h in _history_list:
            window:
                has fixed:
                    yfit True

                if h.who:
                    label h.who:
                        style "history_name"
                        substitute False
                        if "color" in h.who_args:
                            text_color h.who_args["color"]
                        if "outlines" in h.who_args:
                            text_outlines [(absolute(1), "#000", absolute(0), absolute(0))]

                $ what = renpy.filter_text_tags(h.what, allow=gui.history_allow_tags)
                text what:
                    substitute False

                if tl_engine.enabled:
                    $ tl = tl_engine.get(str(h.who) if h.who else "(Narrator)", h.what)
                    if tl and tl != "..." and not tl.startswith("[Error") and tl != "[Same as original]":
                        text tl:
                            style "history_tl"
                            substitute False

        if not _history_list:
            label _("The dialogue history is empty.")

    if _tl_api_ok:
        fixed:
            xpos 1600
            ypos 1020
            hbox:
                spacing 6
                if tl_engine.enabled:
                    textbutton "隐藏译文" action Function(store._tl_toggle):
                        text_style "tl_btn_text"
                        style "tl_btn"
                else:
                    textbutton "显示译文" action Function(store._tl_toggle):
                        text_style "tl_btn_text"
                        style "tl_btn"


init -94 python:
    style.history_tl = Style(style.history_text)
    style.history_tl.size = 20
    style.history_tl.color = "#444444"
    style.history_tl.font = "translator/SourceHanSansCN-Regular.otf"
    style.history_tl.ypos = 30
    style.history_tl.line_spacing = 2
