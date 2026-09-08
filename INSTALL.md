# 安装与跨模型使用

这个技能分两层：

- **能力层**：`scripts/` + `references/`。纯 Python 3.10 标准库 + JSON + Markdown，不依赖任何模型。谁都能跑。
- **触发层**：`SKILL.md`（Claude / Codex 的 skill 约定）、`agents/openai.yaml`（Codex 界面元数据）。只有这一层是特定于宿主的。

换模型时只换触发层，色库、评分、别名、理论一行都不用动。

## Claude Code

本机已装到用户级：`~/.claude/skills/zhongguose-palette/`。新开会话即可用。

```bash
# 用户级（所有项目可用）
cp -r zhongguose-palette ~/.claude/skills/

# 或项目级
mkdir -p .claude/skills && cp -r zhongguose-palette .claude/skills/
```

用户说「配个中国风的颜色」时会自动触发；也可以 `/zhongguose-palette` 手动调用。

改了源目录后要重新拷一次，两处不会自动同步。

## Codex / OpenAI CLI

本机已装到 `~/.codex/skills/zhongguose-palette/`。

```bash
cp -r zhongguose-palette ~/.codex/skills/
```

`agents/openai.yaml` 提供界面显示名与默认提示语，Codex 会读 `SKILL.md` 正文。

## ChatGPT 网页版 / GPTs

没有文件系统，所以不能跑脚本。改成「知识库 + 规则」用法：

1. 建一个 GPT，把这些文件传进 Knowledge：
   - `references/colors.json`（色库，必传）
   - `references/curated.json`（20 套手选方案，必传）
   - `references/aliases.json`（别名，必传）
   - `references/theory.md`、`references/culture.md`（可选，讲道理时用）
2. 把 `SKILL.md` 的「铁律」和「输出格式」两节粘到 Instructions。
3. 删掉 Instructions 里所有 `python scripts/...` 命令，替换成一句：
   「颜色只能从 colors.json 里检索，禁止发明 hex；优先使用 curated.json 里的手选方案。」

没有脚本就没有评分和面积计算，质量会下降。想保住质量，用带代码解释器的版本，把 `scripts/` 一起打包上传，然后让它 `python palette.py generate --scene 青花`。

## Cursor / Windsurf / Cline 等编辑器 Agent

把整个文件夹放进项目，然后在项目规则文件里指一下：

```markdown
配色任务读 zhongguose-palette/SKILL.md，并运行其中的 scripts/palette.py。
```

Cursor 用 `.cursor/rules/`，Cline 用 `.clinerules`，其余同理。

## API / 自己的程序

不经过任何 Agent，直接当 Python 库：

```python
import sys
sys.path.insert(0, "zhongguose-palette/scripts")
from engine import Catalog, generate, tokens, css_vars, as_dict

cat = Catalog()
pal = generate(cat, scene="青花", n=1)[0]
print(pal.dominant.name, pal.dominant.hex)   # 雪白 #fffef9
print(css_vars(tokens(cat, pal)))
print(as_dict(pal, tokens(cat, pal)))        # 可直接喂给任意模型
```

给模型喂 JSON 时用 `as_dict()`，它包含色名、hex、评分、五行关系、建议像素面积。

## 只要色库，不要技能

`references/colors.json` 是自带说明的独立数据文件：526 条，每条含 hex、RGB、CMYK、HSL、HSV、Lab、LCH、对比度、APCA、色系、五行、四季、明度带、彩度带、冷暖、物象来源、设计角色、三种色盲模拟值。任何语言都能读。

`references/source.json` 是官网原件，未加工。

## 依赖

Python 3.10+（用到 `X | None` 类型写法）。无第三方包。Windows / macOS / Linux 通用。

Windows 上若中文显示成乱码，先设：

```bash
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
```
