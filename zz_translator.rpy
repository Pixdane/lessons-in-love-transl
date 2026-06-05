## ============================================================
## Lessons in Love — LLM Translation Overlay
## Non-invasive: delete this file to restore original game.
## Keys: T=toggle translation, R=refresh current line
## ============================================================

init -100 python:
    import json, os, threading, time

    import renpy.store as store

    _TL_DIR = os.path.join(renpy.config.gamedir, "translator")
    _TL_CONFIG_PATH = os.path.join(_TL_DIR, "config.json")
    _TL_CACHE_PATH  = os.path.join(_TL_DIR, "cache.json")
    _TL_STATE_PATH  = os.path.join(_TL_DIR, "state.json")
    os.makedirs(_TL_DIR, exist_ok=True)

    def _tl_load_json(path, default=None):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}

    def _tl_save_json(path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    _tl_config = _tl_load_json(_TL_CONFIG_PATH, {})
    _tl_cache  = _tl_load_json(_TL_CACHE_PATH, {})
    _tl_state  = _tl_load_json(_TL_STATE_PATH, {"enabled": True})

init -99 python:
    class TranslatorEngine:
        def __init__(self):
            self._lock = threading.Lock()
            self._pending = {}
            self._done = {}

        @property
        def enabled(self):
            return _tl_state.get("enabled", True)

        @enabled.setter
        def enabled(self, val):
            _tl_state["enabled"] = val
            _tl_save_json(_TL_STATE_PATH, _tl_state)

        def cache_key(self, speaker, text):
            clean = text.replace("{i}", "").replace("{/i}", "")\
                        .replace("{b}", "").replace("{/b}", "").strip()
            return "{}|||{}".format(speaker or "NARRATOR", clean)

        def get(self, speaker, text):
            if not self.enabled:
                return ""
            if not text or not text.strip():
                return ""
            stripped = text.replace("{i}", "").replace("{/i}", "")\
                           .replace("{b}", "").replace("{/b}", "").strip()
            if len(stripped) <= 1:
                return ""
            key = self.cache_key(speaker, text)
            if key in _tl_cache:
                return _tl_cache[key]
            with self._lock:
                if key in self._done:
                    val = self._done.pop(key)
                    _tl_cache[key] = val
                    self._save_cache_deferred()
                    return val
                if key not in self._pending:
                    self._pending[key] = True
                    t = threading.Thread(
                        target=self._translate_bg,
                        args=(speaker, text, key),
                        daemon=True,
                    )
                    t.start()
                    return "..."
            return "..."

        def refresh(self, speaker, text):
            key = self.cache_key(speaker, text)
            _tl_cache.pop(key, None)
            with self._lock:
                self._done.pop(key, None)
                self._pending.pop(key, None)
            _tl_save_json(_TL_CACHE_PATH, _tl_cache)
            self.get(speaker, text)

        def refresh_current(self):
            speaker = getattr(store, "_tl_speaker", None)
            text = getattr(store, "_tl_text", None)
            if text:
                self.refresh(speaker, text)

        def _translate_bg(self, speaker, text, key):
            try:
                result = self._call_api(speaker, text)
                with self._lock:
                    self._done[key] = result
            except Exception:
                with self._lock:
                    self._done[key] = "[Translation failed]"
            finally:
                with self._lock:
                    self._pending.pop(key, None)

        def _call_api(self, speaker, text):
            api_cfg = _tl_config.get("api", {})
            base_url = api_cfg.get("base_url", "https://api.deepseek.com/v1")
            api_key  = api_cfg.get("api_key", "")
            model    = api_cfg.get("model", "deepseek-chat")
            max_tok  = api_cfg.get("max_tokens", 1024)
            temp     = api_cfg.get("temperature", 0.3)
            system_prompt = _tl_config.get("system_prompt", "")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Speaker: {}\n\nTranslate:\n{}".format(speaker or "(Narrator)", text)},
            ]

            import requests as _requests
            resp = _requests.post(
                "{}/chat/completions".format(base_url.rstrip("/")),
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tok,
                    "temperature": temp,
                    "stream": False,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

        _save_debounce = 0.0

        def _save_cache_deferred(self):
            now = time.time()
            if now - self._save_debounce > 2.0:
                self._save_debounce = now
                _tl_save_json(_TL_CACHE_PATH, _tl_cache)

    tl_engine = TranslatorEngine()

init -98 python:
    _orig_character_call = Character.__call__

    def _tl_patched_call(self, what, interact=True, _call_done=True, multiple=None, **kwargs):
        # Process who/what the same way the original does,
        # so cache keys match history entries exactly.
        who_raw = self.name if hasattr(self, "name") and self.name else None
        what_processed = self.prefix_suffix("what", self.what_prefix, what, self.what_suffix)
        if who_raw is not None:
            who_processed = self.prefix_suffix("who", self.who_prefix, who_raw, self.who_suffix)
            store._tl_speaker = who_processed
        else:
            store._tl_speaker = "(Narrator)"
        store._tl_text = what_processed
        store._tl_time = time.time()
        return _orig_character_call(self, what, interact=interact,
                                    _call_done=_call_done, multiple=multiple, **kwargs)

    Character.__call__ = _tl_patched_call


init -97 python:
    def _tl_overlay_func(st, at):
        text = getattr(store, "_tl_text", None)
        speaker = getattr(store, "_tl_speaker", None)
        if not text or not tl_engine.enabled:
            return renpy.text.text.Text(""), None
        result = tl_engine.get(speaker, text)
        if not result:
            return renpy.text.text.Text(""), None
        if result == "...":
            txt = renpy.text.text.Text("...", style="tl_wait_style")
            return txt, 0.3
        txt = renpy.text.text.Text(result, style="tl_text_style")
        return txt, None


screen tl_overlay():
    if tl_engine.enabled:
        add DynamicDisplayable(_tl_overlay_func):
            xpos 402
            ypos 790
            xmaximum 1116


init -96 python:
    config.overlay_screens.append("tl_overlay")

    style.tl_text_style = Style(style.default)
    style.tl_text_style.size = 24
    style.tl_text_style.color = "#888888"
    style.tl_text_style.font = "YuGothM.ttc"
    style.tl_text_style.line_spacing = 2

    style.tl_wait_style = Style(style.tl_text_style)
    style.tl_wait_style.color = "#666666"
    style.tl_wait_style.italic = True


init -95 python:
    def _tl_toggle():
        tl_engine.enabled = not tl_engine.enabled
        renpy.notify("Translation: {}".format("ON" if tl_engine.enabled else "OFF"))

    def _tl_refresh():
        if tl_engine.enabled:
            tl_engine.refresh_current()
            renpy.notify("Retranslating...")

    config.keymap["toggle_translation"] = ["t"]
    config.keymap["refresh_translation"] = ["shift_T", "r"]
    config.underlay.append(
        renpy.Keymap(
            toggle_translation=_tl_toggle,
            refresh_translation=_tl_refresh,
        )
    )

# ================================================================
# History screen override — shows translation in backlog
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

                # ---- Translation below original ----
                if tl_engine.enabled:
                    $ tl = tl_engine.get(str(h.who) if h.who else "(Narrator)", h.what)
                    if tl and tl != "..." and tl != "[Translation failed]":
                        text tl:
                            style "history_tl"
                            substitute False

        if not _history_list:
            label _("The dialogue history is empty.")


init -94 python:
    style.history_tl = Style(style.history_text)
    style.history_tl.size = 20
    style.history_tl.color = "#777777"
    style.history_tl.ypos = 28
    style.history_tl.line_spacing = 1
