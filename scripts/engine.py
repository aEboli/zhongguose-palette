#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中国传统色检索与配色引擎。

只从 526 色库取色，永不发明新 hex。三色按主场 / 结构 / 点缀分配角色。

核心算法不在 HSL 里混色，而在 CIELAB/LCH 里算距离、冷暖、彩度层级，
再按一组可解释的评分挑出最美的三色。评分权重写在 SCORE_WEIGHTS，可调。
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import colorkit as ck  # noqa: E402
import taxonomy as tx  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "references" / "colors.json"
ALIASES_PATH = ROOT / "references" / "aliases.json"
CURATED_PATH = ROOT / "references" / "curated.json"

# 评分权重：总和不必为 1，相对大小才重要。调参时只改这里。
SCORE_WEIGHTS = dict(
    chroma_hierarchy=1.4,   # 彩度必须分层：主场安静、点缀跳出来
    lightness_ladder=1.1,   # 明度要拉开，否则两个色贴在一起
    undertone=1.2,          # 大面积两色冷暖要同向
    hue_relation=1.0,       # 色相关系：同族稳、邻近雅、互补险
    contrast=1.3,           # 必须能选出可读文字
    cultural=0.6,           # 五行相生加分、相克减分（可被氛围覆盖）
    uniqueness=0.5,         # 三色不能太近
    cvd=0.7,                # 红绿色盲仍可辨
)

# 氛围预设：过滤 60/30/10 各自允许的明度彩度范围，以及是否允许相克。
# 氛围预设：约束 60/30/10 各自的角色、彩度与明度带。
# sec_tone 很关键——只限彩度不限明度时，"空灵"会挑出中明度的灰粉当辅色，
# 于是水墨变成了灰调米色，全无墨意。墨必须是深的。
MOODS = {
    "雅": dict(dom=("浅底", "纸感"), sec_chroma=(0, 28), acc_chroma=(18, 55),
              sec_tone=None, acc_tone=("中", "中深", "深"), allow_ke=False,
              prefer_temp="中性", note="低彩大面积，点缀也不过火，宋瓷、文人画气质"),
    "艳": dict(dom=("浅底", "纸感", "面层"), sec_chroma=(18, 55), acc_chroma=(45, 999),
              sec_tone=None, acc_tone=("中", "中浅", "中深"), allow_ke=True,
              prefer_temp="暖", note="宫廷、年画、漆器：点缀极彩，辅色也可稍艳"),
    "古朴": dict(dom=("面层", "描边", "深底"), sec_chroma=(8, 40), acc_chroma=(20, 70),
                sec_tone=None, acc_tone=("中深", "深", "极深"), allow_ke=False,
                prefer_temp="暖", note="低明度、土黄赭石，青铜、土陶、宣纸旧色"),
    "清冷": dict(dom=("浅底", "纸感"), sec_chroma=(4, 30), acc_chroma=(14, 50),
                sec_tone=None, acc_tone=("中", "中深"), allow_ke=False,
                prefer_temp="冷", note="宋瓷天青、月白、花青，冷调低彩"),
    "浓烈": dict(dom=("深底", "墨色"), sec_chroma=(10, 45), acc_chroma=(40, 999),
                sec_tone=None, acc_tone=("中", "中浅", "中深"), allow_ke=True,
                prefer_temp=None, note="敦煌、漆器：深底托高彩点缀"),
    "空灵": dict(dom=("浅底",), sec_chroma=(0, 18), acc_chroma=(8, 40),
                sec_tone=("中深", "深", "极深"), acc_tone=("中深", "深", "极深"),
                allow_ke=False, prefer_temp="中性",
                note="水墨留白：主场几乎是纸，结构是墨，点缀是一枚印"),
    "市井": dict(dom=("浅底", "纸感", "面层"), sec_chroma=(20, 60), acc_chroma=(45, 999),
                sec_tone=None, acc_tone=("中", "中浅"), allow_ke=True,
                prefer_temp="暖", note="年画、门神：高对比、大红大绿可以相克"),
}

# 场景预设：直接指定氛围 + 建议的色系/五行倾向，作为搜索起点。
# 场景预设：mood 定明度彩度、families 限色系、accent_break 是该场景允许的破色。
# 破色是传统配色的关键手法——水墨全局无彩，唯一的红是那枚印章；
# 没有它，空灵就变成了寡淡。
# acc_hue 限定点缀的 LCH 色相区间。只限色系不够——"红"里既有朱红(H≈35)
# 也有品红/紫荆红(H≈0 或 350+)，后者是化学染料的现代红，出现在故宫配色里立刻失真。
SCENES = {
    "故宫": dict(mood="艳", families=("红", "黄", "白"),
               dom_families=("白", "黄"), accent_break=("红",),
               sec_hue=((20, 80), (70, 110)),  # 朱红/土黄，不要品红
               acc_hue=((20, 70),), wuxing=("火", "土", "金"),
               hint="朱红墙、琉璃黄瓦、汉白玉栏"),
    "青花": dict(mood="清冷", families=("蓝", "白", "青"), accent_break=(),
               wuxing=("水", "金", "木"), hint="甜白釉上的青花蓝，只有青与白"),
    "水墨": dict(mood="空灵", families=("灰", "白", "黑"), accent_break=("红",),
               acc_hue=((15, 55),), acc_chroma=(28, 999),
               wuxing=("水", "金"), hint="墨分五色落在宣纸上，一枚朱红印即是全部的彩"),
    "敦煌": dict(mood="浓烈", families=("棕", "绿", "蓝", "黄"), accent_break=("红", "黄"),
               wuxing=("土", "木"), hint="土红墙壁、石青石绿、沥粉贴金"),
    "宋瓷": dict(mood="雅", families=("青", "绿", "白", "灰"), accent_break=(),
               wuxing=("木", "金", "水"), hint="汝窑天青、粉青、梅子青，不施彩"),
    "唐三彩": dict(mood="艳", families=("黄", "绿", "白", "棕"), accent_break=("绿", "棕"),
                 wuxing=("土", "木", "金"), hint="黄釉绿釉白釉褐釉"),
    "江南": dict(mood="雅", families=("绿", "白", "粉", "灰"), accent_break=("红", "粉"),
               wuxing=("木", "金", "火"), hint="黛瓦、月白墙、竹青，一点胭脂"),
    "漆器": dict(mood="浓烈", families=("红", "黑", "黄"), accent_break=("红", "黄"),
               wuxing=("火", "水", "土"), hint="黑地朱纹或朱地黑纹，点金"),
    "年画": dict(mood="市井", families=("红", "黄", "绿"), accent_break=("绿", "红"),
               wuxing=("火", "土", "木"), hint="大红大绿，民间不怕相克"),
}

