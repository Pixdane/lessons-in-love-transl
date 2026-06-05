# Lessons in Love — LLM Translation Layer

非侵入式翻译层，不加一个文件到游戏目录即可运行。删除即恢复原样。

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    Ren'Py 游戏引擎                        │
│                                                         │
│  Character.__call__ ──patch──▶ 拦截原文 + 说话人          │
│         │                                     │         │
│         ▼                                     ▼         │
│    say 屏幕                          store._tl_text     │
│  (原文显示)                           store._tl_speaker  │
│         │                                     │         │
│         ▼                                     ▼         │
│  tl_overlay 屏幕 ◀── DynamicDisplayable ── tl_engine     │
│  (翻译显示)          每 300ms 轮询          │            │
│                                             │            │
│  history 屏幕 ◀──── tl_engine.get() ────────┘            │
│  (历史翻译显示)                                          │
│                                             │            │
│                           ┌─────────────────┴──────┐     │
│                           │   TranslatorEngine      │     │
│                           │                        │     │
│                           │  cache.json  ◀─ 本地缓存 │     │
│                           │  DeepSeek API ◀─ LLM   │     │
│                           └────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

## 文件结构

```
lessons-in-love-transl/
├── zz_translator.rpy          # 主模块，放入 game/ 目录
└── translator/
    ├── config.json            # API 密钥 + 翻译指南 + 角色档案
    ├── cache.json             # 翻译缓存（自动生成）
    └── state.json             # 运行状态（开关/版本，自动生成）
```

## 技术实现

### 文本拦截

Monkey-patch `Character.__call__`，这是 Ren'Py 中所有角色说话的唯一入口。

```python
_orig_character_call = Character.__call__

def _tl_patched_call(self, what, ...):
    # 仿照原始逻辑，对 who 和 what 应用 prefix_suffix
    # 确保存入的文本与 history 中的一致
    what_processed = self.prefix_suffix("what", self.what_prefix, what, self.what_suffix)
    store._tl_text = what_processed
    store._tl_speaker = who_processed or "(Narrator)"
    return _orig_character_call(self, what, ...)

Character.__call__ = _tl_patched_call
```

调用 `prefix_suffix` 是为了保证缓存 key 与 history 中存储的文本完全一致——history 里的 `h.what` 和 `h.who` 也是经过 `prefix_suffix` 处理后的值。

### 翻译引擎

`TranslatorEngine` 是一个单例，管理翻译生命周期：

```
get(speaker, text)
  ├─ cache.json 命中 → 直接返回
  ├─ _done 中有结果 → 提升到 cache.json，返回
  ├─ _pending 中正在翻译 → 返回 "..."（等待中）
  └─ 未命中且未排队 → 启动后台线程 → 返回 "..."
```

后台线程 `_translate_bg`：
- 调用 DeepSeek API（非流式，一次返回完整结果）
- 完成后将结果放入 `self._done` 字典
- 下次 `get()` 调用时提升到 cache.json

### 实时显示

使用 Ren'Py 的 `DynamicDisplayable` 实现轮询显示：

```python
def _tl_overlay_func(st, at):
    result = tl_engine.get(speaker, text)
    if result == "...":
        return Text("..."), 0.3   # 300ms 后重试
    return Text(result), None      # 完成，停止轮询
```

`DynamicDisplayable` 是 Ren'Py 原生机制，由引擎每帧调用，不需要手动 timer 或 `restart_interaction`。

### 历史记录

覆写 `screen history()` —— 因为 `zz_translator.rpy` 按字母序在 `screens.rpy` 之后加载，同名屏幕后者覆盖前者。

原始屏幕完整保留，只在每条对话原文下方追加翻译行：

```renpy
text what:           # 原文（原有逻辑完全不变）
    substitute False

if tl_engine.enabled:
    $ tl = tl_engine.get(str(h.who) if h.who else "(Narrator)", h.what)
    if tl and tl != "..." and tl != "[Translation failed]":
        text tl:      # 翻译（新增）
            style "history_tl"
            substitute False
```

## DeepSeek 缓存机制

### 工作原理

DeepSeek 提供自动上下文硬盘缓存（KV Cache）。两个请求的 `messages` 数组从前缀开始比对，相同的部分从硬盘直接读取中间计算结果，跳过重复计算。

我们的 prompt 结构天然最优：

```
messages[0] system  ← 翻译指南 + 30 角色档案 (~2500 tokens)
                       永远不变 → 永远命中缓存 → 0.1 元/百万 token
messages[1] user    ← "Speaker: Ami\n\nTranslate:\nI love you!" (~30 tokens)
                       每次不同 → 1 元/百万 token
```

