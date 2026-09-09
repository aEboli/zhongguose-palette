# 中国传统色调色板

从 [zhongguose.com](https://zhongguose.com/) 的 **526 个中国传统色**里选出一套能直接落地的配色。
既是 Claude Code / Codex 的 Skill，也是可独立运行的命令行工具和 Python 库。

**说人话就行**，不用先知道「故宫」「青花」「雅」「空灵」这些名字：

```bash
$ python scripts/palette.py ask "茶叶小店的网站，安静一点"

解读: 网页界面 · 素净耐看

方案 1 · 素净耐看
  页面背景     粉白     #fbf2e3   约 78%
  卡片与导航    瓦松绿    #6e8b74   约 19%
  主按钮      苋菜红    #a61b29   约 3%
  正文用    长石灰    #363433   对比 11.2:1 AAA
  来处      粉墙上的竹影，与一角花窗
  当心      竹青铺成块的时候要把颜色压住，让它像影子而不像叶子
  别做      不要把 苋菜红 铺成整条顶栏或大色带，它只有 3% 的量
```

不是「挑三个好看的 hex」，而是把颜色当角色分配：**来自色库、分得出主次、文字能读、文化上说得通**。

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [安装](#安装)
  - [Claude Code](#claude-code)
  - [Codex / OpenAI CLI](#codex--openai-cli)
  - [Cursor / Cline / Windsurf](#cursor--cline--windsurf)
  - [ChatGPT 网页版 / GPTs](#chatgpt-网页版--gpts)
  - [只当命令行工具用](#只当命令行工具用)
  - [只要色库，不要技能](#只要色库不要技能)
- [使用](#使用)
  - [白话入口 ask](#白话入口-ask)
  - [白话微调 tweak](#白话微调-tweak)
  - [定妆交接 pick](#定妆交接-pick)
  - [查色与吸附 info / snap / search](#查色与吸附-info--snap--search)
  - [已知术语时的直接入口 generate / complete](#已知术语时的直接入口-generate--complete)
  - [预览与自检 preview / selftest](#预览与自检-preview--selftest)
  - [命令总表](#命令总表)
- [能用在 UI/UX 吗](#能用在-uiux-吗)
- [和其他设计技能配合](#和其他设计技能配合)
- [图表用色](#图表用色)
- [当 Python 库用](#当-python-库用)
- [创建思路](#创建思路)
- [数据与理论来源](#数据与理论来源)
- [文件结构](#文件结构)
- [铁律](#铁律)
- [许可](#许可)

---

## 它解决什么问题

让模型配中国风颜色，通常会遇到五个坑：

| 坑 | 表现 | 这里怎么做 |
| --- | --- | --- |
| 编造色值 | 输出「中国红 `#C8161D`」这种查无此色的 hex | 只从 526 色里取，输出必带中文色名 + 拼音 |
| 三色等权 | 主次点缀一样响，像广告布 | 按响度派角色，铺满的那层强制安静 |
| 面积当比例 | 把高彩点缀真铺成一整条色带 | 按感知能量反推建议铺色面积，点缀通常只有 2~5% |
| 文化错配 | 「石青」给成薄荷绿、故宫配色出现品红 | 144 条别名做文化校正，场景限定色相窗口 |
| 要先学术语 | 得先知道「故宫 / 青花 / 雅 / 空灵」才能开口 | `ask` 吃一句人话，535 条线索词 + 63 条回归用例兜住 |

具体能力：

- **12 个场景**：故宫、青花、水墨、敦煌、宋瓷、唐三彩、江南、漆器、年画、祭天、王府、补服
- **7 种氛围**：雅、艳、古朴、清冷、浓烈、空灵、市井（内部参数，不要求用户知道）
- **4 种媒材**：UI、海报/插画、服装、空间（各有不同硬约束）
- **20 套手选方案**：经过文化校对，与算法方案同场评分排序
- **暗色模式**：深底做场，不是把浅色方案整页反相
- **别名解析**：石青、玄色、胭脂、竹青、天青、黛、漆黑、墨色、中国红…告诉你库内对应哪一色
- **交接合同**：一条命令产出 `handoff.json` + `palette.css`，供其他设计技能读
- **711 项回归测试**：色彩数学、色库完整性、白话映射、术语泄露、对比度闸门

---

## 安装

需要 **Python 3.10+**（用到 `X | None` 类型写法），**无第三方依赖**。Windows / macOS / Linux 通用。

这个技能分两层：

- **能力层**：`scripts/` + `references/`。纯标准库 + JSON + Markdown，不绑任何模型。
- **触发层**：`SKILL.md`（Claude / Codex 约定）、`agents/openai.yaml`（Codex 界面元数据）。

换宿主时只换触发层，色库、评分、别名、白话表一行都不用动。

### Claude Code

用户级安装（所有项目可用）：

```bash
git clone https://github.com/aEboli/zhongguose-palette.git
cp -r zhongguose-palette ~/.claude/skills/
```

Windows PowerShell：

```powershell
git clone https://github.com/aEboli/zhongguose-palette.git
Copy-Item -Recurse zhongguose-palette "$env:USERPROFILE\.claude\skills\"
```

项目级安装（只在当前项目可用）：

```bash
mkdir -p .claude/skills
cp -r zhongguose-palette .claude/skills/
```

新开会话即可用。用户说「配个中国风的颜色」时会自动触发，也可以 `/zhongguose-palette` 手动调用。

改了源目录要重新拷一次，两处不会自动同步。

### Codex / OpenAI CLI

```bash
git clone https://github.com/aEboli/zhongguose-palette.git
cp -r zhongguose-palette ~/.codex/skills/
```

`agents/openai.yaml` 提供界面显示名与默认提示语，Codex 会读 `SKILL.md` 正文。

### Cursor / Cline / Windsurf

把整个文件夹放进项目，然后在项目规则文件里指一下：

```markdown
配色任务读 zhongguose-palette/SKILL.md，并运行其中的 scripts/palette.py。
把用户原话交给 `palette.py ask "<原话>"`，不要自己先翻成场景名。
```

Cursor 用 `.cursor/rules/`，Cline 用 `.clinerules`，Windsurf 用 `.windsurfrules`，其余同理。

### ChatGPT 网页版 / GPTs

没有文件系统，跑不了脚本，改成「知识库 + 规则」用法：

1. 建一个 GPT，把这些文件传进 Knowledge：
   - `references/colors.json`（色库，必传）
   - `references/curated.json`（20 套手选方案，必传）
   - `references/aliases.json`（别名，必传）
   - `references/rules.md`、`references/culture.md`（讲道理时用）
2. 把 `SKILL.md` 的「说话的方式」「三条不能破的」两节粘进 Instructions。
3. 删掉 Instructions 里所有 `python scripts/...` 命令，换成一句：
   「颜色只能从 colors.json 里检索，禁止发明 hex；优先使用 curated.json 里的手选方案。」

没有脚本就没有评分、面积计算和对比度闸门，质量会明显下降。想保住质量，用带代码解释器的版本，把 `scripts/` 一起打包上传，然后让它跑 `python palette.py ask "..."`。

### 只当命令行工具用

不接任何模型，直接跑：

```bash
git clone https://github.com/aEboli/zhongguose-palette.git
cd zhongguose-palette
python scripts/selftest.py          # 确认环境没问题，应输出「全部通过」
python scripts/palette.py ask "茶叶小店的网站，安静一点"
```

Windows 上中文显示成乱码时先设：

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

终端色条需要 24 位真彩支持。不想要色条加 `--no-bar`；`NO_COLOR=1` 会全局关掉颜色。

### 只要色库，不要技能

`references/colors.json` 是自带说明的独立数据文件：526 条，每条含 hex、RGB、CMYK、HSL、HSV、Lab、LCH、对比度、APCA、色系、五行、四季、明度带、彩度带、冷暖、物象来源、设计角色、三种色盲模拟值。任何语言都能读。

`references/source.json` 是官网原件，未加工。

---

## 使用

工作目录是本技能根目录。下面所有命令都可直接复制运行。

### 白话入口 ask

**主入口。把用户的原话原样传进去**，不要自己先翻译成场景名或旗标。

```bash
python scripts/palette.py ask "茶叶小店的网站，安静一点"
python scripts/palette.py ask "博物馆海报要有分量"
python scripts/palette.py ask "做个后台仪表盘，深色模式"
python scripts/palette.py ask "过年活动页，要喜庆"
python scripts/palette.py ask "券商的后台系统，要稳重可信"
python scripts/palette.py ask "新中式民宿的墙面配色"
python scripts/palette.py ask "配个中国风的颜色"
python scripts/palette.py ask "用 #c1272d 做品牌色的落地页"
```

参数：

| 参数 | 作用 |
| --- | --- |
| `--n <数>` | 给几套，默认 2 |
| `--css` | 附 CSS 变量块 |
| `--no-bar` | 不画色条（写文件、CI、或终端不支持真彩时用） |

脚本先回读一行 `解读:`，说明它把这句话理解成了什么；有没听懂的词会单独报一行 `没接住:`，不会假装听懂。

```bash
$ python scripts/palette.py ask "要有仙气的网站" --no-bar --n 1
解读: 网页界面 · 素净耐看
      （mood 没说，用了缺省）
没接住: 仙气 —— 这几个词没对上任何取色规则，下面这几套没把它算进去。要紧的话换个说法再讲一次。
```

只看解析结果、不生成配色（调试用）：

```bash
python scripts/palette.py resolve "券商的后台系统，要稳重可信"
```

### 白话微调 tweak

用户的反馈也是原话传进去。`--mood` 传当前那套的档位，用于升降一档。

```bash
python scripts/palette.py tweak "太素了，再艳一点" --mood 雅
python scripts/palette.py tweak "太艳了，收一点" --mood 艳
python scripts/palette.py tweak "红少一点" --mood 艳
python scripts/palette.py tweak "改深色" --mood 雅
python scripts/palette.py tweak "加点金" --mood 空灵
python scripts/palette.py tweak "冷一点" --mood 雅
```

```bash
$ python scripts/palette.py tweak "太素了，再艳一点" --mood 雅 --no-bar --n 1
听到: 太素了，再艳一点
照做: 素艳 —— 雅 -> 艳

改后 1
  页面背景     酪黄     #f6dead   约 74%
  卡片与导航    茶褐     #5d3d21   约 21%
  主按钮      银朱     #f43e06   约 5%
  正文用    长石灰    #363433   对比 9.4:1 AAA
```

**「换个底，其他别动」** —— 用 `--from` 指定原方案，`--keep` 钉住不动的角色：

```bash
python scripts/palette.py tweak "换个底，其他别动" \
  --from "鱼肚白+战舰灰+银朱" --keep secondary --keep accent
```

方案 id 就是三个色名用 `+` 连起来，无状态，不需要会话记忆。

`--pin` 可以直接钉死某个角色（品牌色必须出现时用）：

```bash
python scripts/palette.py tweak "配一套" --pin accent=枫叶红 --mood 艳
```

微调的完整词表在 `references/tweaks.md`。注意微调语境的词义与首轮相反：首轮说「素净一点」是要素净，改稿时说「太素了」是抱怨，意思是往艳走。

### 定妆交接 pick

用户说「就这套」之后，写出给其他设计技能读的文件。

```bash
python scripts/palette.py pick "鱼肚白+战舰灰+银朱" --scene 水墨 --media ui --pair-dark
```

参数：

| 参数 | 作用 |
| --- | --- |
| `--scene` / `--mood` / `--media` | 这套方案的出处，写进 `meta` |
| `--pair-dark` | 同时推导一套暗色，产出 light/dark 两块 CSS |
| `--out <目录>` | 输出目录，默认 `.palette`（已进 `.gitignore`） |

```bash
$ python scripts/palette.py pick "鱼肚白+战舰灰+银朱" --scene 水墨 --media ui --pair-dark
已定妆：鱼肚白+战舰灰+银朱
  .palette/handoff.json
  .palette/palette.css

六个槽（给做前端的技能读）:
  场  鱼肚白    #f7f4ed
  面  珍珠灰    #e4dfd7
  墨  长石灰    #363433
  界  海鸥灰    #9a8878
  骨  战舰灰    #495c69
  眼  银朱     #f43e06

建议铺色面积: 底 92.0%  块 6.0%  点 2.0%
实测对比: 正文 11.27:1  次级 5.47:1  按钮字 4.68:1  描边 3.1:1

撞车提示:
  · 场 鱼肚白 #f7f4ed 距通用暖奶油底 #f4f1ea 只有 ΔE 0.62
    处置: 这是宣纸/绢地的白，不是默认奶油。交接时写明来源…
```

产出的 `palette.css` 直接可引，亮暗两块用正确的选择器分开（不会互相覆盖）：

```css
/* 中国传统色 · 由 zhongguose-palette 生成，色值全部来自 526 色库 */
:root { color-scheme: light dark; }
:root { --color-bg: #f7f4ed; /* 鱼肚白 yudubai */ … }
[data-theme="dark"] { … }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }
```

### 查色与吸附 info / snap / search

```bash
python scripts/palette.py info 石青          # 别名解析
python scripts/palette.py info 中国红        # 泛称也会解析并给出话术
python scripts/palette.py info 月白
python scripts/palette.py snap "#c1272d"     # 库外 hex 吸附到最近具名色
python scripts/palette.py search --family 青 --role 浅底
python scripts/palette.py search --wuxing 木 --season 春 --limit 10
```

```bash
$ python scripts/palette.py info 石青
「石青」是别名 -> 群青 #1772b4
  原因：石青为蓝铜矿，正色是深蓝；网络色卡常误作薄荷绿，不可用
  文学色卡 hex #7bcfa6 仅作参考，输出必须用 #1772b4

$ python scripts/palette.py snap "#c1272d"
枫叶红      #c21f30  ΔE 1.77  红
高粱红      #c02c38  ΔE 2.75  红
鹅冠红      #d11a2d  ΔE 2.81  红
```

`search` 的筛选维度：`--family` `--wuxing` `--season` `--role` `--temperature` `--tone` `--chroma` `--limit`。
注意 `--wuxing` 和 `--season` 只有 `search` 有，`generate` 不收这两个旗标。

### 已知术语时的直接入口 generate / complete

用户自己说了行话（青花瓷、雅、主色辅色）时可以直接用，并跟着用他的词。

```bash
python scripts/palette.py generate --scene 青花 --n 3
python scripts/palette.py generate --mood 雅 --media ui
python scripts/palette.py generate --scene 水墨 --media ui --dark
python scripts/palette.py generate --scene 补服 --media ui --n 1
python scripts/palette.py generate --seed 朱红 --mood 艳
python scripts/palette.py generate --pin accent=枫叶红 --media ui
python scripts/palette.py generate --scene 青花 --media ui --css
python scripts/palette.py generate --scene 水墨 --media ui --json
python scripts/palette.py generate --mood 雅 --media ui --tailwind
```

`generate` 的旗标：

| 旗标 | 取值 |
| --- | --- |
| `--scene` | 故宫 / 青花 / 水墨 / 敦煌 / 宋瓷 / 唐三彩 / 江南 / 漆器 / 年画 / 祭天 / 王府 / 补服 |
| `--mood` | 雅 / 艳 / 古朴 / 清冷 / 浓烈 / 空灵 / 市井 |
| `--media` | ui / poster / fashion / interior |
| `--seed` | 色名、拼音或 hex（软锚，不保证进三色） |
| `--pin` | `dominant=<色名>` / `secondary=<色名>` / `accent=<色名>`（硬钉，必出现） |
| `--dark` | 深底做场 |
| `--n` | 给几套 |
| `--css` / `--json` / `--tailwind` | 附加输出格式 |

两色补全：

```bash
python scripts/palette.py complete 月白 群青
python scripts/palette.py complete 乳白 银朱 --mood 艳
```

### 预览与自检 preview / selftest

```bash
python scripts/palette.py preview --scene 水墨 --media ui --n 3 --out preview.html
python scripts/palette.py preview --scene 青花 --dark --out preview-dark.html
python scripts/selftest.py
```

`preview` 产出的 HTML 里色条按真实建议铺色面积等比画（不是硬编码的 6/3/1）。
`selftest.py` 应输出「全部通过」，共 711 项断言。改分类、评分或白话词表后必须跑通。

### 命令总表

| 命令 | 用途 |
| --- | --- |
| `ask "<原话>"` | **主入口**，白话进、方案出，零提问 |
| `resolve "<原话>"` | 只看白话解析结果，不生成配色 |
| `tweak "<反馈>"` | 白话微调 |
| `pick "<底+块+点>"` | 定妆，写交接文件 |
| `info <色名>` | 查单色，支持别名与泛称 |
| `snap "#xxxxxx"` | 库外 hex 吸附到库内最近具名色 |
| `search` | 按色系/五行/季节/角色等维度检索 |
| `generate` | 按场景/氛围/种子生成（已知术语时用） |
| `complete <色A> <色B>` | 两色补全为一套 |
| `preview` | 生成 HTML 预览 |

重建色库（数据源变了才需要）：

```bash
python scripts/build_catalog.py --src references/source.json --out references/colors.json
python scripts/build_aliases.py
python scripts/selftest.py
```

也可 `build_catalog.py --fetch` 直接从 zhongguose.com 拉最新数据。

---

## 能用在 UI/UX 吗

可以，UI 是它的一等场景。`--media ui` 会把 WCAG 对比度作为硬闸门——不达标的方案直接淘汰，而不是照样输出让你自己发现。

一条命令拿到 17 个可直接落地的 token：

```bash
python scripts/palette.py generate --media ui --scene 水墨 --n 1 --css
```

```css
:root {
  --color-bg: #f7f4ed;              /* 鱼肚白 */
  --color-surface: #e4dfd7;         /* 珍珠灰 */
  --color-text: #363433;            /* 长石灰 */
  --color-muted: #5d655f;           /* 狼烟灰 */
  --color-border: #dad4cb;          /* 浅灰 */
  --color-border-strong: #9a8878;   /* 海鸥灰 */
  --color-secondary: #495c69;       /* 战舰灰 */
  --color-accent: #f43e06;          /* 银朱 */
  --color-accent-fg: #131824;       /* 燕颔蓝 */
  --color-accent-hover: #fa5d19;    /* 莓酱红 */
  --color-accent-active: #f9723d;   /* 芙蓉红 */
  --color-success: #20a162;         /* 翠绿 */
  --color-warning: #815f25;         /* 莱阳梨黄 */
  --color-error: #f43e06;           /* 银朱 */
  --color-info: #0f59a4;            /* 飞燕草蓝 */
  --color-disabled: #c0c4c3;        /* 月影白 */
  --color-ring: #f43e06;            /* 银朱 */
}
```

每个 token 都是色库里的具名色，不是插值出来的中间值。自带的检查覆盖：

| 闸门 | 要求 | 依据 |
| --- | --- | --- |
| 正文 on 底 | ≥ 4.5:1 | WCAG 2.2 AA (1.4.3) |
| 次级文字 on 底 | ≥ 4.5:1 | 次级说明也是正文尺寸，不能用 3:1 的大字额度 |
| 按钮字 on 按钮 | ≥ 4.5:1 | 点缀上要放得下字 |
| 强描边 on 底 | ≥ 3:1 | WCAG 2.2 (1.4.11) 输入框、部件轮廓 |
| 面层 vs 底 | ΔE ≥ 4 | 卡片必须能从背景里浮出来 |
| 状态色徽章 | 徽章上能放下 4.5:1 的字 | 黄色在米色上永远达不到 3:1，所以约束在徽章内部 |
| 色盲 | 点缀与场在三种色盲下 ΔE ≥ 12 | Brettel / Viénot 线性近似 |
| 场景色族 | 派生 token 不得漏出场景语汇 | 青花的暗色描边曾经全是紫，正是「青间紫」死局 |

**可读性优先于色族纯度**：换色会破坏对比度时保留原色，并在 `issues[]` 里如实上报，不静默交付一个读不清的字。

暗色模式是独立推导的：

```bash
python scripts/palette.py generate --media ui --dark --scene 补服 --n 1
# 主场 钢蓝 #0f1423，结构 海涛蓝 #15559a，点缀 金盏黄 #fcc307，正文 银白 16.1:1
```

深底强制安静（L\*≤22 且低彩），不会塌成紫黑；青花的暗色不会变成反相的雪白，而是钢蓝做底、孔雀蓝点缀——仍然只有青与白的语汇。

**已知边界**：不生成 Ant Design 那样的 10 阶交互链，也不做 Material 3 的 tone palette。要接入这类设计系统，把 `accent` 当种子色交给它们自己的算法。

其余媒材的约束：

| 媒材 | 硬约束 | 口令 |
| --- | --- | --- |
| `ui` | 正文 ≥4.5:1 | 页面背景 / 卡片导航 / 主按钮 |
| `poster` | 不因对比度偷换文化色 | 纸地 / 主体色块 / 印章题名 |
| `fashion` | 不做 WCAG | 主面料 / 缘饰里衬 / 盘扣绣佩 |
| `interior` | 墙面强制 C ≤ 28 | 墙面地面 / 家具柜门 / 摆件或一扇门 |

---

## 和其他设计技能配合

**色库永远第一跑。** `frontend-design` 的两遍工作法第一遍就要 4–6 个具名 hex，`artifact-design` 和 `dataviz` 也都在写代码前需要色。任何一个先跑，色就已经定了，再叫色库等于返工，而且必然出现库外 hex。

真源是**文件**不是对话——下游读文件不读对话记忆：

```bash
python scripts/palette.py pick "鱼肚白+战舰灰+银朱" --scene 水墨 --media ui --pair-dark
# → .palette/handoff.json  +  .palette/palette.css
```

`handoff.json` 分段给不同下游读：

| 技能 | 读 | 明确不读 |
| --- | --- | --- |
| frontend-design | `meta` `named6` `roles` `cliche` `bans` | `tokens_*` `chart` |
| artifact-design | `css.light` `css.dark` `tokens_light` `tokens_dark` `bans` | `chart` `named6` |
| dataviz | `chart` `tokens_light.bg/text/border` `bans` | `named6` `roles` |

`named6` 六个槽必须占满（场 / 面 / 墨 / 界 / 骨 / 眼）——**只给三色，下游会自己发明文字色和描边灰**，那两个就是库外 hex 的入口。

`cliche` 段报告是否撞上 AI 默认审美：暖奶油底 `#F4F1EA`、陶土橙 `#D97757`、黑底一枚酸色。命中不阻断，但必须显式说明差异。

下游一律不改 hex；不达标就往 `issues[]` 追加 `{token, 问题, 期望}` 由本技能重跑。需要库外新色就回来跑 `snap`。

完整合同见 [references/handoff.md](references/handoff.md)。

---

## 图表用色

**序列色与双向色在范围内**，因为它们本身就是不等权的明度阶，与「三色不等权」没有冲突。图表的轴线、网格、零线也正好由 `text` / `border` / `border_strong` 承接。

**等权分类色受限**。四条闸门同时成立（两两 ΔE ≥ 25、三种色盲下 ΔE ≥ 12、排除青间紫、对底 ≥ 3:1）时，526 色只凑得出 5 类：

```
底=鱼肚白  5 类  最小 ΔE 28.4  银朱 / 胆矾蓝 / 鷃蓝 / 棕榈绿 / 葡萄酒红
```

要更多类别请改设计——小倍数、直接标注、或明度阶配形状纹样——不要放宽闸门。

写死拒绝的四条：类别 ≥6、彩虹/jet、把三色直接当图表填充、用 success/warning/error/info 当分类色。

细则见 [references/dataviz.md](references/dataviz.md)。

---

## 当 Python 库用

不经过任何 Agent：

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

走白话入口，并产出交接文件：

```python
import sys
from pathlib import Path
sys.path.insert(0, "zhongguose-palette/scripts")

from engine import Catalog, generate
from vernacular import Vernacular
import handoff as ho

cat = Catalog()
it = Vernacular().resolve("券商的后台系统，要稳重可信", catalog=cat)
print(it.echo)        # ['网页界面', '石青深底上一枚金线徽章']
print(it.unheard)     # [] —— 没有接不住的词

pal = generate(cat, scene=it.scene, mood=it.mood, media=it.media, dark=it.dark, n=1)[0]
data = ho.build(cat, pal)
ho.write(data, Path(".palette"))
```

其他有用的入口：

```python
from engine import (
    SCENES, MOODS, MEDIA,          # 场景 / 氛围 / 媒材的定义
    complete_pair,                 # 两色补全
    visual_areas,                  # 建议铺色面积
    apply_family_lock,             # 把 token 吸回场景色族
    cliche_check,                  # AI 默认审美撞车检查
    resolve_seed, SeedNotFound,    # 种子色解析（失败会抛错，不静默）
)
from handoff import sequential, categorical    # 图表色
```

---

## 创建思路

### 1. 先把数据做实，再谈审美

原始 `colors.json` 只有 name / pinyin / hex / RGB / CMYK。直接拿去配色没法筛——526 个色平铺出来，模型只能凭色名猜。所以第一步是给每个色补上可检索、可计算的属性：

- **色彩空间**：HSL、HSV、CIELAB、CIELCh（混色和距离一律走 Lab/LCH，不用 HSL）
- **对比度**：对纯白、纯黑、乳白纸底的 WCAG 比值，外加 APCA 感知值
- **文化标签**：色系、五行、四季、明度带、彩度带、冷暖、物象来源
- **设计角色**：浅底 / 纸感 / 面层 / 墨色 / 点缀 / 描边 / 中性 / 金属…

有了角色标签，「能当纸地的有哪 25 个」「能当正文墨色的有哪 72 个」就成了可直接决策的问题。

处理中发现两处数据问题，都在 `build_catalog.py` 里显式处理：8 条记录的 RGB 字段与 hex 不一致（以 hex 为准，原值留在 `rgb_source`），7 组拼音重复（加数字后缀去重）。

### 2. 分类时色名优先于色值

「鲛青」实测偏墨绿，但古人叫它青，在织物语境里它就是青。所以色系判定先看名字末字，再用实测色相校正明显冲突——名叫白/灰而彩度极高（C≥35）才改判，名叫彩色而实测近无彩（C<5）才改判。

反过来也有陷阱：`海参灰` 实际是近白 `#fffefa`，`长石灰` 是近黑 `#363433`，`新禾绿` 色相 95° 其实是黄。**选色按 LCh，不按字面。**

### 3. 评分要能解释，也要能被反例推翻

八个分项各自惩罚一类具体错误（点缀不够显著、明度贴在一起、冷暖串色、青间紫、放不下文字、五行相克、三色太近、色盲下消失），权重写在 `SCORE_WEIGHTS` 里可调。

关键做法是**用手选方案反过来校准评分**。写完第一版后，手选的「青花甜白」只得 75.8 分，而算法凑出的「玉粉红 + 岩石棕 + 紫荆红」得 95.8——后者和故宫毫无关系。这说明评分错了，不是手选错了。查出两个模型缺陷：

1. 把「点缀必须彩度最高」当成硬规则，但青花的点缀（鷃蓝钩线）是靠**更深**跳出来的。改成取彩度跳与明度跳的较强者。
2. 近无彩的场（纸、绢、宣）参与了五行相克判定，于是甜白釉配青花被「金克木」扣分。纸白在文化上是「地」而非「色」，不该参与。

修完后手选均分 91.1，退化案例（三色同色 37、三色全浅白 43、青间紫 63）明显低于手选。

### 4. 文化规则当语法，不当装饰

五行、正色间色、荆浩口诀不是加在文档末尾的花边，而是写进评分和候选池的约束：

- 荆浩「青间紫不如死」→ 青×紫同时出现，色相分乘 0.45。派生 token 也要防——`family_lock()` 就是为此存在
- 「红间绿花簇簇」→ 年画/市井允许，雅/清冷扣分
- 场景限定色相窗口 → 故宫的点缀必须落在 H 20°–70°（朱红系），品红/紫荆红被挡在池外
- 「后素功」→ 留白算进主场；空灵/水墨/宋瓷 的目标份额是 88/9/3 而不是 60/30/10

### 5. 承认库的边界，用别名兜住

用户会说「石青配月白」，但**石青不在 526 色里**。网络流传的 161 色文学色卡给了一个薄荷绿——那是把「石青」误当成青绿，真正的石青是蓝铜矿。

所以做了别名层：先按 CIEDE2000 找最近邻，再用文化校正覆盖机器结果。输出永远是库内色，同时告诉用户「你说的石青在本色库叫群青」。

别名的 `reason` 与 `target` 必须自洽——曾经有一条 reason 写「青中带灰，不是鲜蓝」而 target 是明亮青蓝，`selftest.py` 现在有断言挡这类自相矛盾。

### 6. 白话映射必须能回归

映射规则写在 `references/vernacular.json` 而不是提示词散文里，配 63 条用例由 `selftest.py` 消费。理由和第 3 节一样：写在散文里的规则会随模型版本漂移，而漂移的症状看起来像「颜色选得不好」，于是会去调评分权重，真正错的却是意图识别。

设计上的三处要点：

- **长词吃掉自己的字符 span**：「素雅」命中后「素」「雅」不能在同一片字符上再各算一次，否则 3.0 会滚成 5.4，歧义门限永远踩不准
- **否定要转对极**：「婚礼请柬，别太艳」里 婚礼(2.0) 减 艳(1.2) 还剩 0.8，只减分的话「别」就白说了；所以同时把权重转给对极
- **微调语境词义相反**：首轮「素净一点」是需求，改稿时「太素了」是抱怨，走独立词表，且用显式对照表而不是在一条数组上走索引

---

## 数据与理论来源

### 色值

**526 色**全部来自 [中国色 zhongguose.com](https://zhongguose.com/) 的 `colors.json`（原件存为 `references/source.json`，未加工）。网站作者署名 Perchouli。本项目未修改任何 hex，只补充计算字段。

若在产品里展示色名，建议注明「色值来自 zhongguose.com」。

### 文学色名

`references/aliases.json` 的典故释义参考网络流传的约 161 色文学色卡（常见于 [zerosoul/chinese-colors](https://github.com/zerosoul/chinese-colors)，其 README 指向新浪博客《中国传统颜色》）。这些 hex **只作典故，不作输出**；若干条（尤其「石青」）与颜料本义不符，已文化校正。

### 配色理论

- **三色层级配色法**：设计与穿搭里通行的做法——一个主导的场、一组承托的结构、几处最小面积的点缀。核心是**不等权**。
- **荆浩《画说》**：「红间黄秋叶坠，红间绿花簇簇，青间紫不如死，粉笼黄胜增光。」五代画论，现存最凝练的中国配色规则。
- **《周礼·考工记》**：五色正轴（青赤黄白黑）、「凡画缋之事，后素功」、钟氏染羽「三入为纁，五入为緅，七入为缁」。
- **郑玄注**：间色为正色两两相加。注意「缁」在钟氏染羽里是七入之黑，在皇侃《论语义疏》一路的五间色系统里被列为黄之间色——两个系统对同一个字的用法不同，不要拿一个否定另一个。
- **《清史稿·舆服志》**：文武各品「补服，色用石青」——礼制里唯一天生「深底 + 小徽章」的形制。
- **Itten** 色彩对比七类、**Albers** 相邻色互相影响。
- **沈宗骞**、清代画论：「以色助墨光，以墨显色彩」；罩染法降火气。

### 色彩科学

- **CIELAB / CIELCh**（D65 白点）：混色、色差、明度分带
- **CIEDE2000**：色差，实现对齐 Sharma 等人的公开测试集
- **WCAG 2.2**：相对亮度与对比度（1.4.3 文本、1.4.11 非文本）
- **APCA 0.1.9**（W3C Silver 草案）：近似实现，仅作感知参考；正式验收仍以 WCAG 为准
- **Brettel / Viénot** 色盲模拟线性近似

### 参照的设计系统

角色命名与分层参考了 Radix Colors（border vs borderStrong 的区分）、shadcn/ui 的语义 token 命名、Material 3 的 on-color 概念。**未**照搬其色阶生成算法——本项目从离散色库取色，不做连续色阶。

---

## 文件结构

```
zhongguose-palette/
├── SKILL.md                     技能入口（模型先读这个，99 行的路由表）
├── README.md
├── INSTALL.md                   六种宿主的安装方式
├── ATTRIBUTION.md               出处
├── LICENSE                      MIT
├── agents/openai.yaml           Codex 界面元数据
├── assets/                      HTML 预览样张
├── references/
│   ├── source.json              官网原件，未加工
│   ├── colors.json              526 色 + LCH / 对比度 / 五行 / 角色
│   ├── aliases.json             144 条经典色名 → 库内色（含文化校正与泛称红）
│   ├── curated.json             20 套手选方案（含白话版出处与注意事项）
│   ├── vernacular.json          白话 → 内部轴的映射表（535 条线索词）
│   ├── vernacular_cases.jsonl   63 条映射回归用例
│   ├── rules.md                 14 条铁律与常见失败
│   ├── tweaks.md                白话微调词表
│   ├── handoff.md               与其他设计技能的交接合同
│   ├── dataviz.md               图表用色：序列 / 双向 / 分类的边界
│   ├── theory.md                层级、混色、对比度、评分
│   ├── culture.md               正色间色、五行、禁忌、场景出处
│   └── examples.md              输出话术样例
└── scripts/
    ├── palette.py               CLI（ask / resolve / tweak / pick / snap / search / info / generate / complete / preview）
    ├── vernacular.py            白话解析器
    ├── render.py                ANSI 面积等比色条
    ├── handoff.py               交接文件生成
    ├── engine.py                检索、评分、生成、token、family lock、cliché
    ├── colorkit.py              sRGB / Lab / LCH / WCAG / APCA / CIEDE2000
    ├── taxonomy.py              色系、五行、四季、角色
    ├── build_catalog.py         从 source.json 重建色库
    ├── build_aliases.py         重建别名表
    └── selftest.py              711 项回归
```

---

## 铁律

完整条文在 [references/rules.md](references/rules.md)。最要紧的几条：

1. **只出色库里的色**，禁止「中国红」这种泛称。要库外的色就 `snap`，不许插值
2. **三色必须不等权**：铺满的底、成块的那层、最小面积那一点，视觉分量依次递减
3. **铺满的那层必须安静**：朱红是点缀或结构，不是满屏背景
4. **素底先立，彩饰后加**；留白算进主场，留白型走 88/9/3
5. **青间紫不如死**；紫禁城红墙黄瓦不是 App 模板；金只走线不填面，也不能当隔断
6. **石青 / 玄色 / 胭脂 / 黛 / 中国红** 等先走别名表
7. **不许暗中换色**：被否决的方向要说原因；为满足要求调整了档位必须明说
8. **可读性优先于色族纯度**：换色会破坏对比度时保留原色并如实上报

对用户说话时不要用这些内部词：主场、结构色、点缀色、五行、相生相克、荆浩、后素功、彩度、明度带、间色正色、ΔE、LCH、token、氛围、场景、媒材。要大声说的是色名、hex、铺在哪、多大面积、字用什么。

---

## 许可

代码与文档：MIT，见 [LICENSE](LICENSE)。

色值数据版权归 [zhongguose.com](https://zhongguose.com/) 所有，本项目仅作整理与计算加工，详见 [ATTRIBUTION.md](ATTRIBUTION.md)。