# 媒材：同一套三色，四套约束。UI 以对比度为硬闸；海报/服装不因 3:1 偷换文化色；
# 空间的主场是墙，必须低彩。口令给交付用，不改角色分工本身。
MEDIA = {
    "ui": dict(
        need_text=True, min_text_ratio=4.5, wall_max_chroma=None,
        labels=("页面背景", "卡片与导航", "主按钮"),
        note="界面：正文必须 4.5:1，点缀只给可点元件，不要铺成顶栏",
    ),
    "poster": dict(
        need_text=False, min_text_ratio=3.0, wall_max_chroma=None,
        labels=("纸地", "主体色块", "印章与题名"),
        note="海报：文化色优先，长文对比不作硬约束；点缀是印章不是色带",
    ),
    "fashion": dict(
        need_text=False, min_text_ratio=0.0, wall_max_chroma=None,
        labels=("主面料", "缘饰里衬", "盘扣绣佩"),
        note="服装：衣/缘/结，不做 WCAG；高彩只走结与绣",
    ),
    "interior": dict(
        need_text=False, min_text_ratio=3.0, wall_max_chroma=28.0,
        labels=("墙面地面", "家具柜门", "摆件或一扇门"),
        note="空间：墙面必须低彩，家具是结构色，摆件才是点缀",
    ),
}


@dataclass
class Color:
    """色库中的一条记录，附带方便配色计算的缓存。"""
    rec: dict

    def __getattr__(self, key):
        return self.rec[key]

    def get(self, key, default=None):
        return self.rec.get(key, default)

    @cached_property
    def lab(self) -> tuple[float, float, float]:
        return tuple(self.rec["lab"])  # type: ignore[return-value]

    @cached_property
    def lch(self) -> tuple[float, float, float]:
        return tuple(self.rec["lch"])  # type: ignore[return-value]

    @property
    def L(self) -> float:
        return self.lch[0]

    @property
    def C(self) -> float:
        return self.lch[1]

    @property
    def H(self) -> float:
        return self.lch[2]


class Catalog:
    def __init__(self, catalog_path: Path = CATALOG_PATH, aliases_path: Path = ALIASES_PATH):
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.colors = [Color(r) for r in data["colors"]]
        self.by_name = {c.name: c for c in self.colors}
        self.by_pinyin = {c.pinyin: c for c in self.colors}
        self.by_hex = {c.hex.lower(): c for c in self.colors}
        self.aliases: dict[str, dict] = {}
        if aliases_path.exists():
            payload = json.loads(aliases_path.read_text(encoding="utf-8"))
            self.aliases = {a["alias"]: a for a in payload["aliases"]}
        self.curated: list[dict] = []
        if CURATED_PATH.exists():
            self.curated = json.loads(CURATED_PATH.read_text(encoding="utf-8"))["palettes"]

    def resolve(self, query: str) -> Color | None:
        """名字 / 拼音 / hex / 别名 -> 色库条目。"""
        q = query.strip()
        if q.startswith("#"):
            return self.by_hex.get(q.lower())
        if q in self.by_name:
            return self.by_name[q]
        if q in self.by_pinyin:
            return self.by_pinyin[q]
        if q in self.aliases:
            return self.by_name[self.aliases[q]["target"]]
        # 宽松：去空格、简体别名已覆盖；再试包含匹配唯一时返回
        hits = [c for c in self.colors if q in c.name]
        if len(hits) == 1:
            return hits[0]
        return None

    def search(self, query: str = "", family: str | None = None, wuxing: str | None = None,
               season: str | None = None, role: str | None = None,
               temperature: str | None = None, tone: str | None = None,
               chroma_band: str | None = None, limit: int = 20) -> list[Color]:
        q = query.strip()
        out: list[Color] = []
        for c in self.colors:
            if family and c.family != family:
                continue
            if wuxing and c.wuxing != wuxing:
                continue
            if season and c.season != season:
                continue
            if role and role not in c.roles:
                continue
            if temperature and c.temperature != temperature:
                continue
            if tone and c.tone != tone:
                continue
            if chroma_band and c.chroma_band != chroma_band:
                continue
            if q and q not in c.name and q not in c.pinyin and q.lower() not in c.hex:
                continue
            out.append(c)
        return out[:limit]

    def nearest(self, hex_value: str, n: int = 5, pool: Iterable[Color] | None = None) -> list[tuple[Color, float]]:
        pool = list(pool) if pool is not None else self.colors
        ranked = sorted(pool, key=lambda c: ck.delta_e_hex(hex_value, c.hex))
        return [(c, ck.delta_e_hex(hex_value, c.hex)) for c in ranked[:n]]

    def snap(self, hex_value: str) -> Color:
        """把任意 hex 吸附到色库最近色。这是『永不发明新色』的入口。"""
        return self.nearest(hex_value, 1)[0][0]


def contrast(a: Color, b: Color) -> float:
    return ck.contrast_ratio(tuple(a.rgb), tuple(b.rgb))  # type: ignore[arg-type]


def delta_e(a: Color, b: Color) -> float:
    return ck.delta_e_2000(a.lab, b.lab)


def wuxing_relation(a: str, b: str) -> str:
    if a == b:
        return "同"
    if tx.WUXING_SHENG.get(a) == b or tx.WUXING_SHENG.get(b) == a:
        return "生"
    if tx.WUXING_KE.get(a) == b or tx.WUXING_KE.get(b) == a:
        return "克"
    return "平"


# ---------------------------------------------------------------- 评分

