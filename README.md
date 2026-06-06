# Lessons in Love — LLM Translation Layer

非侵入式翻译层。将 `zz_translator.rpy` 放入游戏 `game/` 目录即可运行，删除即恢复原版。

## 特性

**核心功能**
- 实时翻译叠加：中文覆盖在英文对话区域上方，思源黑体渲染，白字 + 暗色描边
- 中英切换：右下角「显示译文」/「隐藏译文」按钮，一键开关
- 重新翻译：对当前句子不满意时点「重新翻译」清缓存重调 API
- 历史记录：对话历史里同样显示中文翻译 + 切换按钮

**翻译引擎**
- 请求队列：单 worker 线程串行处理，限制并发 API 调用数
- 持久化缓存：以 `speaker|||text` 为 key 存入 `cache.json`，随 repo 分发可共享翻译进度。清空文件为 `{}` 即可全部重新翻译
- API 兼容：支持 DeepSeek、OpenAI 及任何 OpenAI 兼容 API
- 术语表注入：`glossary.json` 中定义的术语自动注入 system prompt，保证人名、地名翻译一致
- 后处理：自动剥离 LLM 偶尔输出的说话人前缀、引号、`译文：` 等多余格式

**DeepSeek 缓存机制**

system prompt（翻译指南 + 术语表 ~2500 tokens）永远不变 → 命中 DeepSeek 硬盘缓存 → 每次翻译实际只计费约 30 tokens 的用户输入。

## 文件结构

```
lessons-in-love-transl/
├── zz_translator.rpy               # 主模块，放入 game/ 目录
├── README.md
└── translator/
    ├── config.example.json         # 配置模板
    ├── config.json                 # API 密钥 + 翻译指南 + 角色档案
    ├── cache.json                  # 翻译缓存（自动生成，可共享）
    ├── state.json                  # 开关状态（自动生成）
    ├── glossary.json               # 术语表
    └── SourceHanSansCN-Regular.otf # 思源黑体 CN Regular
```

## 按钮

| 按钮 | 位置 | 功能 |
|------|------|------|
| 显示译文 / 隐藏译文 | 对话框 + 历史记录右下角 | 切换翻译开关 |
| 重新翻译 | 对话框右下角 | 清除当前句缓存 + 重调 API |

## 部署

```bash
# 1. 配置 API Key
cp translator/config.example.json translator/config.json
# 编辑 config.json，替换 YOUR_DEEPSEEK_API_KEY_HERE

# 2. 部署到游戏目录
# macOS: GAME_DIR="Game.app/Contents/Resources/autorun/game"
# Windows / Linux: GAME_DIR="Game/game"
GAME_DIR="<your-game-directory>/game"
ln -s "$(pwd)/zz_translator.rpy" "$GAME_DIR/"
ln -s "$(pwd)/translator"        "$GAME_DIR/"

# 3. 启动游戏，点右下角「显示译文」
```

## 跨平台

`zz_translator.rpy` 零硬编码路径，所有文件引用相对于 `renpy.config.gamedir`。Ren'Py 7/8、Windows/macOS/Linux 均可运行。

## 删除

删除游戏目录下的 `zz_translator.rpy` 和 `translator/` 即可恢复原版。

## 缓存

`translator/cache.json` 以 `speaker|||text` 为 key 存储已翻译内容，随 repo 分发可共享翻译进度。如想全部重新翻译，清空文件内容为 `{}` 即可。

## 致谢

本项目由 [Codex](https://openai.com/codex) + DeepSeek V4 Pro 协作完成。翻译风格参考 [GalTransl](https://github.com/GalTransl/GalTransl) 的 Galgame 中文翻译规范。
