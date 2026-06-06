# Lessons in Love — LLM Translation Layer

非侵入式翻译层。加一个文件到游戏目录即可运行，删除即恢复原样。

## 架构

```
Ren'Py 游戏引擎
  │
  └─ renpy.exports.say hook
       │
       ├─ 英文模式 → 原文直通
       └─ 中文模式 → 替换为缓存译文
              │
              ├─ 已缓存 → 直接显示中文
              └─ 未缓存 → 先显示英文
                            │
                    后台线程调 API
                            │
                    译文就绪 → restart_interaction
                            │
                            └─ 翻转为中文
```

翻译完成后文本会**原地翻转**——英文出现 1-3 秒后自动变成中文，不需要重新触发对话。

## 快捷键 → 按钮

弃用了键盘快捷键，改为 UI 按钮：

| 按钮 | 功能 |
|------|------|
| `中` / `EN` | 中英文切换，切换时立即刷新当前文本 |
| `↻` | 重翻当前行（清除缓存 + 重新调 API） |

按钮位于屏幕右下角，hover 时高亮，不干扰游戏画面。

## 部署

```bash
# 1. 配置 API Key
cp translator/config.example.json translator/config.json
# 编辑 config.json，将 YOUR_DEEPSEEK_API_KEY_HERE 替换为真实 key

# 2. 部署到游戏目录（二选一）
GAME_DIR="/Volumes/Yuean Jinn/Games/LessonsInLove0.58.0.app/Contents/Resources/autorun/game"

# 方式 A：符号链接（推荐，方便修改）
ln -s /Users/pixdane/Documents/Vibe/lessons-in-love-transl/zz_translator.rpy "$GAME_DIR/"
ln -s /Users/pixdane/Documents/Vibe/lessons-in-love-transl/translator        "$GAME_DIR/"

# 方式 B：复制
cp zz_translator.rpy "$GAME_DIR/"
cp -r translator        "$GAME_DIR/"

# 3. 启动游戏，点击右下角「中」按钮开启翻译
```

## 删除

删除游戏目录下的 `zz_translator.rpy` 和 `translator/` 即可完全恢复原版。