def _clip01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def score_trio(dom: Color, sec: Color, acc: Color, mood: str | None = None) -> dict:
    """给一组三色打分，返回总分和分项。每项 0-1，再按 SCORE_WEIGHTS 加权。"""
    parts: dict[str, float] = {}

    # 1. 点缀显著度：点缀必须"跳出来"，但跳法有两种——更艳，或更深/更浅。
    #    早先只算彩度差，于是青花（雪白/群青/鷃蓝）被判低分：它的点缀是最深的
    #    钩线蓝，靠明度跳而非彩度跳。故宫（汉白玉/朱红/姜黄）同样被误伤。
    #    取两种跳法的较强者，才符合真实的视觉层级。
    weight_dom, weight_sec, weight_acc = 0.6 * (dom.C + 8), 0.3 * (sec.C + 8), 0.1 * (acc.C + 8)
    chroma_jump = (acc.C - dom.C) / 55.0
    light_jump = abs(acc.L - dom.L) / 55.0
    salience = max(chroma_jump, light_jump)
    parts["chroma_hierarchy"] = _clip01(0.25 + salience * 0.75)
    # 点缀既不比主色艳、也不比主色深浅分明 —— 真正的失败
    if acc.C <= dom.C + 3 and abs(acc.L - dom.L) < 12:
        parts["chroma_hierarchy"] *= 0.3
    # 大面积高彩：主场是背景，铺高彩会视觉过载（深底方案除外，深底本就压得住）
    if dom.C > 45 and "深底" not in dom.roles:
        parts["chroma_hierarchy"] *= 0.45
    # 辅色不该比点缀"更抢"：单位面积显著度上，点缀应强于结构
    sec_salience = max((sec.C - dom.C) / 55.0, abs(sec.L - dom.L) / 55.0)
    if sec_salience > salience * 1.6 and sec.C > 35:
        parts["chroma_hierarchy"] *= 0.65

    # 2. 明度阶梯：主辅至少 ΔL* 8，点缀与主色至少 ΔL* 12 或 ΔC 25
    d_ls = abs(dom.L - sec.L)
    d_la = abs(dom.L - acc.L)
    parts["lightness_ladder"] = _clip01((min(d_ls, 24) / 24) * 0.5 + (min(max(d_la, acc.C - dom.C), 40) / 40) * 0.5)

    # 3. 冷暖：主辅同向（或都中性）最稳，点缀可以反转作为对比。
    #    但允许相克的氛围（浓烈/市井/艳）本就以冷暖对撞为手法——敦煌的土红墙
    #    配石青就是暖冷直接相撞，不该按"底色不统一"扣分。
    w_dom, w_sec, w_acc = dom.warmth, sec.warmth, acc.warmth
    mood_cfg_early = MOODS.get(mood or "", {})
    clash_ok = bool(mood_cfg_early.get("allow_ke"))
    same_sign = (w_dom * w_sec) >= 0 or abs(w_dom) < 0.18 or abs(w_sec) < 0.18
    if same_sign:
        parts["undertone"] = 0.85
    else:
        parts["undertone"] = 0.7 if clash_ok else 0.25
    if abs(w_dom) < 0.18 and abs(w_sec) < 0.18:
        parts["undertone"] = 0.95  # 两个中性最稳

    # 4. 色相关系
    dh_ds = ck.hue_delta(dom.H, sec.H)
    dh_da = ck.hue_delta(dom.H, acc.H)
    # 任一方近无彩时，色相角是数值噪声（雪白的 H 毫无意义），不能拿来比色相关系。
    # 纸白配任何颜色都成立，这正是"素底"在中国配色里的地位。
    if min(dom.C, sec.C) < 10:
        parts["hue_relation"] = 0.9
    elif dh_ds <= 25:
        parts["hue_relation"] = 0.95  # 同族/邻近，最稳
    elif dh_ds <= 60:
        parts["hue_relation"] = 0.8
    elif dh_ds >= 150:
        parts["hue_relation"] = 0.45  # 主辅互补太冲，只在市井/浓烈下可接受
    else:
        parts["hue_relation"] = 0.6
    # 点缀在 150-180°（互补点缀）或 25-50°（邻近点缀）都好；0° 则点缀没存在感
    if acc.C >= 20:
        if 140 <= dh_da <= 180 or 20 <= dh_da <= 70:
            parts["hue_relation"] = min(1.0, parts["hue_relation"] + 0.12)
        if dh_da < 12 and acc.C - dom.C < 15:
            parts["hue_relation"] *= 0.6
    # 荆浩《画说》：「红间黄秋叶坠，红间绿花簇簇，青间紫不如死，粉笼黄胜增光。」
    # 青（蓝绿）配紫是中国配色里被点名的死局，数码蓝配洋红同理。
    def _is_qing(c: Color) -> bool:
        return c.family in ("青", "蓝", "绿") and 140 <= c.H <= 280 and c.C >= 18
    def _is_zi(c: Color) -> bool:
        return (c.family == "紫" or 290 <= c.H <= 340) and c.C >= 18
    trio = (dom, sec, acc)
    if any(_is_qing(x) for x in trio) and any(_is_zi(x) for x in trio):
        parts["hue_relation"] *= 0.45
    # 红间绿：市井/年画是「花簇簇」，其余场合等量会俗，只在 allow_ke 下不罚
    def _is_hong(c: Color) -> bool:
        return c.family == "红" and c.C >= 30
    def _is_lv(c: Color) -> bool:
        return c.family == "绿" and c.C >= 30
    if any(_is_hong(x) for x in trio) and any(_is_lv(x) for x in trio):
        if not clash_ok:
            parts["hue_relation"] *= 0.7

    # 5. 对比：必须能在主色上放下可读文字
    ink_on_dom = max(dom.contrast_white, dom.contrast_black)  # 自身相对纯白/纯黑
    # 更精确：三色两两
    cs = contrast(dom, sec)
    ca = contrast(dom, acc)
    parts["contrast"] = 0.0
    if ink_on_dom >= 4.5:
        parts["contrast"] += 0.5
    elif ink_on_dom >= 3.0:
        parts["contrast"] += 0.25
    parts["contrast"] += 0.25 if cs >= 1.4 else 0.05
    parts["contrast"] += 0.25 if ca >= 2.0 else 0.05  # 点缀必须看得见
    parts["contrast"] = _clip01(parts["contrast"])

    # 6. 文化：五行
    rel_ds = wuxing_relation(dom.wuxing, sec.wuxing)
    rel_da = wuxing_relation(dom.wuxing, acc.wuxing)
    cult = 0.55
    # 近无彩的主色（纸、绢、宣、素墙）在文化上是"地"而非"色"，不参与相生相克。
    # 否则甜白釉配青花会因"金克木"被扣分，而那恰是中国最经典的配色。
    ground = dom.C < 12
    if ground:
        cult = 0.75
    elif rel_ds == "生":
        cult += 0.2
    elif rel_ds == "同":
        cult += 0.1
    elif rel_ds == "克":
        cult -= 0.25
    if rel_da == "生":
        cult += 0.1
    elif rel_da == "克":
        cult -= 0.05  # 点缀相克其实常见（朱印钤在墨上）
    mood_cfg = MOODS.get(mood or "", {})
    if mood_cfg.get("allow_ke") and rel_ds == "克":
        cult += 0.3  # 市井/浓烈允许相克，还加分
    parts["cultural"] = _clip01(cult)

    # 7. 独特性：三色两两 ΔE
    e_ds, e_da, e_sa = delta_e(dom, sec), delta_e(dom, acc), delta_e(sec, acc)
    parts["uniqueness"] = _clip01(min(e_ds, e_da, e_sa) / 25.0)
    if min(e_ds, e_da, e_sa) < 8:
        parts["uniqueness"] *= 0.3  # 几乎是同一个色

    # 8. 色盲：红绿点缀在主色上，模拟后 ΔE 仍 > 12
    def _cvd_ok(kind: str) -> bool:
        a = ck.simulate_cvd(tuple(dom.rgb), kind)  # type: ignore[arg-type]
        b = ck.simulate_cvd(tuple(acc.rgb), kind)  # type: ignore[arg-type]
        return ck.delta_e_2000(ck.rgb_to_lab(a), ck.rgb_to_lab(b)) >= 12
    cvd_hits = sum(_cvd_ok(k) for k in ("protanopia", "deuteranopia", "tritanopia"))
    parts["cvd"] = cvd_hits / 3.0

    total = sum(SCORE_WEIGHTS[k] * parts[k] for k in SCORE_WEIGHTS)
    max_total = sum(SCORE_WEIGHTS.values())
    return {
        "total": round(100 * total / max_total, 1),
        "parts": {k: round(v, 3) for k, v in parts.items()},
        "metrics": {
            "delta_e": {"dom-sec": round(e_ds, 1), "dom-acc": round(e_da, 1), "sec-acc": round(e_sa, 1)},
            "hue_delta": {"dom-sec": round(dh_ds, 1), "dom-acc": round(dh_da, 1)},
            "contrast": {"dom-sec": round(cs, 2), "dom-acc": round(ca, 2)},
            "wuxing": {"dom-sec": rel_ds, "dom-acc": rel_da},
            "visual_weight": {"dominant": round(weight_dom, 1), "secondary": round(weight_sec, 1), "accent": round(weight_acc, 1)},
        },
    }


