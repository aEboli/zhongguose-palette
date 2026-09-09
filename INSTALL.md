# 安装与跨模型使用

[README](README.md) 里有精简版安装说明。这份文件讲得更细，包括每种宿主的差异、
降级后会丢什么、以及排错。

## 两层结构

- **能力层**：`scripts/` + `references/`。纯 Python 3.10 标准库 + JSON + Markdown，
  不依赖任何模型。谁都能跑。
- **触发层**：`SKILL.md`（Claude / Codex 的 skill 约定）、`agents/openai.yaml`
  （Codex 界面元数据）。只有这一层是特定于宿主的。

换宿主时只换触发层，色库、评分、别名、白话表一行都不用动。

## 依赖

Python **3.10+**（用到 `X | None` 类型写法）。无第三方包。Windows / macOS / Linux 通用。

确认环境：

```bash
python --version          # 应 ≥ 3.10
python scripts/selftest.py   # 应输出「全部通过」
```

`selftest.py` 共 711 项断言，覆盖色彩数学、色库完整性、别名文化校正、白话映射、
术语泄露、对比度闸门、暗底安全区、交接文件字段、README 里写出来的每条命令。
跑一次约需 1~2 分钟（其中一组会真的启动子进程跑 CLI）。

## Claude Code

用户级（所有项目可用）：

```bash
git clone https://github.com/aEboli/zhongguose-palette.git
cp -r zhongguose-palette ~/.claude/skills/
```

Windows PowerShell：

```powershell
git clone https://github.com/aEboli/zhongguose-palette.git
Copy-Item -Recurse zhongguose-palette "$env:USERPROFILE\.claude\skills\"
```

项目级（只在当前项目可用）：

```bash
mkdir -p .claude/skills
cp -r zhongguose-palette .claude/skills/
```

新开会话即可用。用户说「配个中国风的颜色」时会自动触发，也可以
`/zhongguose-palette` 手动调用。

装好之后最短的一条路是把用户原话直接交给 `ask`：

```bash
python scripts/palette.py ask "茶叶小店的网站，安静一点"
```

不需要先知道场景名、氛围名或旗标。

**注意**：改了源目录要重新拷一次，两处不会自动同步。开发时可以改用符号链接：

```bash
ln -s "$(pwd)/zhongguose-palette" ~/.claude/skills/zhongguose-palette
```

```powershell
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\zhongguose-palette" -Target (Resolve-Path .\zhongguose-palette)
```

## Codex / OpenAI CLI

```bash
git clone https://github.com/aEboli/zhongguose-palette.git
cp -r zhongguose-palette ~/.codex/skills/
```

`agents/openai.yaml` 提供界面显示名、简介与默认提示语；Codex 会读 `SKILL.md` 正文。
默认提示语里已经写明「把用户原话原样交给 `ask`，不要自己先翻成场景名」。

## Cursor / Cline / Windsurf 等编辑器 Agent

把整个文件夹放进项目，然后在项目规则文件里指一下：

```markdown
配色任务读 zhongguose-palette/SKILL.md，并运行其中的 scripts/palette.py。
把用户原话交给 `palette.py ask "<原话>"`，不要自己先翻成场景名或旗标。
对用户不要说主场/结构/点缀/五行/彩度/氛围/场景这些内部词。
```

规则文件位置：Cursor 用 `.cursor/rules/`，Cline 用 `.clinerules`，
Windsurf 用 `.windsurfrules`，其余同理。

## ChatGPT 网页版 / GPTs

没有文件系统，跑不了脚本，改成「知识库 + 规则」用法：

1. 建一个 GPT，把这些文件传进 Knowledge：
   - `references/colors.json`（色库，必传）
   - `references/curated.json`（20 套手选方案，必传）
   - `references/aliases.json`（别名，必传）
   - `references/rules.md`、`references/culture.md`（讲道理时用，可选）
2. 把 `SKILL.md` 的「说话的方式」与「三条不能破的」两节粘进 Instructions。
3. 删掉 Instructions 里所有 `python scripts/...` 命令，换成一句：
   「颜色只能从 colors.json 里检索，禁止发明 hex；优先使用 curated.json 里的手选方案。」

**降级会丢什么**（都在脚本里）：评分、色差计算、对比度闸门、建议铺色面积、
白话解析、场景色族检查、撞车检查、交接文件。质量会明显下降。