实际成本：每次翻译基本只付 30 token 的钱。

### 命中验证

API 返回的 `usage` 字段包含缓存命中统计：

```json
{
  "prompt_cache_hit_tokens":  2500,   // 命中 2500 token
  "prompt_cache_miss_tokens": 30      // 新计算 30 token
}
```

### 设计原则

**稳定内容放前面，变化内容放后面。**

由于 DeepSeek 缓存使用前缀匹配，所有可变信息必须放在 messages 数组的最后。如果第一条消息就包含变化内容（如随机的 request ID），整个缓存将失效。

## 翻译指南设计

### 角色档案

从 `definitions.rpy` 中提取了全部 30+ 角色的名称。通过抽样阅读各角色的对话脚本（AmiEvents.rpy、MayaEvents.rpy 等），总结了每个角色的说话风格和性格关键词。

档案格式：

```
Ami: Female, warm and affectionate. Calls Sensei by pet names.
      Speech: sweet, playful, uses ~ to mark warmth.

Maya: Female, cold and sarcastic, philosophical. Shrine maiden.
      Speech: cutting, intellectual, formal register even when insulting.
```

### 文风定位

- **目标风格**：有文学野心的轻小说中文
- **叙述者独白**：保留哲学性、自嘲、暗喻的语言密度，翻译成自然流畅的书面中文叙事
- **角色对话**：遵循 Galgame 中文约定，口语化，保留语气词（呢、哦、啊、嘛、吧）
- **格式标记**：`{i}...{/i}` 和 `{b}...{/b}` 必须原样保留，放置于对应强调词周围

### 系统 Prompt 结构

1. 角色定位（你是文学翻译）
2. 翻译原则（叙述声音、对话风格、标记保留）
3. 质量约束（不翻译人名、不过度形式化、不添加注释）
4. 输出格式（仅输出译文，无包装）

完整 prompt 见 `translator/config.json` 的 `system_prompt` 字段。

## 快捷键

| 按键 | 功能 |
|------|------|
| `T` | 切换翻译层开关（通知栏显示 ON/OFF） |
| `R` | 刷新当前行的翻译（清除缓存 + 重新调用 API） |

## 配置

编辑 `translator/config.json`：

```json
{
  "api": {
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "YOUR_DEEPSEEK_API_KEY_HERE",
    "model": "deepseek-chat",
    "max_tokens": 1024,
    "temperature": 0.3
  }
}
```

支持任何 OpenAI 兼容 API（Ollama、LM Studio、OpenRouter 等），只需修改 `base_url` 和 `model`。

## 部署

```bash
# 1. 解除 macOS Gatekeeper 隔离
xattr -dr com.apple.quarantine \
  "/Volumes/Yuean Jinn/Games/LessonsInLove0.58.0.app"

# 2. 符号链接（推荐 — 方便修改）
GAME_DIR="/Volumes/Yuean Jinn/Games/LessonsInLove0.58.0.app/Contents/Resources/autorun/game"

ln -s /Users/pixdane/Documents/Vibe/lessons-in-love-transl/zz_translator.rpy \
      "$GAME_DIR/zz_translator.rpy"
ln -s /Users/pixdane/Documents/Vibe/lessons-in-love-transl/translator \
      "$GAME_DIR/translator"

# 3. 填入 API Key
# 编辑 translator/config.json，替换 YOUR_DEEPSEEK_API_KEY_HERE

# 4. 启动游戏，按 T 开启翻译
```

如果符号链接不生效（某些 Ren'Py 版本不跟随 symlink），改用复制：

```bash
cp zz_translator.rpy "$GAME_DIR/"
cp -r translator "$GAME_DIR/"
```

## 删除

删除游戏目录下的 `zz_translator.rpy` 和 `translator/` 即可完全恢复原版。不影响任何原有文件。

## 局限性 & 未来改进

**当前版本的局限性：**

- 非流式 API 调用（后台线程等待完整返回）。翻译过程中游戏可能短暂显示 "..."，待结果返回后刷新显示
- 首次遇到未缓存文本时，翻译有 1-3 秒延迟
- History 屏幕大量未缓存条目时可能同时触发多个后台请求
- 文本中的 Ren'Py 变量插值（`[var]`）已在拦截时完成替换，缓存 key 是基于插值后的文本

**可能的改进方向：**

- SSE 流式翻译，逐 token 打字机效果
- 批量翻译（一次发 6-9 句，利用上下文提升质量）
- 请求队列（限制并发 API 调用数）
- 预翻译模式（启动时扫描全部脚本，后台填充缓存）
- 翻译校对 pass（第一次翻译后用 LLM 自审润色）