# ---------------------------------------------------------------- 候选池

def _has_role(c: Color, roles: tuple[str, ...] | None) -> bool:
    if not roles:
        return True
    return any(r in c.roles for r in roles)


def dominant_pool(cat: Catalog, mood: str | None = None, seed: Color | None = None,
                  families: tuple[str, ...] | None = None, dark: bool = False) -> list[Color]:
    """主场候选：大面积必须安静。深色氛围走深底，其余走浅底/纸感。

    dark=True 时强制深底/墨色做场，不整页反相——浅色方案的纸地换成燕颔蓝、
    豆沙、苷蓝绿一类，点缀仍然可以是朱红或金。
    """
    cfg = MOODS.get(mood or "", {})
    roles = ("深底", "墨色") if dark else cfg.get("dom")
    pool = [c for c in cat.colors if _has_role(c, roles)]
    if not pool:
        pool = [c for c in cat.colors if "纸感" in c.roles or "浅底" in c.roles or "深底" in c.roles]
    if families:
        narrowed = [c for c in pool if c.family in families]
        # 暗色 + 浅色系场景（青花的白）时，白系里没有深底，放宽到同场景的蓝/青/灰
        if not narrowed and dark:
            narrowed = [c for c in pool if c.family in ("蓝", "青", "灰", "黑", "棕")]
        if narrowed:
            pool = narrowed
    prefer = cfg.get("prefer_temp")
    if prefer == "冷":
        pool = sorted(pool, key=lambda c: c.warmth)
    elif prefer == "暖":
        pool = sorted(pool, key=lambda c: -c.warmth)
    if dark:
        pool = sorted(pool, key=lambda c: (c.L, c.C))
    if seed is not None:
        # 有种子时，主场取与种子同冷暖、低彩的近亲，或种子自己（若它够安静）
        if seed.C <= 32 and ((not dark and seed.L >= 78) or seed.L <= 28):
            return [seed] + [c for c in pool if c.name != seed.name][:24]
        undertone = [c for c in pool if (c.warmth * seed.warmth) >= 0 or abs(c.warmth) < 0.2]
        target_l = 12.0 if dark else (100.0 if seed.L < 50 else 0.0)
        undertone.sort(key=lambda c: abs(c.H - seed.H) if min(c.C, seed.C) > 8 else abs(c.L - target_l))
        return undertone[:28] or pool[:28]
    return pool[:40]


