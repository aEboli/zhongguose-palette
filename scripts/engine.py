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
# 深底安全区。库内没有纯黑，最深的一批里混着深牵牛紫这类紫黑；
# 不设上限地取「最深」会让所有暗色方案塌到同一块紫黑上。
DARK_GROUND_MAX_L = 22.0
DARK_GROUND_MAX_C = 20.0

# 语义色（success/warning/error/info）本就跨色族——绿/黄/红/青是它们的文化锁，
# 不属于场景色族。family lock 扫描必须放行这一组，否则每个场景都会误报。
SEMANTIC_TOKENS = ("success", "warning", "error", "info")
# 徽章上的字跟着徽章走。徽章色本身跨族，压在它上面的字只能在它的对比窗口里挑，
# 场景语汇管不到——把 *_fg 也放行，否则每个场景都会为这四个字误报出族。
SEMANTIC_FG_TOKENS = tuple(f"{k}_fg" for k in SEMANTIC_TOKENS)
NEUTRAL_FAMILIES = ("灰", "白", "黑")

# 留白型：这些氛围与场景以纸地为主体，结构色的面积下限要放宽，
# 否则「大面留白」「几乎是纸」只是文案，做不出来。
AIRY_MOODS = ("空灵",)
AIRY_SCENES = ("水墨", "宋瓷")

