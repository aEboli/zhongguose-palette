# 交接合同

其他设计技能怎么消费这套配色。

## 谁先跑：色库永远第一

`frontend-design` 的两遍工作法第一遍就要 4–6 个具名 hex；`artifact-design` 和
`dataviz` 也都在写代码前需要色。任何一个先跑，色就已经定了，再叫色库等于返工，
而且必然出现库外 hex。

## 真源是文件，不是对话

```bash
python scripts/palette.py pick "鱼肚白+战舰灰+银朱" --scene 水墨 --media ui --pair-dark
```

写出两个文件（默认 `.palette/`，已进 `.gitignore`）：

- `.palette/handoff.json` —— 分段给不同下游读
- `.palette/palette.css` —— 亮暗两块 CSS 变量，可直接引

下游读文件不读对话记忆。留在对话里的结果是它自己发明灰色和描边色，
库外 hex 立刻漏出去。

## 谁读哪一段

| 技能 | 读 | 明确不读 |
| --- | --- | --- |
| frontend-design | `meta` `named6` `roles` `ornament` `cliche` `bans` | `tokens_*` `chart` |
| artifact-design | `css.light` `css.dark` `tokens_light` `tokens_dark` `bans` | `chart` `named6` |
| dataviz | `chart` `tokens_light.bg/text/border` `bans` | `named6` `roles` |

只读自己那段，避免上下文膨胀。

## ornament：纹样点缀怎么消费

`--motif` 选了纹样时，`handoff.json` 多一段 `ornament`。它给的是**借哪个变量**，
不是 hex——纹样资产里一个色值字符都没有。

| 字段 | 是什么 |
| --- | --- |
| `chosen[]` | 选中的纹样。每条给 `borrows_var`（CSS 变量名）、`borrows_alternates`（备选变量）、`placement`（落位）、`css_hint`（尺寸）、`alpha_suggested` / `alpha_max`、`ink_pct` + `ink_range` + `ink_note`（墨量）、`charge`（计费明细） |
| `suggestions[]` | 这个场景适配的纹样 id。按纹样自己的 `fits_scenes` 算，不是「没被排除」 |
| `issues[]` | 不合规的地方：借了白名单外的 token、彩度抬升超闸门、alpha 超上限、场景气质不合、计费超额。**必须向用户明说，不许静默交付** |
| `render` | 渲染形态。`preferred: mask`，`must_not` 列出禁止的三种写法 |
| `ink_sources.allowed` | 合法借色源只有 8 个。交互态（`accent_hover` 等）、语义徽章（`success` 等）、失能态、焦点环一律不许借——那等于把状态语义泄进装饰层 |
| `chroma_gate` | 压在正文下时合成彩度的抬升上限。实测借高彩 accent 会冲到 +13.5，那是一片可见色晕 |
| `alpha_ceilings` | 各 token 作纹样底时的 alpha 上限。看的是合成后正文还剩多少对比，不是看借了哪个 token |
| `budget` | 墨量与铺色面积是两套账。`charge` 给折价公式与上限，`accent_pct` 给点缀额度 |
| `sets` / `taboo` | 成套语汇（四君子一屏一种）与礼制等第（五爪龙、十二章、补子）。拒绝要给替代路径 |

三条硬的：

1. **只许 mask 或 inline SVG。** 禁用 `background-image: url()` 承载有色纹样——
   url() 让 SVG 成为外部资源，`currentColor` 与 `var()` 在里面一律失效，想换色只能改那串 hex。
2. **裸 `var()` 写在 SVG 呈现属性上会静默降级且方向相反**：`fill` 回落成纯黑
   （破「不许纯黑」），`stroke` 回落成 `none`（纹样凭空消失）。必须带 fallback：
   `stroke="var(--color-border, currentColor)"`。
3. **纹样是装饰**，`aria-hidden="true" focusable="false"`。若它承载了信息
   （用图案区分类别），那它就不是装饰，必须另给文字或 `aria-label`。