def secondary_pool(cat: Catalog, dom: Color, mood: str | None = None,
                   families: tuple[str, ...] | None = None,
                   scene: str | None = None) -> list[Color]:
    cfg = MOODS.get(mood or "", {})
    scene_cfg = SCENES.get(scene or "", {})
    cmin, cmax = cfg.get("sec_chroma", (0, 40))
    sec_tones = cfg.get("sec_tone")
    hue_ranges = scene_cfg.get("sec_hue")
    pool = []
    for c in cat.colors:
        if c.name == dom.name:
            continue
        if not (cmin <= c.C <= cmax):
            continue
        if sec_tones and c.tone not in sec_tones:
            continue
        if hue_ranges and c.C >= 18 and not any(lo <= c.H <= hi for lo, hi in hue_ranges):
            continue
        if abs(c.L - dom.L) < 6 and ck.hue_delta(c.H, dom.H) < 12 and abs(c.C - dom.C) < 8:
            continue  # 几乎重复
        if delta_e(c, dom) < 8:
            continue
        pool.append(c)
    if families:
        narrowed = [c for c in pool if c.family in families or c.family in ("灰", "白", "棕")]
        if len(narrowed) >= 8:
            pool = narrowed
    # 结构色的正确定位是"中间层"：与主色拉开一个台阶即可，不是拉到最远。
    # 早先按 -abs(ΔL) 排序，结果每套辅色都挑到近黑的极深色——
    # 那是文字色的位置，不是结构色该有的分量。理想 ΔL* 在 18-45 之间。
    def sec_key(c: Color) -> tuple:
        d_l = abs(c.L - dom.L)
        ladder = 0 if 16 <= d_l <= 48 else (1 if 10 <= d_l <= 62 else 2)
        undertone = 0 if (c.warmth * dom.warmth) >= -0.05 or abs(c.warmth) < 0.18 else 1
        hue_ok = 0 if ck.hue_delta(c.H, dom.H) <= 55 or min(c.C, dom.C) < 10 else 1
        return (ladder, undertone, hue_ok, -c.C)
    pool.sort(key=sec_key)
    return pool[:36]


def accent_pool(cat: Catalog, dom: Color, sec: Color, mood: str | None = None,
                families: tuple[str, ...] | None = None,
                scene: str | None = None) -> list[Color]:
    cfg = MOODS.get(mood or "", {})
    scene_cfg = SCENES.get(scene or "", {})
    cmin, cmax = scene_cfg.get("acc_chroma") or cfg.get("acc_chroma", (18, 999))
    tones = cfg.get("acc_tone")
    hue_ranges = scene_cfg.get("acc_hue")
    pool = []
    for c in cat.colors:
        if c.name in (dom.name, sec.name):
            continue
        if not (cmin <= c.C <= cmax):
            continue
        if tones and c.tone not in tones:
            continue
        if hue_ranges and not any(lo <= c.H <= hi for lo, hi in hue_ranges):
            continue
        if delta_e(c, dom) < 12 or delta_e(c, sec) < 10:
            continue
        if contrast(c, dom) < 1.6:  # 点缀贴在主色上看不见
            continue
        pool.append(c)
    # 场景限定色系时，点缀必须留在场景语汇内（含该场景允许的破色）。
    # 否则青花会被红棕点缀抢走——青花的规矩就是只有青与白。
    if families:
        allowed = set(families) | set(scene_cfg.get("accent_break") or ())
        inside = [c for c in pool if c.family in allowed]
        if len(inside) >= 4:
            pool = inside
    # 点缀要"跳得出来"：先看彩度，再要求与主色有色相差，但不必是极彩。
    # 极彩优先会让每套方案都收敛到同一个银朱，多样性归零。
    def acc_key(c: Color) -> tuple:
        dh = ck.hue_delta(c.H, dom.H)
        band = 0 if 20 <= dh <= 80 or 135 <= dh <= 180 else 1
        return (band, -c.C)
    pool.sort(key=acc_key)
    return pool[:40]


# ---------------------------------------------------------------- 生成

@dataclass
class Palette:
    dominant: Color
    secondary: Color
    accent: Color
    score: dict
    mood: str | None = None
    scene: str | None = None
    rationale: list[str] = field(default_factory=list)
    curated_name: str | None = None
    dark: bool = False
    media: str | None = None

    @property
    def trio(self) -> tuple[Color, Color, Color]:
        return self.dominant, self.secondary, self.accent


def curated_palettes(cat: Catalog, mood: str | None = None, scene: str | None = None,
                     seed: Color | None = None, dark: bool = False) -> list[Palette]:
    """取手选方案并按同一套评分打分，使其能与算法方案同场排序。"""
    out: list[Palette] = []
    for entry in cat.curated:
        if scene and entry.get("scene") != scene:
            continue
        if mood and entry.get("mood") != mood and not scene:
            continue
        try:
            dom, sec, acc = (cat.by_name[entry[k]] for k in ("dominant", "secondary", "accent"))
        except KeyError:
            continue
        if seed is not None and seed.name not in (dom.name, sec.name, acc.name):
            continue
        if dark and dom.L > 40:
            continue  # 浅色手选不能硬反相成暗色方案
        sc = score_trio(dom, sec, acc, entry.get("mood"))
        pal = Palette(dom, sec, acc, sc, entry.get("mood"), entry.get("scene"), dark=dark)
        pal.rationale = [f"手选方案「{entry['name']}」：{entry['source']}",
                         f"注意：{entry['caution']}"] + _rationale(pal)[:4]
        pal.curated_name = entry["name"]
        out.append(pal)
    out.sort(key=lambda p: -p.score["total"])
    return out