# 能当「金」的库内色。金黄 #f26b1f（H52.3）与金驼 #e46828（H51.4）实测落在橙区，
# 名字带金但不是金属色，和金莲花橙、金鱼紫一样要排除。
GOLD_NAMES = ("金盏黄", "金瓜黄", "金叶黄", "甘草黄", "姜黄")

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
    "艳": dict(dom=("浅底", "纸感", "面层", "彩底"), sec_chroma=(18, 55), acc_chroma=(45, 999),
              sec_tone=None, acc_tone=("中", "中浅", "中深"), allow_ke=True,
              prefer_temp="暖", note="宫廷、年画、漆器：点缀极彩，辅色也可稍艳"),
    "古朴": dict(dom=("面层", "描边", "深底"), sec_chroma=(8, 40), acc_chroma=(20, 70),
                sec_tone=None, acc_tone=("中深", "深", "极深"), allow_ke=False,
                prefer_temp="暖", note="低明度、土黄赭石，青铜、土陶、宣纸旧色"),
    "清冷": dict(dom=("浅底", "纸感"), sec_chroma=(4, 30), acc_chroma=(14, 50),
                sec_tone=None, acc_tone=("中", "中深"), allow_ke=False,
                prefer_temp="冷", note="宋瓷天青、月白、花青，冷调低彩"),
    "浓烈": dict(dom=("深底", "墨色", "彩底"), sec_chroma=(10, 45), acc_chroma=(40, 999),
                sec_tone=None, acc_tone=("中", "中浅", "中深"), allow_ke=True,
                prefer_temp=None, note="敦煌、漆器：深底托高彩点缀"),
    "空灵": dict(dom=("浅底",), sec_chroma=(0, 18), acc_chroma=(8, 40),
                sec_tone=("中深", "深", "极深"), acc_tone=("中深", "深", "极深"),
                allow_ke=False, prefer_temp="中性",
                note="水墨留白：主场几乎是纸，结构是墨，点缀是一枚印"),
    "市井": dict(dom=("浅底", "纸感", "面层", "彩底"), sec_chroma=(20, 60), acc_chroma=(45, 999),
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
    # 故宫有两种读法，并列而非主次：白石台基为局（汉白玉铺满、朱红成块），
    # 或宫墙为局（苋菜红一类深彩红铺满、白字压上、金只走线）。dom_families 因此
    # 必须含红——只留白黄，第二种读法根本进不了主场池。
    "故宫": dict(mood="艳", families=("红", "黄", "白"),
               dom_families=("白", "黄", "红"), accent_break=("红",),
               sec_hue=((20, 80), (70, 110)),  # 朱红/土黄，不要品红
               acc_hue=((20, 70), (70, 100)), wuxing=("火", "土", "金"),
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
    # 以下三个场景来自礼制而非工艺，各自解决一个既有场景解决不了的问题。
    # 祭天：故宫给的是"红墙黄瓦"的暖，但清代祭祀改色——《清史稿·舆服志》皇帝朝服
    # "色用明黄，惟祀天用蓝，朝日用红，夕月用月白"。这是唯一有原典背书的冷调宫廷方案，
    # 也是天坛祈年殿纯青琉璃瓦的同一套逻辑。青花只有青白两色，此处允许一点朝日红破色。
    "祭天": dict(mood="清冷", families=("蓝", "白", "青"), accent_break=("红",),
               dom_families=("白",), sec_hue=((190, 300),), acc_hue=((20, 70), (200, 290)),
               wuxing=("水", "金", "木"),
               hint="祀天用蓝、夕月用月白，一点朝日红；天坛祈年殿的纯青琉璃"),
    # 王府：琉璃瓦等第里"绿用于王府"这一级。故宫是明黄+朱红的极暖，王府降一等后
    # 变成绿瓦红墙，冷暖对撞反而更适合屏幕——绿可以做结构色，而明黄不能。
    "王府": dict(mood="艳", families=("绿", "白", "灰"), accent_break=("红",),
               dom_families=("白", "灰"), acc_hue=((20, 70),),
               wuxing=("木", "金", "火"),
               hint="绿琉璃瓦、朱漆门、汉白玉阶，比故宫降一等的中间调"),
    # 补服：《清史稿·舆服志》文武各品"补服，色用石青"。这是礼制里唯一的"深底+小徽章"
    # 范式：一件石青大袍，胸背各一方补。深色模式与"低调品牌+小面积金"的现成古典依据。
    "补服": dict(mood="浓烈", families=("蓝", "青", "灰"), accent_break=("黄",),
               dom_families=("蓝", "青", "黑"), sec_hue=((190, 300),), acc_hue=((70, 110),),
               wuxing=("水", "木", "土"),
               hint="石青地一方补子，深底托一枚金线徽章"),
}

# 媒材：同一套三色，四套约束。UI 以对比度为硬闸；海报/服装不因 3:1 偷换文化色；
# 空间的主场是墙，必须低彩。口令给交付用，不改角色分工本身。
MEDIA = {
    "ui": dict(
        need_text=True, min_text_ratio=4.5, wall_max_chroma=None,
        labels=("页面背景", "导航与图形", "主按钮"),
        note="界面：普通卡片用低彩面层；彩色块单独配字，按钮只占小面积",
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
    # 大面积高彩：主场是背景，铺高彩会视觉过载。两类例外：
    # 深底本就压得住；彩底是「深而彩的矿物色」，红墙、土壁、蓝釉本来就是整片铺的，
    # 白字压得住（contrast_white≥4.5）才拿到这个角色。
    # 没有彩底豁免时，苋菜红宫墙被压到 chroma_hierarchy 0.392、总分 84.5，
    # 而点缀几乎看不见的 汉白玉+朱红+姜黄（点缀对底仅 1.62:1）拿 93.1——
    # 评分在系统性奖励看不见的点缀。豁免后宫墙升到约 93.1。
    # 朱红/银朱/大红（中调高彩、白字 <4.5）拿不到彩底，仍被这条罚。
    if dom.C > 45 and "深底" not in dom.roles and "彩底" not in dom.roles:
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


def wants_chroma_ground(mood: str | None, dark: bool = False) -> bool:
    """这一档氛围是否要「彩底为局」这条读法。

    只认 MOODS[mood]['dom'] 里写没写彩底，不认颜色身上的角色标签。两者不等价：
    满天星紫 同时是 深底 与 彩底，它靠 深底 合法进 古朴 的主场池，但 古朴 的 dom
    里没有彩底——按标签判会让「留名额」和「彩底名额」在 古朴 上生效，把 84.6 分的
    紫底顶到第三位、挤掉 89.5 分的可可棕。雅/清冷/空灵 的池里没有彩底，按标签判
    恰好也是空操作，于是这个错只在 古朴 上露头。
    dark 走的是 (深底, 墨色)，不读 dom，深色方案本就由深底承担，不另留名额。
    """
    if dark:
        return False
    return "彩底" in (MOODS.get(mood or "", {}).get("dom") or ())


def _reserve_ground(pool: list[Color], limit: int, keep: int = 3) -> list[Color]:
    """截断主场池时给彩底留名额。

    单纯 `pool[:limit]` 会把彩底整个切掉——素底池通常远超 limit，而彩底按
    _ground_tier 排在它们之后。切掉之后「宫墙为局」只能靠手选方案存在，
    算法路径永远出不来，用户换个说法就再也见不到红底。
    """
    plain = [c for c in pool if _ground_tier(c) == 0]
    chromatic = [c for c in pool if _ground_tier(c) == 1]
    if not chromatic:
        return pool[:limit]
    # 彩底内部不按冷暖排——冷暖会把 夕阳红（白字仅 4.72:1）顶到 苋菜红 前面，
    # 而红墙的活儿是承住白字。先要留出余量（白字 ≥6:1），再要够彩。
    chromatic.sort(key=lambda c: (0 if c.contrast_white >= 6.0 else 1, -c.C))
    head = plain[:max(limit - keep, 1)]
    return head + chromatic[:keep]


def _ground_tier(c: Color) -> int:
    """素底 0、彩底 1。素底仍是缺省读法，彩底是第二读法。

    只当排序键的第一档，不做过滤：不压这一档的话，「艳 + 偏暖」会让落霞红、
    夕阳红一类把 doms[:12] 顶满，缺省行为从纸地变成红墙，那是把一个默认换成
    另一个默认，不是并列两种读法。
    """
    return 1 if "彩底" in c.roles else 0


def dominant_pool(cat: Catalog, mood: str | None = None, seed: Color | None = None,
                  families: tuple[str, ...] | None = None, dark: bool = False) -> list[Color]:
    """主场候选：大面积必须安静。深色氛围走深底，其余走浅底/纸感。

    dark=True 时强制深底/墨色做场，不整页反相——浅色方案的纸地换成燕颔蓝、
    豆沙、苷蓝绿一类，点缀仍然可以是朱红或金。
    """
    cfg = MOODS.get(mood or "", {})
    roles = ("深底", "墨色") if dark else cfg.get("dom")
    reserve = wants_chroma_ground(mood, dark)
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
    # 彩底压到排序末档，只在这一档真的要彩底时做——否则 古朴 的池会被连坐：
    # 石竹紫 同时是 深底 与 彩底，靠 深底 合法进池，压到末档后整池前移一位，
    # 暗驼棕 从第 13 位挤进 doms[:12]，古朴 的出色顺序无端改了。
    tier = _ground_tier if reserve else (lambda c: 0)
    if prefer == "冷":
        pool = sorted(pool, key=lambda c: (tier(c), c.warmth))
    elif prefer == "暖":
        pool = sorted(pool, key=lambda c: (tier(c), -c.warmth))
    elif reserve:
        pool = sorted(pool, key=tier)
    if dark:
        # 深底要的是「安静的深」，不是「全库最深」。按 (L, C) 排序会把
        # 深牵牛紫 #1c0d1a（L*6、紫）顶到第一位，于是 雅/清冷/空灵 加 --dark
        # 全部塌成同一块紫黑——既违反「主场必须安静」，也把青紫死局引进场。
        # 先卡住深底安全区，再按彩度从低到高取，让燕颔蓝、钢蓝这类站前面。
        safe = [c for c in pool if c.L <= DARK_GROUND_MAX_L and c.C <= DARK_GROUND_MAX_C]
        pool = sorted(safe or pool, key=lambda c: (c.C, c.L))
    if seed is not None:
        # 有种子时，主场取与种子同冷暖、低彩的近亲，或种子自己（若它够安静）
        if seed.C <= 32 and ((not dark and seed.L >= 78) or seed.L <= 28):
            return [seed] + [c for c in pool if c.name != seed.name][:24]
        undertone = [c for c in pool if (c.warmth * seed.warmth) >= 0 or abs(c.warmth) < 0.2]
        target_l = 12.0 if dark else (100.0 if seed.L < 50 else 0.0)
        undertone.sort(key=lambda c: (tier(c),
                                      abs(c.H - seed.H) if min(c.C, seed.C) > 8
                                      else abs(c.L - target_l)))
        if not reserve:
            return undertone[:28] or pool[:28]
        return _reserve_ground(undertone, 28) or _reserve_ground(pool, 28)
    return _reserve_ground(pool, 40) if reserve else pool[:40]


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
    # 手选方案的出处与注意事项的白话版。给用户念这两个，不念 rationale 里的术语版。
    origin_plain: str | None = None
    caution_plain: str | None = None

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
        # 白话版单独留字段。rationale 里那两条含「结构色」「彩度」「相克」这类
        # 内部术语，照样念给用户会把分析框架泄露出去；但也不能删掉出处与注意事项
        # ——那是这个技能最有价值的部分。所以两版并存，输出层挑一版。
        pal.origin_plain = entry.get("source_plain") or entry.get("source")
        pal.caution_plain = entry.get("caution_plain") or entry.get("caution")
        out.append(pal)
    out.sort(key=lambda p: -p.score["total"])
    return out


class SeedNotFound(ValueError):
    """种子色解析失败。必须显式报错——静默回落到默认方案是错得没有症状的那种错。"""

    def __init__(self, query: str, suggestions: list[tuple[str, str]]):
        self.query = query
        self.suggestions = suggestions
        hint = "，".join(f"{n} {h}" for n, h in suggestions)
        super().__init__(f"色库里没有「{query}」。最接近的是：{hint}")


def resolve_seed(cat: Catalog, seed: str | Color | None) -> Color | None:
    """把 seed 解析成库内色，失败即抛错。

    旧行为是解析不出就返回 None，于是 `--seed 米黄色` 静默给出与无参完全相同
    的默认方案——用户以为品牌色生效了，其实根本没进去。
    """
    if seed is None or isinstance(seed, Color):
        return seed
    q = str(seed).strip()
    if not q:
        return None
    if q.startswith("#"):
        try:
            return cat.snap(q)
        except Exception as exc:
            raise SeedNotFound(q, []) from exc
    hit = cat.resolve(q)
    if hit is not None:
        return hit
    # 给可执行的下一步：按名字里的字找同字色，再兜底给几个常见具名色
    near = [c for c in cat.colors if any(ch in c.name for ch in q)][:5]
    raise SeedNotFound(q, [(c.name, c.hex) for c in near])


def generate(cat: Catalog, mood: str | None = None, scene: str | None = None,
             seed: str | Color | None = None, n: int = 5,
             dark: bool = False, media: str | None = None,
             pin: dict | None = None) -> list[Palette]:
    """主入口：氛围 / 场景 / 种子色 -> 若干套三色配色。

    手选方案优先出现（经过文化校对），算法方案补足数量与多样性。
    dark 强制深底做场，不整页反相。media 只改约束与口令，不改角色。
    pin 把指定角色钉死（{"accent": "朱红"}），用于品牌色必须出现的场合——
    seed 只是软锚，实测 --seed "#c1272d" 会整个漂走。
    """
    families = None
    if scene and scene in SCENES:
        mood = mood or SCENES[scene]["mood"]
        families = SCENES[scene].get("families")
    seed_color = resolve_seed(cat, seed)
    pinned = {k: (v if isinstance(v, Color) else cat.resolve(str(v)))
              for k, v in (pin or {}).items()}
    for role, col in pinned.items():
        if col is None:
            raise SeedNotFound(str((pin or {})[role]), [])

    curated = curated_palettes(cat, mood, scene, seed_color, dark=dark)
    dom_families = None
    if scene and scene in SCENES:
        dom_families = SCENES[scene].get("dom_families") or families
    if dark and scene in SCENES:
        # 暗色场不该被「故宫主场必须是白/黄」绑死，但也不能把场景家族整个清空
        # ——清空之后 --scene 青花 --dark 会跑到库内任意深色上，青花的语汇就没了。
        # 正确做法是退到该场景的深色家族，仍受场景约束。
        dom_families = tuple(f for f in (families or ()) if f not in ("白", "黄")) or None
    doms = dominant_pool(cat, mood, seed_color, dom_families, dark=dark)
    if pinned.get("dominant"):
        doms = [pinned["dominant"]]
    media_cfg = MEDIA.get(media or "", {})
    wall_c = media_cfg.get("wall_max_chroma")
    if wall_c is not None:
        walled = [c for c in doms if c.C <= wall_c]
        if walled:
            doms = walled
    results: list[Palette] = []
    seen: set[tuple[str, str, str]] = set()

    # 主场头部：素底占满 12 个名额后，再给彩底留 2 个。
    # 单靠排序键不够——素底池通常远超 12 个（艳 + 白黄红 有 39 个），彩底会被整个
    # 挤出头部，「宫墙为局」这条读法就只能靠手选方案存在，算法永远出不来。
    # 反过来若不压素底名额，缺省行为会从纸地翻成红墙。两条都要，所以分名额而不是分池。
    # 只在这一档氛围真的要彩底时分名额（wants_chroma_ground 读 dom，不读颜色标签）。
    reserve_chroma = wants_chroma_ground(mood, dark)
    if reserve_chroma:
        head = [c for c in doms if _ground_tier(c) == 0][:12]
        if not head:
            head = doms[:12]
        taken = {c.name for c in head}
        head += [c for c in doms if _ground_tier(c) == 1 and c.name not in taken][:2]
    else:
        head = doms[:12]

    for dom in head:
        secs = [pinned["secondary"]] if pinned.get("secondary") else secondary_pool(cat, dom, mood, families, scene)
        for sec in secs[:8]:
            if sec.name == dom.name:
                continue
            accs = ([pinned["accent"]] if pinned.get("accent")
                    else accent_pool(cat, dom, sec, mood, families, scene))
            best_for_pair: Palette | None = None
            for acc in accs[:10]:
                key = (dom.name, sec.name, acc.name)
                if key in seen:
                    continue
                sc = score_trio(dom, sec, acc, mood)
                pal = Palette(dom, sec, acc, sc, mood, scene, dark=dark, media=media)
                if best_for_pair is None or sc["total"] > best_for_pair.score["total"]:
                    best_for_pair = pal
            # 用户钉死了角色时放宽及格线：钉住本身就是他的决定，
            # 这时候「因为分不够所以换掉他指定的色」正是必须禁止的暗中换色。
            gate = 30 if pinned else 48
            if best_for_pair and best_for_pair.score["total"] >= gate:
                seen.add((best_for_pair.dominant.name, best_for_pair.secondary.name, best_for_pair.accent.name))
                best_for_pair.rationale = _rationale(best_for_pair)
                results.append(best_for_pair)

    results.sort(key=lambda p: -p.score["total"])
    picked: list[Palette] = []
    dom_count: dict[str, int] = {}
    acc_count: dict[str, int] = {}
    # 钉死角色时手选方案不参与——它们不含被钉的色，混进来等于无视用户的指定
    if pinned:
        curated = [p for p in curated
                   if all(getattr(p, r).name == c.name for r, c in pinned.items())]
    ordered = curated + results
    # 素雅 UI 先看是否连贯，再使用原排序。明确场景、品牌色和非 UI 不受此偏好影响。
    if media == "ui" and not scene and not pinned and seed_color is None and mood in (None, "雅", "清冷", "空灵"):
        def quiet_key(p: Palette) -> tuple:
            sec, acc = p.secondary, p.accent
            same_hue = ck.hue_delta(sec.H, acc.H) <= 45
            neutral_support = min(sec.C, acc.C) < 12
            return (max(sec.C, acc.C) > 50, 0 if same_hue else 1 if neutral_support else 2)
        ordered.sort(key=quiet_key)

    def admissible(p: Palette) -> bool:
        if not media_cfg.get("need_text"):
            return True
        need = media_cfg.get("min_text_ratio") or 4.5
        backgrounds = p.trio if media == "ui" and not pinned else (p.dominant,)
        return all(pick_text_checked(cat, c, min_ratio=need)[1] for c in backgrounds)

    for p in ordered:
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
        if not admissible(p):
            continue
        picked.append(p)
        dom_count[p.dominant.name] = dom_count.get(p.dominant.name, 0) + 1
        acc_count[p.accent.name] = acc_count.get(p.accent.name, 0) + 1
        if len(picked) >= n:
            break
    # 彩底名额：n 套里给「彩底为局」留一套。
    # 纯按分排永远轮不到它——苋菜红宫墙最高 93.5，而同场景的浅底方案能到 95.7，
    # 差距来自评分现在还在奖励看不见的点缀（点缀对底 1.62:1 也不扣分，那条改写是另案）。
    # 没有这个名额，「两种读法并列」在代码里成立、在用户看到的 n 套里不成立。
    # 只留一套：素底仍是缺省，彩底是第二读法，不是新的默认。
    if (reserve_chroma and n >= 2
            and not any("彩底" in p.dominant.roles for p in picked)):
        alt = next((p for p in ordered
                    if "彩底" in p.dominant.roles
                    and not any((q.dominant.name, q.secondary.name, q.accent.name)
                                == (p.dominant.name, p.secondary.name, p.accent.name)
                                for q in picked)
                    and admissible(p)), None)
        if alt is not None:
            # 插在第三位，不是追加在末尾。调用方常取 generate(n+2) 再自己截断
            # （palette.py 的 ask 就是这么做的），追加在末尾的那一套正好被截掉——
            # 名额留了，用户还是看不到。前两位仍是素底，缺省读法不变。
            slot = min(2, len(picked))
            if len(picked) >= n:
                picked.pop()
            picked.insert(slot, alt)
    return picked


def can_ground(cat: Catalog, c: Color) -> bool:
    """这一色能不能当 UI 的底。

    两条都要满足：
    1. 底上得能写正文——但正文必须来自**墨色池或纸感池**，不是全库任意一色。
       全库任取时，526 色对某库内色的最佳对比几乎全都过 4.5，这条等于没写。
    2. 不是中调高彩（52 < L* < 78 且 C > 45）。朱红/银朱/大红正落在这里：
       它们白字只有 3.6~3.8，黑字也不够，铺成底就没有能写字的正文色，只能做大字。
    """
    if 52 < c.L < 78 and c.C > 45:
        return False
    pool = [x for x in cat.colors
            if ("墨色" in x.roles or "纸感" in x.roles) and contrast(x, c) >= 4.5]
    return bool(pool)


def complete_pair(cat: Catalog, a: str | Color, b: str | Color, mood: str | None = None) -> list[Palette]:
    """两色补全：按明度/彩度决定谁当主场/结构/点缀，再补第三个。

    两色都 `can_ground` 时返回两种读法并列（各留至少一套）：白为地、红成块，
    与红为地、白成块。只按 quiet_key 排一次的话，苋菜红+汉白玉 永远只出白地，
    「宫墙为局」这条读法在 complete 里根本不存在——而它恰是用户拿这两色来问的
    时候最想看到的那一种。
    """
    ca = a if isinstance(a, Color) else cat.resolve(str(a))
    cb = b if isinstance(b, Color) else cat.resolve(str(b))
    if ca is None or cb is None:
        raise ValueError("找不到指定的颜色，请用色库中的中文名、拼音或 hex")
    # 更安静、更浅（或同样深但更灰）的当 60
    def quiet_key(c: Color) -> tuple:
        return (0 if c.C < 28 else 1, 0 if c.L >= 78 or c.L <= 26 else 1, c.C, -c.L if c.L >= 50 else c.L)
    first, second = (ca, cb) if quiet_key(ca) <= quiet_key(cb) else (cb, ca)

    def reading(ground: Color, other: Color) -> list[Palette]:
        out: list[Palette] = []
        if other.C >= 40:
            # other 当点缀，补一个 30
            for sec in secondary_pool(cat, ground, mood)[:12]:
                if sec.name in (ground.name, other.name):
                    continue
                sc = score_trio(ground, sec, other, mood)
                pal = Palette(ground, sec, other, sc, mood)
                pal.rationale = _rationale(pal)
                out.append(pal)
        else:
            # other 当 30，补一个 10
            for acc in accent_pool(cat, ground, other, mood)[:12]:
                if acc.name in (ground.name, other.name):
                    continue
                sc = score_trio(ground, other, acc, mood)
                pal = Palette(ground, other, acc, sc, mood)
                pal.rationale = _rationale(pal)
                out.append(pal)
        out.sort(key=lambda p: -p.score["total"])
        return out

    primary = reading(first, second)
    # 第二读法只在「翻过来也真能当底」时给。两色都是浅色时翻过来还是纸地，
    # 那不是第二种读法，只是把同一种读法说两遍。
    invert = (can_ground(cat, second) and can_ground(cat, first)
              and abs(first.L - second.L) >= 20)
    if not invert:
        return primary[:5]
    alt = reading(second, first)
    if not alt:
        return primary[:5]
    return primary[:3] + alt[:3]


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
        need = cfg.get("min_text_ratio") or 4.5
        text = pick_text(cat, p.dominant, min_ratio=need)
        lines.append(f"正文 {text.name} {text.hex} 对比 {contrast(text, p.dominant):.2f}:1")
        # 块上的字要单独说。b 的落位（「卡片与导航」一类）下游一定会放字，
        # 而库内有 16 个色不存在 4.5 的搭配——那种块只能放大字，必须明说，
        # 不能让下游以为它和底一样能承载正文。
        sec_fg, met = pick_text_checked(cat, p.secondary, min_ratio=4.5)
        ratio = contrast(sec_fg, p.secondary)
        if met:
            lines.append(f"{b}上的字 {sec_fg.name} {sec_fg.hex} 对比 {ratio:.2f}:1")
        else:
            lines.append(f"{b}上的字 {sec_fg.name} {sec_fg.hex} 对比只有 {ratio:.2f}:1"
                         f"——库内没有能对 {p.secondary.name} 达到 4.5:1 的色，"
                         f"这块只放大字（≥3:1 的额度），不承载正文")
    return lines


# ---------------------------------------------------------------- 文字色与 token

def pick_text_checked(cat: Catalog, bg: Color, min_ratio: float = 4.5) -> tuple[Color, bool]:
    """挑文字色，并如实交出「达标了没有」。

    浅底优先墨色（深、低彩），深底优先纸感。不只看对比数字——
    纯黑 (#000) 在米色上对比够高但发死，战舰灰/深灰蓝更像墨。

    两条修正，都是「闸门验的色不是交付的色」这一族错：
    1. L* 50~55 的底两个方向都不成立时（想要浅字，而没有浅字够 4.5），
       旧代码静默塞一个写死的燕颔蓝。实测 33 个底走这条路，其中 17 个
       库内明明有 ≥4.5 的色，只是被 L 过滤挡在池外。所以先按原偏好试
       反方向，再退到全库最大对比——不写死任何一个色名。
    2. 剩下 16 个底（全部 L* 50.1~52.0，最低 丽春红 4.313）库内真的不存在
       4.5 的搭配。这些必须让调用方知道，不能靠返回值假装成功：
       met=False 的落位只能放大字（≥3:1），不承载正文。
    """
    def ranked(want_dark: bool) -> list[Color]:
        pool = [c for c in cat.colors if contrast(c, bg) >= min_ratio]
        if want_dark:
            pool = [c for c in pool if c.L < bg.L - 8]
            pool.sort(key=lambda c: (0 if "墨色" in c.roles else 1, c.C, -contrast(c, bg)))
        else:
            pool = [c for c in pool if c.L > bg.L + 8]
            pool.sort(key=lambda c: (0 if "纸感" in c.roles or "浅底" in c.roles else 1, c.C, -contrast(c, bg)))
        return pool

    prefer_dark = bg.L >= 55
    for want_dark in (prefer_dark, not prefer_dark):
        pool = ranked(want_dark)
        if pool:
            return pool[0], True
    best = max(cat.colors, key=lambda c: contrast(c, bg))
    return best, contrast(best, bg) >= min_ratio


def pick_text(cat: Catalog, bg: Color, min_ratio: float = 4.5) -> Color:
    """pick_text_checked 的旧签名。只要色、不要达标标记的调用点用这个。"""
    return pick_text_checked(cat, bg, min_ratio)[0]


def pick_muted(cat: Catalog, bg: Color, text: Color, surface: Color | None = None) -> Color:
    """次级文字：比正文轻，但仍然是文字，所以必须 ≥4.5:1。

    早先取 3:1–4.5:1，那是 WCAG 给大字和部件的额度。次级说明、时间戳、
    表单帮助文字都是正文尺寸，落在 3.x 就是不合规——弱化要靠明度而非违规。
    """
    backgrounds = (bg, surface) if surface is not None else (bg,)
    lo, hi = 4.5, 9.0
    pool = [c for c in cat.colors
            if all(contrast(c, b) >= lo for b in backgrounds)
            and contrast(c, bg) < hi and c.C <= 18 and c.name not in (bg.name, text.name)]
    if not pool:
        pool = [c for c in cat.colors
                if all(contrast(c, b) >= lo for b in backgrounds)
                and c.C <= 18 and c.name not in (bg.name, text.name)]
    # 次级文字必须是墨/灰一类安静色。按对比贴近 5.5 会误把龙睛鱼红
    # （高彩橙、碰巧 5.5:1）当成 muted——那是点缀不是字。
    def muted_key(c: Color) -> tuple:
        return (c.C > 10, abs(min(contrast(c, b) for b in backgrounds) - 5.5), c.C)
    pool.sort(key=muted_key)
    return pool[0] if pool else text


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


def pick_semantic(cat: Catalog, bg: Color, kind: str) -> tuple[Color, Color]:
    """状态色：作徽章底，不要求和页面 3:1（黄在米色上几乎永远不够）。

    硬条件是徽章上能放下字（on-color ≥4.5:1），以及色相落在该语义的窗口里。

    返回 (徽章色, 徽章上的字)。判据色就是交付色——早先这里算出 on 只拿去做
    if 判断，然后 `return usable[0]` 把它丢掉，于是「徽章上能放下字」这句话
    验的是一个从不出现在交付物里的色。下游拿到徽章色后只有 --color-text 可用，
    而没人验过它压在徽章上是多少。
    """
    spec = SEMANTIC_SPEC[kind]
    fallback = cat.by_name.get(spec["fallback"]) or cat.colors[0]

    def in_hue(c: Color) -> bool:
        return any(lo <= c.H <= hi or (lo > hi and (c.H >= lo or c.H <= hi))
                   for lo, hi in spec["hue"])

    pool = [c for c in cat.colors
            if c.family in spec["families"] and in_hue(c) and c.C >= spec["chroma_min"]]
    usable: list[tuple[Color, Color]] = []
    for c in pool:
        on, met = pick_text_checked(cat, c, min_ratio=4.5)
        if met:
            usable.append((c, on))
    if not usable:
        # 回落的徽章底从来没人验过它上面的字。这条路径也必须走 checked，
        # 不达标由调用方上报（死区色只放大字）。
        return fallback, pick_text_checked(cat, fallback, min_ratio=4.5)[0]
    # 状态本身已由色相区分，无需再挑同色相中最刺眼的一枚。
    target_c = max(38, spec["chroma_min"])
    if bg.L >= 55:
        usable.sort(key=lambda t: (0 if contrast(t[0], bg) >= 3.0 else 1, abs(t[0].C - target_c), t[0].L))
    else:
        usable.sort(key=lambda t: (0 if t[0].L >= 45 else 1, abs(t[0].C - target_c)))
    return usable[0]


def _near_color(target: str, candidates: list[Color], fallback: Color) -> Color:
    """只在合格候选里找近邻；无候选时保留调用方指定的安全回落。"""
    lab = ck.rgb_to_lab(ck.hex_to_rgb(target))
    return min(candidates, key=lambda c: ck.delta_e_2000(c.lab, lab)) if candidates else fallback


def _same_hue(c: Color, anchor: Color) -> bool:
    if anchor.C < 12:
        return c.C <= 14
    return anchor.C * 0.5 <= c.C <= anchor.C + 8 and ck.hue_delta(c.H, anchor.H) <= 25


def tokens(cat: Catalog, pal: Palette) -> dict:
    """展开实际可用的 UI 配对。保留三色，派生色同时满足对比与色相约束。"""
    bg, accent = pal.dominant, pal.accent
    text = pick_text(cat, bg)
    neutral = [c for c in cat.colors if c.C <= 12]
    surface_hex = ck.adjust(bg.hex, dl=(-6 if bg.L >= 70 else 7), dc=-max(0, bg.C - 6))
    surfaces = [c for c in neutral if delta_e(c, bg) >= 4 and contrast(text, c) >= 4.5
                and abs(c.L - bg.L) <= 16]
    surface = _near_color(surface_hex, surfaces, bg)
    backgrounds = (bg, surface)
    muted = pick_muted(cat, bg, text, surface)
    border = _near_color(ck.adjust(surface.hex, dl=(-12 if bg.L >= 60 else 12)),
                         [c for c in neutral if delta_e(c, surface) >= 3], surface)
    strong_pool = [c for c in neutral if all(contrast(c, b) >= 3 for b in backgrounds)]
    border_strong = _near_color(ck.adjust(bg.hex, dl=(-30 if bg.L >= 60 else 30)),
                                strong_pool, text)
    accent_fg = pick_text(cat, accent)
    secondary_fg = pick_text(cat, pal.secondary)
    state_pool = [c for c in cat.colors if _same_hue(c, accent)
                  and contrast(accent_fg, c) >= 4.5]
    # 向远离字色的方向变化，不再把白字按钮提亮到读不清。
    direction = -1 if accent_fg.L > accent.L else 1
    hover_pool = [c for c in state_pool if direction * (c.L - accent.L) >= 2]
    accent_hover = _near_color(ck.adjust(accent.hex, dl=direction * 5), hover_pool, accent)
    active_pool = [c for c in hover_pool if direction * (c.L - accent_hover.L) >= 2]
    accent_active = _near_color(ck.adjust(accent.hex, dl=direction * 9), active_pool, accent_hover)
    disabled = _near_color(ck.adjust(bg.hex, dl=(-18 if bg.L >= 60 else 18)), neutral, surface)
    ring_pool = [c for c in cat.colors if _same_hue(c, accent)
                 and all(contrast(c, b) >= 3 for b in backgrounds)]
    ring = _near_color(accent.hex, ring_pool, border_strong)
    sem = {k: pick_semantic(cat, bg, k) for k in SEMANTIC_TOKENS}
    raw = {
        "bg": bg, "surface": surface, "text": text, "muted": muted,
        "border": border, "border_strong": border_strong,
        "secondary": pal.secondary, "secondary_fg": secondary_fg, "accent": accent,
        "accent_fg": accent_fg, "accent_hover": accent_hover, "accent_active": accent_active,
        "success": sem["success"][0], "success_fg": sem["success"][1],
        "warning": sem["warning"][0], "warning_fg": sem["warning"][1],
        "error": sem["error"][0], "error_fg": sem["error"][1],
        "info": sem["info"][0], "info_fg": sem["info"][1],
        "disabled": disabled, "ring": ring,
    }
    return apply_family_lock(cat, raw, pal.scene)[0]


# 同一张配对表供派生修补与交接验收使用，避免检查与实际交付脱节。
CONTRAST_GATES = {
    "text_on_bg": (4.5, "正文"),
    "text_on_surface": (4.5, "卡片正文"),
    "muted_on_bg": (4.5, "次级文字"),
    "muted_on_surface": (4.5, "卡片说明"),
    "accent_fg_on_accent": (4.5, "按钮上的字"),
    "accent_fg_on_accent_hover": (4.5, "悬停按钮上的字"),
    "accent_fg_on_accent_active": (4.5, "按下按钮上的字"),
    "secondary_fg_on_secondary": (4.5, "彩色块上的字"),
    "success_fg_on_success": (4.5, "成功徽章上的字"),
    "warning_fg_on_warning": (4.5, "警示徽章上的字"),
    "error_fg_on_error": (4.5, "错误徽章上的字"),
    "info_fg_on_info": (4.5, "信息徽章上的字"),
    "border_strong_on_bg": (3.0, "页面输入轮廓"),
    "border_strong_on_surface": (3.0, "卡片输入轮廓"),
    "ring_on_bg": (3.0, "页面焦点轮廓"),
    "ring_on_surface": (3.0, "卡片焦点轮廓"),
}


def _preserves_contrast(key: str, candidate: Color, tok: dict) -> bool:
    for pair, (need, _) in CONTRAST_GATES.items():
        fg, bg = pair.split("_on_")
        if key in (fg, bg):
            partner = tok[bg if key == fg else fg]
            if contrast(candidate, partner) < need:
                return False
    return True


# 保留单背景义务的旧映射；完整的多背景约束由 CONTRAST_GATES 统一提供。
TOKEN_OBLIGATIONS = {
    "text": ("bg", 4.5),
    "muted": ("bg", 4.5),
    "accent_fg": ("accent", 4.5),
    # 块上的字欠块 4.5。块的落位标签是「卡片与导航」，下游一定会在它上面放字。
    # 达不到时与 family_lock 既有原则一致：保留原色并上报，不换出读不清的字。
    "secondary_fg": ("secondary", 4.5),
    "border_strong": ("bg", 3.0),
}


def family_lock(cat: Catalog, tok: dict, scene: str | None) -> list[dict]:
    """检查派生色，保留已选三色；修补不得破坏任何实际配对或按钮色相。"""
    if not scene or scene not in SCENES:
        return []
    base_allowed = set(SCENES[scene].get("families") or ()) | set(NEUTRAL_FAMILIES)
    accent_keys = ("accent", "accent_fg", "accent_hover", "accent_active", "ring")
    issues: list[dict] = []
    for key, col in tok.items():
        if key in SEMANTIC_TOKENS or key in SEMANTIC_FG_TOKENS or not isinstance(col, Color):
            continue
        allowed = base_allowed | (set(SCENES[scene].get("accent_break") or ())
                                  if key in accent_keys else set())
        if col.family in allowed or col.C <= 12:
            continue
        cands = [c for c in cat.colors
                 if c.family in allowed and abs(c.L - col.L) <= 8 and c.C <= max(col.C + 6, 14)]
        cands = [c for c in cands if _preserves_contrast(key, c, tok)]
        if key in ("accent_hover", "accent_active", "ring"):
            cands = [c for c in cands if _same_hue(c, tok["accent"])]
        # 用户看到并选定的三色是锚点，不能在交接阶段重新配一套。
        if key in ("bg", "secondary", "accent"):
            cands = []
        cands.sort(key=lambda c: (abs(c.L - col.L), abs(c.C - col.C)))
        issue = {
            "token": key,
            "was": {"name": col.name, "hex": col.hex, "family": col.family},
            "problem": f"{col.family} 不在场景「{scene}」的色族 {sorted(allowed)} 内",
            "suggest": [{"name": c.name, "hex": c.hex} for c in cands[:3]],
        }
        if not cands:
            issue["problem"] += ("；这是已选颜色，保留并提示场景冲突" if key in ("bg", "secondary", "accent")
                                 else "；没有同时满足实际配对与色相约束的替代色，保留原色")
            issue["kept"] = True
        issues.append(issue)
    return issues


def apply_family_lock(cat: Catalog, tok: dict, scene: str | None) -> tuple[dict, list[dict]]:
    """把漏出色族的 token 吸回场景语汇。

    换不动的（场景语汇内没有能保住对比义务的色）保留原色，并留在返回的问题列表里
    向用户明说——静默交付一个读不清的字比出族严重得多。
    """
    issues = family_lock(cat, tok, scene)
    fixed = dict(tok)
    unresolved: list[dict] = []
    for issue in issues:
        key = issue["token"]
        replacement = next((cat.by_name[c["name"]] for c in issue["suggest"]
                            if _preserves_contrast(key, cat.by_name[c["name"]], fixed)), None)
        if replacement is not None:
            fixed[key] = replacement
        else:
            issue["kept"] = True
            unresolved.append(issue)
    return fixed, unresolved


# AI 生成设计的三个高频撞车点。前两个是实测出来的：frontend-design 自己点名
# 「暖奶油底 #F4F1EA + 陶土橙 #D97757」是当下最容易被认出来的 AI 默认。
CLICHE_REFS = {
    "cream_ground": ("#f4f1ea", 6.0),
    "clay_accent": ("#d97757", 10.0),
}


def cliche_check(pal: Palette) -> list[dict]:
    """报告是否撞上 AI 默认审美。命中不阻断，但必须显式说明差异。"""
    out: list[dict] = []
    ref, thr = CLICHE_REFS["cream_ground"]
    d = ck.delta_e_hex(pal.dominant.hex, ref)
    if d < thr:
        out.append({
            "flag": "cream_ground",
            "detail": f"场 {pal.dominant.name} {pal.dominant.hex} 距通用暖奶油底 {ref} 只有 ΔE {d:.2f}",
            "handle": f"这是{'甜白釉' if pal.scene == '青花' else '宣纸/绢地'}的白，不是默认奶油。"
                      f"交接时写明来源，并要求下游把差异化预算花在版式与留白节奏上；"
                      f"或换场（月白 #eef7f2 / 米色 #f9e9cd）。",
        })
    ref, thr = CLICHE_REFS["clay_accent"]
    for role, col in (("accent", pal.accent), ("secondary", pal.secondary)):
        d = ck.delta_e_hex(col.hex, ref)
        if d < thr:
            out.append({
                "flag": "clay_accent",
                "detail": f"{role} {col.name} {col.hex} 距通用陶土橙 {ref} 只有 ΔE {d:.2f}",
                "handle": "说明这是矿物朱/银朱的来源，或换一枚更正的红（苋菜红 #a61b29 / 枫叶红 #c21f30）。",
            })
    if pal.dominant.L <= 22 and pal.accent.C >= 60 and pal.accent.family in ("绿", "红"):
        out.append({
            "flag": "acid_on_black",
            "detail": f"深场 {pal.dominant.name} + 单一高彩{pal.accent.family} {pal.accent.name}",
            "handle": "加一层结构色分隔，或把点缀降到中彩，避免落进「黑底 + 一枚酸色」的通用暗色模板。",
        })
    return out


def css_vars(tok: dict, selector: str = ":root") -> str:
    lines = [selector + " {"]
    mapping = [
        ("bg", "bg"), ("surface", "surface"), ("text", "text"), ("muted", "muted"),
        ("border", "border"), ("border_strong", "border-strong"),
        ("secondary", "secondary"), ("secondary_fg", "secondary-fg"), ("accent", "accent"),
        ("accent_fg", "accent-fg"), ("accent_hover", "accent-hover"),
        ("accent_active", "accent-active"),
        ("success", "success"), ("success_fg", "success-fg"),
        ("warning", "warning"), ("warning_fg", "warning-fg"),
        ("error", "error"), ("error_fg", "error-fg"),
        ("info", "info"), ("info_fg", "info-fg"),
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
            "secondary", "secondary_fg", "accent", "accent_fg",
            "accent_hover", "accent_active",
            "success", "success_fg", "warning", "warning_fg",
            "error", "error_fg", "info", "info_fg", "disabled", "ring")
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
    # 留白型方案的目标份额本来就不是 60/30/10——一张宣纸加几笔墨加一枚印，
    # 意图是 88/9/3。只放宽下限不够：份额还是按 60/30/10 归一化的话，
    # 主场永远到不了 85% 以上，「大面留白」就只是文案。
    airy = (pal.mood in AIRY_MOODS) or (pal.scene in AIRY_SCENES)
    targets = (88, 9, 3) if airy else (60, 30, 10)
    raw = (targets[0] / i60, targets[1] / i30, targets[2] / i10)
    s = sum(raw)
    a60, a30, a10 = (x / s * 100 for x in raw)
    # 点缀按响度收面积；结构色必须仍能成「块」——能量公式会把朱红墙压得过小，
    # 那在角色上已经变成点缀。给结构留一个下限，剩下的全给主场。
    a10 = min(8.0, max(2.0, a10))
    # 结构色的下限本来是为了让它仍能成「块」。留白型里这条要放松到 6%——
    # 墨在宣纸上确实只占那么一点，再夹到 16% 就把留白挤掉了。
    sec_floor = 6.0 if airy else 16.0
    a30 = min(18.0 if airy else 32.0, max(sec_floor, a30))
    cap = 20.0 if airy else 46.0
    if a10 + a30 > cap:
        a30 = cap - a10
    a60 = 100.0 - a10 - a30
    return {
        "pixel_pct": {"dominant": round(a60, 1), "secondary": round(a30, 1), "accent": round(a10, 1)},
        "intensity": {"dominant": round(i60, 3), "secondary": round(i30, 3), "accent": round(i10, 3)},
        "airy": airy,
        "note": "pixel_pct 是建议铺色面积，非角色额度。主场最大、结构居中、点缀最小。"
                + ("留白型方案：目标份额按 88/9/3 算。留白型几套常常都落在 92/6/2，"
                   "那不是没算——能量公式本身想要的更极端（结构 3.6~5.9%、点缀 0.6~1.2%），"
                   "是下限把它拉回来的：0.6% 的点缀在界面里点不着，3.6% 的结构撑不起导航。"
                   if airy else ""),
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