补偿办法：让它优先直接引用 `curated.json` 的 20 套手选方案，不要现场配色。

想保住质量就用带代码解释器的版本，把 `scripts/` 一起打包上传，然后让它跑：

```
python palette.py ask "茶叶小店的网站，安静一点"
```

## 只当命令行工具用

不接任何模型：

```bash
git clone https://github.com/aEboli/zhongguose-palette.git
cd zhongguose-palette
python scripts/selftest.py
python scripts/palette.py ask "茶叶小店的网站，安静一点"
```

完整命令说明见 [README 的使用一节](README.md#使用)。

## 当 Python 库用

```python
import sys
sys.path.insert(0, "zhongguose-palette/scripts")

from engine import Catalog, generate, tokens, css_vars, as_dict

cat = Catalog()
pal = generate(cat, scene="青花", media="ui", n=1)[0]
print(pal.dominant.name, pal.dominant.hex)   # 雪白 #fffef9
print(css_vars(tokens(cat, pal)))
print(as_dict(pal, tokens(cat, pal)))        # 完整 JSON，可喂给任意模型
```

走白话入口并产出交接文件：

```python
import sys
from pathlib import Path
sys.path.insert(0, "zhongguose-palette/scripts")

from engine import Catalog, generate
from vernacular import Vernacular
import handoff as ho

cat = Catalog()
it = Vernacular().resolve("券商的后台系统，要稳重可信", catalog=cat)
print(it.echo)      # ['网页界面', '石青深底上一枚金线徽章']
print(it.unheard)   # [] —— 有接不住的词会列在这里

pal = generate(cat, scene=it.scene, mood=it.mood, media=it.media, dark=it.dark, n=1)[0]
ho.write(ho.build(cat, pal), Path(".palette"))
```

给模型喂 JSON 时用 `as_dict()`，它包含色名、hex、评分、五行关系、建议铺色面积。
给其他设计工具用 `handoff.build()`，字段说明见 [references/handoff.md](references/handoff.md)。

## 只要色库，不要技能

`references/colors.json` 是自带说明的独立数据文件：526 条，每条含 hex、RGB、CMYK、
HSL、HSV、Lab、LCH、对比度、APCA、色系、五行、四季、明度带、彩度带、冷暖、
物象来源、设计角色、三种色盲模拟值。任何语言都能读。

`references/source.json` 是官网原件，未加工。

另外两个数据文件也可独立使用：

- `references/aliases.json` —— 144 条经典色名 → 库内色的映射，含文化校正理由
- `references/vernacular.json` —— 535 条白话线索词 → 场景/氛围/媒材的映射表

## 排错

### Windows 中文显示成乱码

```bash
# Git Bash / macOS / Linux
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
```

```powershell
# PowerShell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```

```cmd
:: cmd.exe
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
```

### 色条显示成乱码或方块

终端不支持 24 位真彩。加 `--no-bar` 关掉色条，或设 `NO_COLOR=1` 全局关闭颜色。
脚本会自动降级到 256 色，再降到无色表格。

### `--scene` 报 invalid choice

场景名必须是这 12 个之一：故宫、青花、水墨、敦煌、宋瓷、唐三彩、江南、漆器、
年画、祭天、王府、补服。

**但一般不该手写 `--scene`** —— 用 `ask "<用户原话>"`，它会自己判断。

### `--seed` 报「色库里没有」

种子色必须是库内色名、拼音或 hex。报错会附最近邻建议。
这是故意的：早先解析失败会静默回落到默认方案，用户以为品牌色生效了，其实没进去。

### 找不到 `.palette/handoff.json`

`pick` 默认写到当前工作目录下的 `.palette/`（已进 `.gitignore`）。
用 `--out <目录>` 指定别处。

### `selftest.py` 有失败项

先看失败的是哪一组：

- `白话映射` —— 改了 `vernacular.json` 的词表但没同步 `vernacular_cases.jsonl`
- `术语泄露` —— 给用户看的输出里出现了内部词，通常是新增文案时带进去的
- `README 命令应可跑` —— 文档里写了 CLI 没实现的旗标
- `色库 526 条` —— `colors.json` 被改动了

改分类或评分后原有断言必须仍通过，不要为了让测试变绿而放宽断言。