def generate(cat: Catalog, mood: str | None = None, scene: str | None = None,
             seed: str | Color | None = None, n: int = 5,
             dark: bool = False, media: str | None = None) -> list[Palette]:
    """主入口：氛围 / 场景 / 种子色 -> 若干套三色配色。

    手选方案优先出现（经过文化校对），算法方案补足数量与多样性。
    dark 强制深底做场，不整页反相。media 只改约束与口令，不改角色。
    """
    families = None
    if scene and scene in SCENES:
        mood = mood or SCENES[scene]["mood"]
        families = SCENES[scene].get("families")
    seed_color = None
    if isinstance(seed, Color):
        seed_color = seed
    elif isinstance(seed, str) and seed:
        seed_color = cat.resolve(seed) or cat.snap(seed) if seed.startswith("#") else cat.resolve(seed)

    curated = curated_palettes(cat, mood, scene, seed_color, dark=dark)
    dom_families = None
    if scene and scene in SCENES:
        dom_families = SCENES[scene].get("dom_families") or families
    if dark:
        # 暗色场不应再被「故宫主场必须是白/黄」绑死，改走同场景的深色家族
        dom_families = None
    doms = dominant_pool(cat, mood, seed_color, dom_families, dark=dark)
    media_cfg = MEDIA.get(media or "", {})
    wall_c = media_cfg.get("wall_max_chroma")
    if wall_c is not None:
        walled = [c for c in doms if c.C <= wall_c]
        if walled:
            doms = walled
    results: list[Palette] = []
    seen: set[tuple[str, str, str]] = set()

    for dom in doms[:12]:
        secs = secondary_pool(cat, dom, mood, families, scene)
        for sec in secs[:8]:
            accs = accent_pool(cat, dom, sec, mood, families, scene)
            best_for_pair: Palette | None = None
            for acc in accs[:10]:
                key = (dom.name, sec.name, acc.name)
                if key in seen:
                    continue
                sc = score_trio(dom, sec, acc, mood)
                pal = Palette(dom, sec, acc, sc, mood, scene, dark=dark, media=media)
                if best_for_pair is None or sc["total"] > best_for_pair.score["total"]:
                    best_for_pair = pal
            if best_for_pair and best_for_pair.score["total"] >= 48:
                seen.add((best_for_pair.dominant.name, best_for_pair.secondary.name, best_for_pair.accent.name))
                best_for_pair.rationale = _rationale(best_for_pair)
                results.append(best_for_pair)

    results.sort(key=lambda p: -p.score["total"])
    picked: list[Palette] = []
    dom_count: dict[str, int] = {}
    acc_count: dict[str, int] = {}
    for p in curated + results:
        p.dark = dark
        p.media = media
        if media:
            extra = _media_lines(p, cat)
            p.rationale = list(p.rationale) + extra
        key = (p.dominant.name, p.secondary.name, p.accent.name)
        if any((q.dominant.name, q.secondary.name, q.accent.name) == key for q in picked):
            continue
        if dom_count.get(p.dominant.name, 0) >= 2:
            continue
        if acc_count.get(p.accent.name, 0) >= 3:
            continue
        if media_cfg.get("need_text"):
            text = pick_text(cat, p.dominant, min_ratio=media_cfg.get("min_text_ratio") or 4.5)
            if contrast(text, p.dominant) < (media_cfg.get("min_text_ratio") or 4.5):
                continue
        picked.append(p)
        dom_count[p.dominant.name] = dom_count.get(p.dominant.name, 0) + 1
        acc_count[p.accent.name] = acc_count.get(p.accent.name, 0) + 1
        if len(picked) >= n:
            break
    return picked


def complete_pair(cat: Catalog, a: str | Color, b: str | Color, mood: str | None = None) -> list[Palette]:
    """两色补全：按明度/彩度决定谁当主场/结构/点缀，再补第三个。"""
    ca = a if isinstance(a, Color) else cat.resolve(str(a))
    cb = b if isinstance(b, Color) else cat.resolve(str(b))
    if ca is None or cb is None:
        raise ValueError("找不到指定的颜色，请用色库中的中文名、拼音或 hex")
    # 更安静、更浅（或同样深但更灰）的当 60
    def quiet_key(c: Color) -> tuple:
        return (0 if c.C < 28 else 1, 0 if c.L >= 78 or c.L <= 26 else 1, c.C, -c.L if c.L >= 50 else c.L)
    first, second = (ca, cb) if quiet_key(ca) <= quiet_key(cb) else (cb, ca)
    # first 做 60，second 可能是 30 或 10
    out: list[Palette] = []
    if second.C >= 40:
        # second 当点缀，补一个 30
        for sec in secondary_pool(cat, first, mood)[:12]:
            sc = score_trio(first, sec, second, mood)
            pal = Palette(first, sec, second, sc, mood)
            pal.rationale = _rationale(pal)
            out.append(pal)
    else:
        # second 当 30，补一个 10
        for acc in accent_pool(cat, first, second, mood)[:12]:
            sc = score_trio(first, second, acc, mood)
            pal = Palette(first, second, acc, sc, mood)
            pal.rationale = _rationale(pal)
            out.append(pal)
    out.sort(key=lambda p: -p.score["total"])
    return out[:5]


def _rationale(p: Palette) -> list[str]:
    m = p.score["metrics"]
    lines = [
        f"主场 {p.dominant.name}（{p.dominant.family}/{p.dominant.wuxing}，{p.dominant.chroma_band}）铺大面积",
        f"结构 {p.secondary.name}（{p.secondary.family}/{p.secondary.wuxing}）承托，与主场 ΔE {m['delta_e']['dom-sec']}、色相差 {m['hue_delta']['dom-sec']}°",
        f"点缀 {p.accent.name}（{p.accent.family}/{p.accent.wuxing}，{p.accent.chroma_band}）作标点，对比 {m['contrast']['dom-acc']}:1",
        f"五行 主场-结构 {m['wuxing']['dom-sec']}，主场-点缀 {m['wuxing']['dom-acc']}；视觉重量 主场 {m['visual_weight']['dominant']} 结构 {m['visual_weight']['secondary']} 点缀 {m['visual_weight']['accent']}",
    ]
    if p.mood:
        lines.append(f"氛围「{p.mood}」：{MOODS[p.mood]['note']}")
    if p.scene:
        lines.append(f"场景「{p.scene}」：{SCENES[p.scene]['hint']}")
    if p.dark:
        lines.append(f"暗色方案：场取深底 {p.dominant.name}（L*{p.dominant.L:.0f}），不是浅色方案反相")
    return lines


def _media_lines(p: Palette, cat: Catalog) -> list[str]:
    """媒材口令：把 60/30/10 翻译成该媒材的具体位置。"""
    cfg = MEDIA.get(p.media or "", {})
    if not cfg:
        return []
    a, b, c = cfg["labels"]
    lines = [f"媒材「{p.media}」：{a}={p.dominant.name}，{b}={p.secondary.name}，{c}={p.accent.name}",
             cfg["note"]]
    if cfg.get("need_text"):
        text = pick_text(cat, p.dominant, min_ratio=cfg.get("min_text_ratio") or 4.5)
        lines.append(f"正文 {text.name} {text.hex} 对比 {contrast(text, p.dominant):.2f}:1")
    return lines


# ---------------------------------------------------------------- 文字色与 token

