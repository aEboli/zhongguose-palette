# 中国传统色配色技能

从 [zhongguose.com](https://zhongguose.com/) 的 **526 个中国传统色**里，按**主场 / 结构 / 点缀**三个角色选出一套能直接用的配色。既是 Claude Code / Codex 的 Skill，也是可独立运行的命令行工具和 Python 库。

不是「挑三个好看的 hex」，而是把颜色当成角色来分配：**来自色库、分得出主次、文字能读、文化上说得通**。

```bash
$ python scripts/palette.py generate --scene 青花 --n 1

评分 93.9  氛围=清冷  场景=青花
  主场  雪白       #fffef9  白 无彩
  结构  群青       #1772b4  青 中彩
  点缀  鷃蓝       #144a74  蓝 中彩
    · 手选方案「青花甜白」：明永乐甜白釉上的苏麻离青
    · 注意：青花的规矩是只有青与白，不要加第四色
```


## 目录

- [它解决什么问题](#它解决什么问题)
- [能用在 UI/UX 吗](#能用在-uiux-吗)
- [快速开始](#快速开始)
- [创建思路](#创建思路)
- [数据与理论来源](#数据与理论来源)
- [跨模型使用](#跨模型使用)
- [文件结构](#文件结构)
- [铁律](#铁律)

## 它解决什么问题

让模型配中国风颜色，通常会遇到四个坑，这个技能逐个堵掉：

| 坑 | 表现 | 这里怎么做 |
| --- | --- | --- |
| 编造色值 | 输出「中国红 `#C8161D`」这种查无此色的 hex | 只从 526 色里取，输出必带中文色名 + 拼音 |
| 三色等权 | 主场、结构、点缀一样响，像广告布 | 按响度派角色，主场强制安静 |
| 面积当比例 | 把高彩点缀真铺成一整条色带 | 按感知能量反推建议铺色面积，点缀实附远小于名义额度 |
| 文化错配 | 「石青」给成薄荷绿、故宫配色出现品红 | 140 条别名做文化校正，场景限定色相窗口 |

具体能力：

- **9 个场景**：故宫、青花、水墨、敦煌、宋瓷、唐三彩、江南、漆器、年画
- **7 种氛围**：雅、艳、古朴、清冷、浓烈、空灵、市井
- **4 种媒材**：UI、海报/插画、服装、空间（各有不同硬约束）
- **暗色模式**：深底做场，不是浅色方案整页反相
- **20 套手选方案**：经过文化校对，与算法方案同场评分排序
- **别名解析**：石青、玄色、胭脂、竹青、天青、黛、漆黑、墨色… 告诉你库内对应哪一色
- **输出格式**：CSS 变量、Tailwind theme、JSON、HTML 预览

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

每个 token 都是色库里的具名色，不是插值出来的中间值。自带的检查（`selftest.py` 共 525 项）覆盖：

| 闸门 | 要求 | 依据 |
| --- | --- | --- |
| 正文 on 底 | ≥ 4.5:1 | WCAG 2.2 AA (1.4.3) |
| 次级文字 on 底 | ≥ 4.5:1 | 次级说明也是正文尺寸，不能用 3:1 的大字额度 |
| 点缀字 on 点缀 | ≥ 4.5:1 | 按钮上的字 |
| 强描边 on 底 | ≥ 3:1 | WCAG 2.2 (1.4.11) 输入框、部件轮廓 |
| 面层 vs 底 | ΔE ≥ 4 | 卡片必须能从背景里浮出来 |
| 状态色徽章 | 徽章上能放下 4.5:1 的字 | 黄色在米色上永远达不到 3:1，所以约束在徽章内部而不是对页面 |
| 色盲 | 点缀与场在三种色盲下 ΔE ≥ 12 | Brettel/Viénot 线性近似 |

暗色模式是独立推导的：

```bash
python scripts/palette.py generate --media ui --dark
# 主场 燕颔蓝 #131824，结构 朱红 #ed5126，点缀 甘草黄 #f3bf4c
# text 银白 15.57:1，surface 牛角灰，warning 藤黄
```

青花的暗色不会变成反相的雪白，而是钢蓝做底、孔雀蓝点缀——仍然只有青与白的语汇。

**已知边界**：不生成 Ant Design 那样的 10 阶交互链，也不做 Material 3 的 tone palette。要接入这类设计系统，把 `accent` 当种子色交给它们自己的算法。数据可视化的分类色系列也不在范围内——那需要等权色，与三色不等权的前提冲突。

其余媒材的约束：

| 媒材 | 硬约束 | 口令 |
| --- | --- | --- |
| `ui` | 正文 ≥4.5:1 | 页面背景 / 卡片导航 / 主按钮 |
| `poster` | 不因对比度偷换文化色 | 纸地 / 主体色块 / 印章题名 |
| `fashion` | 不做 WCAG | 主面料 / 缘饰里衬 / 盘扣绣佩 |
| `interior` | 墙面强制 C ≤ 28 | 墙面地面 / 家具柜门 / 摆件或一扇门 |

## 快速开始

需要 Python 3.10+，**无第三方依赖**。

```bash
git clone https://github.com/aEboli/zhongguose-palette.git
cd zhongguose-palette

python scripts/palette.py generate --scene 青花 --n 3
python scripts/palette.py generate --mood 雅
python scripts/palette.py generate --seed 朱红 --mood 艳
python scripts/palette.py generate --dark                    # 暗色：深底做场
python scripts/palette.py generate --media ui --scene 水墨    # ui/poster/fashion/interior
python scripts/palette.py complete 月白 群青                  # 两色补全
python scripts/palette.py info 石青                           # 别名解析
python scripts/palette.py search --family 青 --role 浅底
python scripts/palette.py preview --scene 水墨 --out preview.html
python scripts/selftest.py                                   # 525 项回归
```

Windows 中文乱码时先设 `PYTHONUTF8=1` 和 `PYTHONIOENCODING=utf-8`。

## 创建思路

### 1. 先把数据做实，再谈审美

原始 `colors.json` 只有 name / pinyin / hex / RGB / CMYK。直接拿去配色没法筛——526 个色平铺出来，模型只能凭色名猜。所以第一步是给每个色补上可检索、可计算的属性：

- **色彩空间**：HSL、HSV、CIELAB、CIELCh（混色和距离一律走 Lab/LCH，不用 HSL）
- **对比度**：对纯白、纯黑、乳白纸底的 WCAG 比值，外加 APCA 感知值
- **文化标签**：色系、五行、四季、明度带、彩度带、冷暖、物象来源
- **设计角色**：浅底 / 纸感 / 面层 / 墨色 / 点缀 / 描边 / 中性 / 金属…

有了角色标签，「能当主场纸地的有哪 25 个」「能当正文墨色的有哪 72 个」就成了可直接决策的问题。

处理中发现两处数据问题，都在 `build_catalog.py` 里显式处理：8 条记录的 RGB 字段与 hex 不一致（以 hex 为准，原值留在 `rgb_source`），7 组拼音重复（加数字后缀去重）。

### 2. 分类时色名优先于色值

「鲛青」实测偏墨绿，但古人叫它青，在织物语境里它就是青。所以色系判定先看名字末字，再用实测色相校正明显冲突——名叫白/灰而彩度极高（C≥35）才改判，名叫彩色而实测近无彩（C<5）才改判。

反过来也有陷阱：`海参灰` 实际是近白 `#fffefa`，`长石灰` 是近黑 `#363433`，`新禾绿` 色相 95° 其实是黄。**选色按 LCh，不按字面。**

### 3. 评分要能解释，也要能被反例推翻

八个分项各自惩罚一类具体错误（点缀不够显著、明度贴在一起、冷暖串色、青间紫、放不下文字、五行相克、三色太近、色盲下消失），权重写在 `SCORE_WEIGHTS` 里可调。

关键做法是**用手选方案反过来校准评分**。写完第一版后，手选的「青花甜白」只得 75.8 分，而算法凑出的「玉粉红 + 岩石棕 + 紫荆红」得 95.8——后者和故宫毫无关系。这说明评分错了，不是手选错了。查出两个模型缺陷：

1. 我把「点缀必须彩度最高」当成硬规则，但青花的点缀（鷃蓝钩线）是靠**更深**跳出来的。改成取彩度跳与明度跳的较强者。
2. 近无彩的场（纸、绢、宣）参与了五行相克判定，于是甜白釉配青花被「金克木」扣分。纸白在文化上是「地」而非「色」，不该参与。

修完后手选均分 91.1，退化案例（三色同色 37、三色全浅白 43、青间紫 63）明显低于手选。

### 4. 文化规则当语法，不当装饰

五行、正色间色、荆浩口诀不是加在文档末尾的花边，而是写进评分和候选池的约束：

- 荆浩「青间紫不如死」→ 青×紫同时出现，色相分乘 0.45
- 「红间绿花簇簇」→ 年画/市井允许，雅/清冷扣分
- 场景限定色相窗口 → 故宫的点缀必须落在 H 20°–70°（朱红系），品红/紫荆红被挡在池外
- 「后素功」→ 留白算进主场，中国气质常常比通用配色更偏向大面留白

### 5. 承认库的边界，用别名兜住

用户会说「石青配月白」，但**石青不在 526 色里**。网络流传的 161 色文学色卡给了一个薄荷绿——那是把「石青」误当成青绿，真正的石青是蓝铜矿。

所以做了别名层：先按 CIEDE2000 找最近邻，再用 37 条文化校正覆盖机器结果。输出永远是库内色，同时告诉用户「你说的石青在本色库叫群青」。

## 数据与理论来源

### 色值

**526 色**全部来自 [中国色 zhongguose.com](https://zhongguose.com/) 的 `colors.json`（原件存为 `references/source.json`，未加工）。网站作者署名 Perchouli。本项目未修改任何 hex，只补充计算字段。

若在产品里展示色名，建议注明「色值来自 zhongguose.com」。

### 文学色名

`references/aliases.json` 的典故释义参考网络流传的约 161 色文学色卡（常见于 [zerosoul/chinese-colors](https://github.com/zerosoul/chinese-colors)，其 README 指向新浪博客《中国传统颜色》）。这些 hex **只作典故，不作输出**；若干条（尤其「石青」）与颜料本义不符，已文化校正。

### 配色理论

- **三色层级配色法**：设计与穿搭里通行的做法——一个主导的场、一组承托的结构、几处最小面积的点缀。核心是**不等权**：三者的视觉分量必须依次递减，而不是均分画布。本项目按角色分工实现，具体面积由感知能量反推。
- **荆浩《画说》**：「红间黄秋叶坠，红间绿花簇簇，青间紫不如死，粉笼黄胜增光。」五代画论，现存最凝练的中国配色规则。
- **《周礼·考工记》**：五色正轴（青赤黄白黑）、「凡画缋之事，后素功」、钟氏染羽「三入为纁，五入为緅，七入为缁」。
- **郑玄注**：间色为正色两两相加（绿为青之间、红为赤之间、碧为白之间、紫为黑之间、缁为黄之间）。
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

## 跨模型使用

能力层（`scripts/` + `references/`）是纯 Python 标准库 + JSON + Markdown，不绑任何模型。只有 `SKILL.md` 和 `agents/openai.yaml` 是宿主约定。

| 宿主 | 怎么接 | 效果 |
| --- | --- | --- |
| Claude Code | 拷进 `~/.claude/skills/` | 完整 |
| Codex / OpenAI CLI | 拷进 `~/.codex/skills/` | 完整 |
| ChatGPT 带代码解释器 | 打包上传，让它跑 `palette.py` | 完整 |
| GPTs / 网页版无代码 | `references/*.json` 传 Knowledge，铁律粘进 Instructions | 降级 |
| Cursor / Cline / Windsurf | 放进项目，规则文件指向 `SKILL.md` | 完整 |
| 自己的程序 | 当 Python 库导入 | 完整 |

```python
import sys; sys.path.insert(0, "zhongguose-palette/scripts")
from engine import Catalog, generate, tokens, css_vars, as_dict

cat = Catalog()
pal = generate(cat, scene="青花", media="ui", n=1)[0]
print(pal.dominant.name, pal.dominant.hex)   # 雪白 #fffef9
print(css_vars(tokens(cat, pal)))
print(as_dict(pal, tokens(cat, pal)))        # 完整 JSON，可喂给任意模型
```

无代码环境会明显降级：评分、色差、对比、面积换算都在脚本里。补偿办法是让它优先直接引用 `curated.json` 的 20 套手选方案，别现场配。

详见 [INSTALL.md](INSTALL.md)。

## 文件结构

```
zhongguose-palette/
├── SKILL.md                 技能入口（模型先读这个）
├── README.md
├── INSTALL.md               六种宿主的安装方式
├── ATTRIBUTION.md           出处
├── agents/openai.yaml       Codex 界面元数据
├── assets/                  HTML 预览样张
├── references/
│   ├── source.json          官网原件，未加工
│   ├── colors.json          526 色 + LCH / 对比度 / 五行 / 角色
│   ├── aliases.json         140 条经典色名 → 库内色（37 条文化校正）
│   ├── curated.json         20 套手选方案
│   ├── theory.md            层级、混色、对比度、评分
│   ├── culture.md           正色间色、五行、禁忌、别名
│   └── examples.md          输出话术样例
└── scripts/
    ├── palette.py           CLI
    ├── engine.py            检索、评分、生成、token
    ├── colorkit.py          sRGB / Lab / LCH / WCAG / APCA / CIEDE2000
    ├── taxonomy.py          色系、五行、四季、角色
    ├── build_catalog.py     从 source.json 重建色库
    ├── build_aliases.py     重建别名表
    └── selftest.py          525 项回归
```

重建色库：

```bash
python scripts/build_catalog.py --src references/source.json --out references/colors.json
python scripts/build_aliases.py
python scripts/selftest.py
```

也可 `--fetch` 直接从 zhongguose.com 拉最新数据。

## 铁律

完整条文在 [SKILL.md](SKILL.md)。最要紧的几条：

1. 只出色库里的色，禁止「中国红」这种泛称
2. 三色必须不等权：主场、结构、点缀的视觉分量依次递减
3. 主场必须安静：朱红是点缀或结构，不是满屏背景
4. 素底先立，彩饰后加；留白算进主场
5. 青间紫不如死；紫禁城红墙黄瓦不是 App 模板；金只走线不填面
6. 石青 / 玄色 / 胭脂 / 黛 等先走别名表

## 许可

代码与文档：MIT。

色值数据版权归 [zhongguose.com](https://zhongguose.com/) 所有，本项目仅作整理与计算加工，详见 [ATTRIBUTION.md](ATTRIBUTION.md)。