计费的判据是**实测彩度 C≥12**，不是 token 名。年画的 surface 是荔肉白 C=13.2、
border 是菊蕾白 C=20.8，都在彩度档要计费；水墨的 accent 是银灰 C=10.8，反倒零计费。
把 `surface` / `border` 当成「中性」的同义词只在素净场景里偶然成立。

细则读 `references/motifs.md`。

## named6 为什么必须占满六槽

`frontend-design` 要 4–6 个具名 hex。**只给三色，它会自己发明文字色和描边灰**
——那两个就是库外 hex 的入口。

槽名用中文单字，本身就是差异化的来源：

| 槽 | 来自 | 用途 |
| --- | --- | --- |
| 场 | `tokens.bg` | 页面底 |
| 面 | `tokens.surface` | 卡片、面层 |
| 墨 | `tokens.text` | 正文 |
| 界 | `tokens.border_strong` | 输入框、部件轮廓 |
| 骨 | 成块那层 | 导航、图形主体 |
| 眼 | 标点 | 主按钮、印章 |

随色必交三件非色值的东西：

1. `roles.*.area_pct` —— 不给的话 60/30/10 会被读成三等分，标点会铺成整条顶栏
2. 一句物象出处（`meta.origin`）
3. `cliche` 报告

同时写明：**字体与布局不属本技能**。

## 回写通道

下游一律不改 hex。不达标、漏色、类别数超上限时，往 `issues[]` 追加：

```json
{"token": "accent_fg", "problem": "按钮上的字只有 4.07:1", "expected": "≥4.5:1"}
```

由本技能重跑。**没有回写通道，下游遇到不合意的色一定自己改，真源立刻失效**
——这是「唯一真源」能否成立的唯一闸门。

## 撞车闸门（cliche）

`frontend-design` 自己点名了当下最容易被认出来的 AI 默认审美：

| flag | 判定 | 处置 |
| --- | --- | --- |
| `cream_ground` | 底距 `#F4F1EA` ΔE < 6 | 说明这是甜白釉/宣纸的白，不是默认奶油；或换月白/米色 |
| `clay_accent` | 标点或成块层距 `#D97757` ΔE < 10 | 说明这是矿物朱的来源，或换苋菜红/枫叶红 |
| `acid_on_black` | 深底 + 单一高彩绿/朱 | 加一层结构分隔，或把标点降到中彩 |

命中不阻断，但**必须显式说明差异**，不许沉默通过。
实测：鱼肚白距那个奶油底只有 ΔE 0.62 —— 而它正是水墨方案的缺省底。

## family lock

`tokens()` 的签名里没有 scene，是 scene-blind 的，所以派生层会漏色。

实测 `--scene 青花 --dark`：surface=暗龙胆紫、border=龙葵紫、border_strong=山梗紫
——青配紫，正是荆浩点名的死局，而 `artifact-design` 消费的恰恰是 token 而非三色。

交接前扫一遍：落在「场景色族 ∪ {灰,白,黑}」之外的按同明度吸附回场景语汇，
改不动的写进 `issues[]` 并向用户明说。

**语义色不参与扫描**：success / warning / error / info 的绿黄红青是文化锁，本就跨族。

## 暗色两块 CSS 的正确形状

两块都出 `:root` 会互相覆盖。正确写法：

```css
:root { color-scheme: light dark; }
:root { /* 亮色 17 个变量 */ }
[data-theme="dark"] { /* 暗色 17 个变量 */ }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* 同上 */ }
}
```

两边键完全一致、只有值不同，且必须来自**两次独立运行**（第二次带 `--dark`）。
禁用 `filter: invert`。

配对时两次都只给 `--scene`（可加 `--mood`），**不要串 seed**：实测
`--dark --scene 青花` 不带 seed 给孔雀蓝（仍是青，通过），加 `--seed 鷃蓝`
就变成莽丛绿，青花的语汇破了。

## 分工线

本技能只定**色**与**面积预算**，不对 typography、间距、圆角、组件结构、动效发言。
两个技能在同一轴上打架比各自留白更糟。

给 `artifact-design` 额外一条：直接写 `background: white` 就破了铁律 1，
库内最近的是雪白 `#fffef9`；深色用燕颔蓝 `#131824`，不是 `#000`。