def pick_text(cat: Catalog, bg: Color, min_ratio: float = 4.5) -> Color:
    """从色库里挑一个能在给定背景上达到对比度的文字色。

    浅底优先墨色（深、低彩），深底优先纸感。不只看对比数字——
    纯黑 (#000) 在米色上对比够高但发死，战舰灰/深灰蓝更像墨。
    """
    want_dark = bg.L >= 55
    pool = [c for c in cat.colors if contrast(c, bg) >= min_ratio]
    if want_dark:
        pool = [c for c in pool if c.L < bg.L - 8]
        pool.sort(key=lambda c: (0 if "墨色" in c.roles else 1, c.C, -contrast(c, bg)))
    else:
        pool = [c for c in pool if c.L > bg.L + 8]
        pool.sort(key=lambda c: (0 if "纸感" in c.roles or "浅底" in c.roles else 1, c.C, -contrast(c, bg)))
    return pool[0] if pool else (cat.by_name.get("燕颔蓝") or cat.colors[0])


def pick_muted(cat: Catalog, bg: Color, text: Color) -> Color:
    """次级文字：比正文轻，但仍然是文字，所以必须 ≥4.5:1。

    早先取 3:1–4.5:1，那是 WCAG 给大字和部件的额度。次级说明、时间戳、
    表单帮助文字都是正文尺寸，落在 3.x 就是不合规——弱化要靠明度而非违规。
    """
    lo, hi = 4.5, 9.0
    pool = [c for c in cat.colors
            if lo <= contrast(c, bg) < hi and c.name not in (bg.name, text.name)]
    if not pool:
        pool = [c for c in cat.colors
                if contrast(c, bg) >= lo and c.name not in (bg.name, text.name)]
    # 次级文字必须是墨/灰一类安静色。按对比贴近 5.5 会误把龙睛鱼红
    # （高彩橙、碰巧 5.5:1）当成 muted——那是点缀不是字。
    def muted_key(c: Color) -> tuple:
        quiet = 0 if c.chroma_band in ("无彩", "微彩", "低彩") else 1
        family = 0 if c.family in ("灰", "黑", "白", "棕") else 1
        return (quiet, family, abs(contrast(c, bg) - 5.5))
    pool.sort(key=muted_key)
    return pool[0] if pool else text


def _snap_away(cat: Catalog, bg: Color, target_hex: str, min_de: float = 4.0,
               min_contrast: float = 0.0, chroma_cap: float | None = None) -> Color:
    """吸附到色库，但不要吸回自己，并满足最小色差 / 对比。"""
    snapped = cat.snap(target_hex)
    if snapped.name != bg.name and delta_e(snapped, bg) >= min_de:
        if min_contrast <= 0 or contrast(snapped, bg) >= min_contrast:
            if chroma_cap is None or snapped.C <= chroma_cap:
                return snapped
    cands = [c for c in cat.colors
             if c.name != bg.name
             and delta_e(c, bg) >= min_de
             and (min_contrast <= 0 or contrast(c, bg) >= min_contrast)
             and (chroma_cap is None or c.C <= chroma_cap)]
    cands.sort(key=lambda c: (delta_e(c, cat.snap(target_hex)), -contrast(c, bg)))
    return cands[0] if cands else snapped


# 语义色的色相窗口：family 不够——橄榄绿名义是绿、色相却是黄。
SEMANTIC_SPEC = {
    "success": dict(families=("绿", "青"), hue=((110, 170),), chroma_min=28,
                    fallback="孔雀绿"),
    "warning": dict(families=("黄", "橙"), hue=((70, 105),), chroma_min=35,
                    fallback="姜黄"),
    "error": dict(families=("红",), hue=((15, 50), (350, 360), (0, 15)), chroma_min=35,
                  fallback="苋菜红"),
    "info": dict(families=("蓝", "青"), hue=((220, 280),), chroma_min=25,
                 fallback="群青"),
}


def pick_semantic(cat: Catalog, bg: Color, kind: str) -> Color:
    """状态色：作徽章底，不要求和页面 3:1（黄在米色上几乎永远不够）。

    硬条件是徽章上能放下字（on-color ≥4.5:1），以及色相落在该语义的窗口里。
    """
    spec = SEMANTIC_SPEC[kind]
    fallback = cat.by_name.get(spec["fallback"]) or cat.colors[0]

    def in_hue(c: Color) -> bool:
        return any(lo <= c.H <= hi or (lo > hi and (c.H >= lo or c.H <= hi))
                   for lo, hi in spec["hue"])

    pool = [c for c in cat.colors
            if c.family in spec["families"] and in_hue(c) and c.C >= spec["chroma_min"]]
    usable = []
    for c in pool:
        on = pick_text(cat, c, min_ratio=4.5)
        if contrast(on, c) >= 4.5:
            usable.append(c)
    if not usable:
        return fallback
    # 浅底上宁可深一点的状态色（能看清形状），深底上宁可亮一点
    if bg.L >= 55:
        usable.sort(key=lambda c: (0 if contrast(c, bg) >= 3.0 else 1, -c.C, c.L))
    else:
        usable.sort(key=lambda c: (0 if c.L >= 45 else 1, -c.C))
    return usable[0]


def tokens(cat: Catalog, pal: Palette) -> dict:
    """把三色展开成一套 UI token。全部仍从色库吸附，不发明 hex。

    分层：
    - 结构：bg / surface / text / muted / border / border_strong
    - 品牌：secondary / accent / accent_fg / accent_hover / accent_active
    - 语义：success / warning / error / info（文化上：绿 / 黄 / 红 / 青）
    - 状态：disabled / ring
    """
    bg = pal.dominant
    text = pick_text(cat, bg)
    muted = pick_muted(cat, bg, text)
    # 面层必须和底分得开：浅底往下走、深底往上走，ΔE 至少 4
    surface_hex = ck.adjust(bg.hex, dl=(-8 if bg.L >= 70 else 10), dc=-2)
    surface = _snap_away(cat, bg, surface_hex, min_de=4.0, chroma_cap=28)
    # 装饰描边可以弱；输入框/按钮轮廓必须 ≥3:1（WCAG 1.4.11）
    border_hex = ck.adjust(bg.hex, dl=(-14 if bg.L >= 60 else 14), dc=2)
    border = _snap_away(cat, bg, border_hex, min_de=3.0, chroma_cap=22)
    border_strong = _snap_away(cat, bg, ck.adjust(bg.hex, dl=(-28 if bg.L >= 60 else 28), dc=6),
                              min_de=8.0, min_contrast=3.0, chroma_cap=36)
    accent_fg = pick_text(cat, pal.accent, min_ratio=4.5)
    # 交互态：悬停略提亮/加压，按下再压一档，全部吸回色库
    hover_dl = 6 if pal.accent.L < 70 else -8
    accent_hover = cat.snap(ck.adjust(pal.accent.hex, dl=hover_dl, dc=4))
    accent_active = cat.snap(ck.adjust(pal.accent.hex, dl=hover_dl * 1.6, dc=6))
    if accent_hover.name == pal.accent.name:
        accent_hover = _snap_away(cat, pal.accent, ck.adjust(pal.accent.hex, dl=hover_dl, dc=8), min_de=3)
    if accent_active.name in (pal.accent.name, accent_hover.name):
        accent_active = _snap_away(cat, pal.accent, ck.adjust(pal.accent.hex, dl=hover_dl * 1.8, dc=10), min_de=5)
    disabled = _snap_away(cat, bg, ck.adjust(bg.hex, dl=(-18 if bg.L >= 60 else 18), dc=-8),
                         min_de=6.0, chroma_cap=16)
    ring = pal.accent
    return {
        "bg": bg, "surface": surface, "text": text, "muted": muted,
        "border": border, "border_strong": border_strong,
        "secondary": pal.secondary, "accent": pal.accent,
        "accent_fg": accent_fg, "accent_hover": accent_hover, "accent_active": accent_active,
        "success": pick_semantic(cat, bg, "success"),
        "warning": pick_semantic(cat, bg, "warning"),
        "error": pick_semantic(cat, bg, "error"),
        "info": pick_semantic(cat, bg, "info"),
        "disabled": disabled, "ring": ring,
    }


def css_vars(tok: dict) -> str:
    lines = [":root {"]
    mapping = [
        ("bg", "bg"), ("surface", "surface"), ("text", "text"), ("muted", "muted"),
        ("border", "border"), ("border_strong", "border-strong"),
        ("secondary", "secondary"), ("accent", "accent"),
        ("accent_fg", "accent-fg"), ("accent_hover", "accent-hover"),
        ("accent_active", "accent-active"),
        ("success", "success"), ("warning", "warning"), ("error", "error"), ("info", "info"),
        ("disabled", "disabled"), ("ring", "ring"),
    ]
    for key, css in mapping:
        c: Color = tok[key]
        r, g, b = c.rgb
        lines.append(f"  --color-{css}: {c.hex};           /* {c.name} {c.pinyin} */")
        lines.append(f"  --color-{css}-rgb: {r}, {g}, {b};")
    lines.append("}")
    return "\n".join(lines)


def tailwind_extend(tok: dict) -> str:
    keys = ("bg", "surface", "text", "muted", "border", "border_strong",
            "secondary", "accent", "accent_fg", "accent_hover", "accent_active",
            "success", "warning", "error", "info", "disabled", "ring")
    body = ",\n".join(f'        "{k}": "{tok[k].hex}"' for k in keys)
    return "extend: {\n      colors: {\n        zhongguose: {\n" + body + "\n        }\n      }\n    }"


def visual_areas(pal: Palette) -> dict:
    """按感知能量反推建议铺色面积。

    角色分工不等于像素占比：高彩点缀铺得越大，观感越抢。
    Intensity ≈ 0.55·C/80 + 0.35·|ΔL|/50 + 0.10·暖度，面积 ∝ 目标份额 / Intensity。
    点缀被夹在一个很小的区间（下限保证可点，上限防止它变成色带）。
    """
    def intensity(c: Color, bg: Color) -> float:
        chroma = min((c.C / 80.0) * 1.6, 1.6)
        contrast_l = min(abs(c.L - bg.L) / 50.0, 1.6)
        warm = 0.5 * (1.0 + math.cos(math.radians(c.H - 55.0)))
        return 0.15 + 0.55 * chroma + 0.35 * contrast_l + 0.10 * warm

    i60 = intensity(pal.dominant, pal.dominant)
    i30 = intensity(pal.secondary, pal.dominant)
    i10 = intensity(pal.accent, pal.dominant)
    raw = (60 / i60, 30 / i30, 10 / i10)
    s = sum(raw)
    a60, a30, a10 = (x / s * 100 for x in raw)
    # 点缀按响度收面积；结构色必须仍能成「块」——能量公式会把朱红墙压得过小，
    # 那在角色上已经变成点缀。给结构留一个下限，剩下的全给主场。
    a10 = min(8.0, max(2.0, a10))
    a30 = min(32.0, max(16.0, a30))
    if a10 + a30 > 46.0:
        a30 = 46.0 - a10
    a60 = 100.0 - a10 - a30
    return {
        "pixel_pct": {"dominant": round(a60, 1), "secondary": round(a30, 1), "accent": round(a10, 1)},
        "intensity": {"dominant": round(i60, 3), "secondary": round(i30, 3), "accent": round(i10, 3)},
        "note": "pixel_pct 是建议铺色面积，非角色额度。主场最大、结构居中、点缀最小。",
    }


def as_dict(pal: Palette, tok: dict | None = None) -> dict:
    def pack(c: Color) -> dict:
        return dict(name=c.name, pinyin=c.pinyin, hex=c.hex, rgb=c.rgb, cmyk=c.cmyk,
                    family=c.family, wuxing=c.wuxing, season=c.season,
                    tone=c.tone, chroma_band=c.chroma_band, temperature=c.temperature)
    out = {
        "mood": pal.mood,
        "scene": pal.scene,
        "dark": pal.dark,
        "media": pal.media,
        "media_labels": list(MEDIA[pal.media]["labels"]) if pal.media in MEDIA else None,
        "score": pal.score["total"],
        "score_parts": pal.score["parts"],
        "metrics": pal.score["metrics"],
        "rationale": pal.rationale,
        "areas": visual_areas(pal),
        "dominant": pack(pal.dominant),
        "secondary": pack(pal.secondary),
        "accent": pack(pal.accent),
    }
    if tok:
        out["tokens"] = {k: pack(v) for k, v in tok.items()}
        out["css"] = css_vars(tok)
    return out
