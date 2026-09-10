#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交接合同：把选定的一套配色写成下游设计技能能读的文件。

为什么要落文件而不是留在对话里：下游技能（frontend-design 第一遍就要 4–6 个
具名 hex）不读对话记忆，只读文件。留在对话里的结果是它自己发明灰色和描边色，
库外 hex 立刻漏出去，「只出色库里的色」这条就破了。

写两个文件：
  .palette/handoff.json  分段给不同下游读
  .palette/palette.css   亮暗两块 CSS 变量，artifact 直接用
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import colorkit as ck  # noqa: E402
from engine import (  # noqa: E402
    MEDIA, SCENES, Catalog, Color, Palette, apply_family_lock, cliche_check,
    contrast, css_vars, generate, pick_text, tokens, visual_areas,
)

TOKEN_KEYS = ("bg", "surface", "text", "muted", "border", "border_strong",
              "secondary", "accent", "accent_fg", "accent_hover", "accent_active",
              "success", "warning", "error", "info", "disabled", "ring")


def _pack(c: Color) -> dict:
    return {"name": c.name, "pinyin": c.pinyin, "hex": c.hex, "family": c.family}


def named6(cat: Catalog, pal: Palette, tok: dict) -> dict:
    """六个槽必须占满。

    frontend-design 要 4–6 个具名 hex。只给三色，它会自己补文字色和描边灰，
    那两个就是库外 hex 的入口。槽名用中文单字，本身就是差异化的来源。
    """
    return {
        "场": _pack(tok["bg"]),
        "面": _pack(tok["surface"]),
        "墨": _pack(tok["text"]),
        "界": _pack(tok["border_strong"]),
        "骨": _pack(pal.secondary),
        "眼": _pack(pal.accent),
    }


def sequential(cat: Catalog, hue_lo: float, hue_hi: float, n: int = 5) -> list[dict]:
    """同族明度阶。

    序列色本身就是不等权的明度梯，与「三色不等权」没有冲突，所以它在范围内。
    必须走 LCH 色相窗口而不是 --family：青族按字面只有 9 条，筛不出五档。
    """
    pool = [c for c in cat.colors if hue_lo <= c.H <= hue_hi and c.C >= 12]
    if len(pool) < n:
        return []
    pool.sort(key=lambda c: c.L)
    lo, hi = pool[0].L, pool[-1].L
    out: list[Color] = []
    for i in range(n):
        target = lo + (hi - lo) * i / (n - 1)
        cand = min((c for c in pool if c not in out), key=lambda c: abs(c.L - target))
        out.append(cand)
    out.sort(key=lambda c: c.L)
    return [dict(_pack(c), L=round(c.L, 1)) for c in out]


def categorical(cat: Catalog, bg: Color, max_n: int = 5) -> dict:
    """分类色：四条闸门同时成立才收。

    上限 5 是色盲安全线定的，不是审美偏好。超过就该改设计（小倍数、直接标注、
    明度阶加形状），不是硬凑颜色。
    """
    def cvd_ok(a: Color, b: Color) -> bool:
        for kind in ("protanopia", "deuteranopia", "tritanopia"):
            ra = ck.simulate_cvd(tuple(a.rgb), kind)  # type: ignore[arg-type]
            rb = ck.simulate_cvd(tuple(b.rgb), kind)  # type: ignore[arg-type]
            if ck.delta_e_2000(ck.rgb_to_lab(ra), ck.rgb_to_lab(rb)) < 12:
                return False
        return True

    def is_qing(c: Color) -> bool:
        return c.family in ("青", "蓝", "绿") and 140 <= c.H <= 280 and c.C >= 18

    def is_zi(c: Color) -> bool:
        return (c.family == "紫" or 290 <= c.H <= 340) and c.C >= 18

    base = [c for c in cat.colors if c.C >= 25 and contrast(c, bg) >= 3.0]

    def grow(order: list[Color]) -> list[Color]:
        out: list[Color] = []
        for c in order:
            if len(out) >= max_n:
                break
            if any(ck.delta_e_2000(c.lab, p.lab) < 25 for p in out):
                continue
            if any(not cvd_ok(c, p) for p in out):
                continue
            if any((is_qing(c) and is_zi(p)) or (is_zi(c) and is_qing(p)) for p in out):
                continue
            out.append(c)
        return out

    def min_pairwise(cols: list[Color]) -> float:
        if len(cols) < 2:
            return 0.0
        return min(ck.delta_e_2000(a.lab, b.lab)
                   for i, a in enumerate(cols) for b in cols[i + 1:])

    # 单趟贪心会按起点聚堆：按彩度降序只出 3 类（红/紫/棕），按色相升序出 4 类
    # 但全落在红紫区。四条闸门同时成立本身就极紧，所以换成多起点小搜索，
    # 取「类别数最多、且两两最小 ΔE 最大」的那组。仍然是确定性的。
    candidates: list[list[Color]] = [
        grow(sorted(base, key=lambda c: -c.C)),
        grow(sorted(base, key=lambda c: c.H)),
        grow(sorted(base, key=lambda c: -c.L)),
        grow(sorted(base, key=lambda c: c.L)),
    ]
    # 再以每个高彩色为起点各试一次，让第一枚不必是全库最艳的那个
    for seed in sorted(base, key=lambda c: -c.C)[:24]:
        rest = sorted((c for c in base if c.name != seed.name),
                      key=lambda c: -ck.hue_delta(c.H, seed.H))
        candidates.append(grow([seed] + rest))

    best = max(candidates, key=lambda s: (len(s), round(min_pairwise(s), 1)))
    return {
        "colors": [_pack(c) for c in best],
        "max_safe_n": len(best),
        "cvd_min_de": 12,
        "min_pairwise_de": round(min_pairwise(best), 1),
        "refuse_above": len(best),
        "note": f"两两 ΔE≥25、三种色盲下 ΔE≥12、排除青×紫、对底 ≥3:1。"
                f"这套闸门下全库只凑出 {len(best)} 类（两两最小 ΔE "
                f"{min_pairwise(best):.1f}）。要更多类别请改设计——小倍数、直接标注、"
                f"或明度阶配形状纹样——不要放宽闸门。",
    }


# 每项对比度的最低要求。达不到不能只报个数字就交出去——下游不会去核对，
# 它会照用，然后按钮上的字就是读不清的。
CONTRAST_GATES = {
    "text_on_bg": (4.5, "正文"),
    "muted_on_bg": (4.5, "次级文字"),
    "accent_fg_on_accent": (4.5, "按钮上的字"),
    "border_strong_on_bg": (3.0, "输入框/部件轮廓"),
}


def _verify(tok: dict) -> dict:
    pairs = {
        "text_on_bg": (tok["text"], tok["bg"]),
        "muted_on_bg": (tok["muted"], tok["bg"]),
        "accent_fg_on_accent": (tok["accent_fg"], tok["accent"]),
        "border_strong_on_bg": (tok["border_strong"], tok["bg"]),
    }
    out: dict = {"fail": []}
    for key, (a, b) in pairs.items():
        ratio = round(contrast(a, b), 2)
        need, label = CONTRAST_GATES[key]
        out[key] = ratio
        if ratio < need:
            out["fail"].append({
                "check": key,
                "label": label,
                "got": ratio,
                "need": need,
                "pair": f"{a.name} {a.hex} on {b.name} {b.hex}",
                "handle": "换点缀色，或把这个色只用在大字/图形上（≥3:1 的额度），不要拿它承载正文",
            })
    return out


ROOT = Path(__file__).resolve().parents[1]
MOTIFS_PATH = ROOT / "references" / "motifs.json"


_MOTIFS_CACHE: dict | None = None


def _load_motifs() -> dict:
    """读纹样表。文件在一次运行里是静态的，读一次就够。

    读不出来要**响亮地**失败，不许回落成空表。回落的症状是「你输的 id 不存在」
    ——把一个数据文件的语法错报成用户拼错了纹样名，而 motifs 子命令还会
    一本正经地打「0 个纹样」。那正是这份文件自己在 250 行处点名的那类错：
    错得没有症状。
    """
    global _MOTIFS_CACHE
    if _MOTIFS_CACHE is None:
        try:
            _MOTIFS_CACHE = json.loads(MOTIFS_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError as e:
            raise SystemExit(f"读不到纹样表 {MOTIFS_PATH}：{e}") from e
        except json.JSONDecodeError as e:
            raise SystemExit(f"纹样表 {MOTIFS_PATH} 不是合法 JSON：第 {e.lineno} 行 {e.msg}") from e
    return _MOTIFS_CACHE


def _composite(fg_hex: str, bg_hex: str, alpha: float) -> tuple:
    f = ck.hex_to_rgb(fg_hex)
    b = ck.hex_to_rgb(bg_hex)
    return tuple(round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3))


def chroma_rise(fg_hex: str, bg_hex: str, alpha: float) -> float:
    """纹样压在底色上后，合成彩度比底色高出多少。

    这是「纹样不许变成第四个配比色」最直接的度量。实测借高彩 accent 时
    ΔC 会冲到 +13.5，那就是一片可见色晕；借 border 只有 +0.5。
    """
    lab_c = ck.rgb_to_lab(_composite(fg_hex, bg_hex, alpha))
    lab_b = ck.rgb_to_lab(ck.hex_to_rgb(bg_hex))
    return math.hypot(lab_c[1], lab_c[2]) - math.hypot(lab_b[1], lab_b[2])


def ink_charge(motif: dict, tok: dict, accent_pct: float) -> dict | None:
    """彩度型借色折价计入该 token 的额度。返回 None 表示零计费。

    charge = ink_pct × (C_ink / C_accent)，上限 0.3 × accent_pct。
    这是「纹样不占配比」这句话唯一的兑现方式——在 ink_pct 数值化之前
    公式只是散文，谁也算不了，于是那句话就只是文案。
    """
    data = _load_motifs()
    rule = data.get("charge_rule") or {}
    borrow = (motif.get("borrows_token") or ["border"])[0]
    if borrow not in tok or "accent" not in tok:
        return None
    c_ink = tok[borrow].C
    if c_ink < 12:  # 中性借色零计费
        return None
    c_accent = tok["accent"].C
    rng = motif.get("ink_range") or [0.0, 0.0]
    ink_hi = float(rng[1])
    charge = ink_hi * (c_ink / c_accent) if c_accent > 0 else ink_hi
    cap = 0.3 * accent_pct
    return {
        "borrows_token": borrow,
        "ink_pct_hi": ink_hi,
        "c_ink": round(c_ink, 1),
        "c_accent": round(c_accent, 1),
        "charge_pct": round(charge, 3),
        "cap_pct": round(cap, 3),
        "over": charge > cap,
        "formula": rule.get("formula"),
    }


def check_ornament(cat: Catalog, tok: dict, motif: dict, alpha: float,
                   scene: str | None = None, accent_pct: float | None = None) -> list:
    """一个纹样在当前配色下是否合规。返回问题列表（空表示可用）。"""
    data = _load_motifs()
    allowed = set((data.get("ink_sources") or {}).get("allowed") or [])
    gate = (data.get("chroma_gate") or {}).get("max_delta_c", 4.0)
    ceilings = data.get("alpha_ceilings") or {}
    out = []
    for b in (motif.get("borrows_token") or []):
        if allowed and b not in allowed:
            out.append({"motif": motif["id"], "problem": f"不许借 {b}",
                        "why": "交互态、语义徽章、失能态、焦点环不能借给装饰层"})
    # 场景不合要在这里也拦一次。ask 那条路会解释后丢弃，pick 原先直接照出——
    # 同一条规则两个入口给不同答案，比两边都不管更难查。
    if scene and scene in (motif.get("avoid_scenes") or []):
        out.append({"motif": motif["id"], "problem": f"与场景「{scene}」气质不合",
                    "why": "这个纹样自己的 avoid_scenes 点名了这个场景",
                    "fix": "换一个纹样，或换场景"})
    fits = motif.get("fits_scenes") or []
    if scene and fits and scene not in fits:
        out.append({"motif": motif["id"], "problem": f"没标注适配场景「{scene}」",
                    "why": f"它自己的 fits_scenes 只有 {'、'.join(fits)}",
                    "fix": "不算硬错，但要向用户说明这是跨场景借用",
                    "soft": True})
    # 每一个候选借色都要过闸门，不只是首选。只查 [0] 的话，
    # borrows_token 里写着的第二选择等于没人验过——而它正是文档
    # 告诉下游「首选不可用时改指这个」的那一个。
    if motif.get("under_text") and "bg" in tok:
        for borrow in (motif.get("borrows_token") or ["border"]):
            if borrow not in tok:
                continue
            rise = chroma_rise(tok[borrow].hex, tok["bg"].hex, alpha)
            if rise > gate:
                out.append({
                    "motif": motif["id"],
                    "problem": f"压在文字下借 {borrow}（{tok[borrow].name}）时合成彩度抬升 "
                               f"{rise:.1f}，超过 {gate}",
                    "why": "那会成为一片可见色晕，被读成第四个色块",
                    "fix": "改借近无彩的 surface / border / muted，或把这个纹样移出正文区",
                })
            cap = ceilings.get(borrow)
            if cap is not None and alpha > cap:
                out.append({
                    "motif": motif["id"],
                    "problem": f"alpha {alpha} 超过借 {borrow} 时的上限 {cap}",
                    "why": "正文对合成后底色会跌破 4.5:1",
                })
    if accent_pct is not None:
        ch = ink_charge(motif, tok, accent_pct)
        if ch and ch["over"]:
            out.append({
                "motif": motif["id"],
                "problem": f"借彩度色 {ch['borrows_token']} 折价后占 {ch['charge_pct']}%，"
                           f"超过点缀额度的三成（{ch['cap_pct']}%）",
                "why": "那已经不是点缀，是第二块同色——「纹样不占配比」这句话在这里不成立了",
                "fix": "改借中性色（surface / border / muted，零计费），或选墨量更小的纹样",
            })
    return out


def ornament(cat: Catalog, pal: Palette, tok: dict, motif_ids: list | None = None,
             areas: dict | None = None) -> dict:
    """纹样点缀段。

    纹样不是第四个配比色——它借用已有 token 的颜色，资产里一个色值字符都没有。
    所以这一段给的是「借哪个变量」而不是 hex，下游想换色只能改变量指向，
    而变量只能指向本段列出的那几个。
    """
    data = _load_motifs()
    by_id = {m["id"]: m for m in data.get("motifs", [])}
    picked = [by_id[i] for i in (motif_ids or []) if i in by_id]
    # 拼错的 id 要报出来，不许静默产出一个没有纹样的交接文件——
    # 那和 --seed 解析失败静默回落是同一类错：错得没有症状。
    unknown = [i for i in (motif_ids or []) if i not in by_id]
    ceilings = data.get("alpha_ceilings", {})
    scene = pal.scene
    accent_pct = (areas or visual_areas(pal)["pixel_pct"])["accent"]

    def usable(m: dict) -> bool:
        """既不能撞 avoid_scenes，也要真在 fits_scenes 里。

        只查 avoid 的话，年画场景下 8 条推荐里有 7 条的 fits_scenes 根本没写年画
        （折枝梅只适配水墨/宋瓷/江南/青花）。fits_scenes 在 22 条纹样上全都写了、
        selftest 也验了它的合法性，但代码一处都没读——「已适配」于是成了
        「没被明确排除」，而 suggestions 正是 frontend-design 直接照用的那份。
        """
        if scene and scene in (m.get("avoid_scenes") or []):
            return False
        fits = m.get("fits_scenes") or []
        if scene and fits and scene not in fits:
            return False
        return True

    suggestions = [m["id"] for m in data.get("motifs", []) if usable(m)][:8]

    out = {
        "prime_rule": data.get("meta", {}).get("prime_rule"),
        "unknown_ids": unknown,
        "chosen": [],
        "suggestions": suggestions,
        "render": {
            "preferred": "mask",
            "why": "mask 方案的纹样资产里一个颜色字符都没有（路径全是不透明黑，只当 alpha 用），"
                   "颜色唯一入口是 background-color 指向的变量。要引入新色必须在 CSS 里手打 hex，"
                   "一条正则就能在 CI 里抓住。",
            "mask": ".orn{--orn-ink:var(--color-border-strong);background-color:var(--orn-ink);"
                    "-webkit-mask-image:var(--orn-tile);mask-image:var(--orn-tile);"
                    "mask-mode:alpha;mask-repeat:repeat;mask-size:160px 160px;opacity:.08}",
            "inline_svg": '<svg aria-hidden="true" focusable="false" style="color:var(--color-border-strong)">'
                          '<path fill="currentColor" d="…"/></svg>',
            "must_not": [
                "禁止在 data URI 里写 fill/stroke 的字面色值——那是库外 hex 的入口",
                "禁止用 background-image 承载有色纹样：url() 让 SVG 成为外部资源，"
                "currentColor 与 var() 在里面一律失效，想换色只能改那串 hex",
                "裸 var() 写在 SVG 呈现属性上会静默降级且方向相反："
                "fill 回落成纯黑（破「不许纯黑」），stroke 回落成 none（纹样凭空消失）。"
                "必须带 fallback：stroke=\"var(--color-border, currentColor)\"",
            ],
        },
        "alpha_ceilings": ceilings,
        "budget": {
            "rule": data.get("meta", {}).get("two_budgets"),
            "ink_pct_def": data.get("meta", {}).get("ink_pct_def"),
            "charge": data.get("charge_rule", {}),
            "accent_pct": accent_pct,
        },
        "ink_sources": data.get("ink_sources", {}),
        "chroma_gate": data.get("chroma_gate", {}),
        "ink_ladder": data.get("ink_ladder", {}),
        "sets": data.get("sets", {}),
        "taboo": data.get("taboo", {}),
        "a11y": {
            "decorative": 'aria-hidden="true" focusable="false"，或 role="presentation"',
            "note": "纹样是装饰，不承载信息，不进无障碍树。若纹样承载了信息（例如用图案区分类别），"
                    "那它就不是装饰，必须另给文字或 aria-label。",
            "reduced_motion": "纹样本身不该动。若做了入场动画，@media (prefers-reduced-motion: reduce) 里去掉",
            "forced_colors": "@media (forced-colors: active) 时隐藏纹样（forced-colors 会重置背景色，"
                             "mask 方案会露出系统色块）",
        },
    }
    alpha_default = ceilings.get("practical_default", 0.08)
    out["issues"] = []
    for m in picked:
        out["issues"].extend(
            check_ornament(cat, tok, m, alpha_default, scene=scene, accent_pct=accent_pct))
    for m in picked:
        borrows = [b for b in (m.get("borrows_token") or ["border"])]
        borrow = borrows[0]
        out["chosen"].append({
            "id": m["id"],
            "name": m["name"],
            "category": m["category"],
            "form": m["form"],
            # 画法细则必须一起交出去。`form` 只有两个字（「折枝」），
            # 而「花必五瓣、枝作顿折的硬转、不带根土」这类反俗硬规则全在
            # form_detail 里——不交，下游只能凭「折枝」二字自己想象。
            "form_detail": m.get("form_detail"),
            "borrows_var": f"--color-{borrow.replace('_', '-')}",
            "borrows_token": borrow,
            # 备选也要给出来。文档告诉下游「首选不可用时改指下一个」，
            # 只发首选的话那句话没有落点。
            "borrows_alternates": [f"--color-{b.replace('_', '-')}" for b in borrows[1:]],
            "borrowed_hex_for_reference": tok[borrow].hex if borrow in tok else None,
            "alpha_max": ceilings.get(borrow) if m.get("under_text") else None,
            "alpha_suggested": alpha_default,
            "ink_pct": m.get("ink_pct"),
            "ink_range": m.get("ink_range"),
            "ink_note": m.get("ink_note"),
            "charge": ink_charge(m, tok, accent_pct),
            "coverage_pct": m.get("coverage_pct"),
            "placement": m["placement"],
            "css_hint": m.get("css_hint"),
            "under_text": bool(m.get("under_text")),
            "fits_scenes": m.get("fits_scenes") or [],
            "culture_note": m.get("culture_note") or None,
        })
    return out


def build(cat: Catalog, pal: Palette, dark_pal: Palette | None = None,
          chosen_from: str = "", motif_ids: list | None = None) -> dict:
    """组装 handoff.json。"""
    tok_light, issues = apply_family_lock(cat, tokens(cat, pal), pal.scene)
    areas = visual_areas(pal)["pixel_pct"]
    text = tok_light["text"]

    out: dict = {
        "meta": {
            "source": "zhongguose.com 526 色",
            "scene": pal.scene,
            "mood": pal.mood,
            "media": pal.media,
            "score": pal.score["total"],
            "origin": next((l.split("：", 1)[-1] for l in pal.rationale if l.startswith("手选方案")), None),
            "caution": next((l.split("：", 1)[-1] for l in pal.rationale if l.startswith("注意：")), None),
            "chosen_from": chosen_from,
            "labels": list(MEDIA.get(pal.media or "", {}).get("labels") or ()),
        },
        "roles": {
            "dominant": dict(_pack(pal.dominant), area_pct=areas["dominant"]),
            "secondary": dict(_pack(pal.secondary), area_pct=areas["secondary"]),
            "accent": dict(_pack(pal.accent), area_pct=areas["accent"]),
            "note": "area_pct 是建议铺色面积，不是三等分。点缀铺成整条顶栏就毁了。",
        },
        "named6": named6(cat, pal, tok_light),
        "tokens_light": {k: _pack(tok_light[k]) for k in TOKEN_KEYS},
        "css": {"light": css_vars(tok_light, ":root")},
        "verify": _verify(tok_light),
        "chart": {
            "neutrals": {
                "axis": _pack(tok_light["text"]),
                "grid": _pack(tok_light["border"]),
                "annotation": _pack(tok_light["muted"]),
                "zero_line": _pack(tok_light["border_strong"]),
            },
            "sequential": sequential(cat, 200, 280, 5),
            "categorical": categorical(cat, tok_light["bg"]),
            "bans": [
                "不要彩虹/jet：明度非单调，序列语义会失真",
                "不要把三色直接当图表填充：点缀是标点不是面",
                "不要用 success/warning/error/info 当分类色：它们是徽章内部色，藤黄对白只有 1.46:1",
                "序列色不占点缀额度，它是另一组令牌",
            ],
        },
        "ornament": ornament(cat, pal, tok_light, motif_ids, areas=areas),
        "cliche": cliche_check(pal),
        "bans": {
            "accent_max_area_pct": areas["accent"],
            "no_accent_topbar": True,
            "text_min_ratio": 4.5,
            "gold_stroke_only": True,
            "body_text_forbidden": ["姜黄", "银朱", "北瓜黄"],
            "banned_terms": ["中国红"],
            "no_pure_white_black": "不要 #ffffff / #000000。库内最近是 雪白 #fffef9 / 燕颔蓝 #131824",
            "downstream_must_not_edit_hex": "需要库外新色时回来跑 palette.py snap \"#xxxxxx\"，不要插值",
        },
        "issues": list(issues) + [
            {"token": f["check"], "problem": f"{f['label']}对比只有 {f['got']}:1，需要 {f['need']}:1",
             "detail": f["pair"], "handle": f["handle"]}
            for f in _verify(tok_light)["fail"]
        ],
        "scope": {
            "owns": ["色", "面积预算", "对比度闸门"],
            "not_owns": ["字体", "间距", "圆角", "组件结构", "动效"],
            "note": "版式与排版属于 frontend-design。两个技能在同一轴上打架比各自留白更糟。",
        },
        "read_map": {
            "frontend-design": ["meta", "named6", "roles", "ornament", "cliche", "bans"],
            "artifact-design": ["css", "tokens_light", "tokens_dark", "bans"],
            "dataviz": ["chart", "tokens_light.bg", "tokens_light.text", "tokens_light.border", "bans"],
        },
    }

    if dark_pal is not None:
        tok_dark, dark_issues = apply_family_lock(cat, tokens(cat, dark_pal), dark_pal.scene)
        out["tokens_dark"] = {k: _pack(tok_dark[k]) for k in TOKEN_KEYS}
        # 两块都出 :root 会互相覆盖。暗色必须走 data-theme + prefers-color-scheme。
        out["css"]["dark"] = css_vars(tok_dark, '[data-theme="dark"]')
        out["css"]["dark_media"] = (
            "@media (prefers-color-scheme: dark) {\n"
            + css_vars(tok_dark, ':root:not([data-theme="light"])').replace("\n", "\n  ")
            + "\n}"
        )
        out["issues"] = list(out["issues"]) + dark_issues
        out["meta"]["dark_pair"] = {
            "accent_family_match": dark_pal.accent.family == pal.accent.family,
            "note": "亮暗必须共享点缀色族与场景语汇，否则是两套无关的方案",
        }
    return out


def css_file(data: dict) -> str:
    parts = ["/* 中国传统色 · 由 zhongguose-palette 生成，色值全部来自 526 色库 */",
             ":root { color-scheme: light dark; }",
             data["css"]["light"]]
    if "dark" in data["css"]:
        parts += [data["css"]["dark"], data["css"]["dark_media"]]
    return "\n\n".join(parts) + "\n"


def write(data: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    j = out_dir / "handoff.json"
    c = out_dir / "palette.css"
    j.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    c.write_text(css_file(data), encoding="utf-8")
    return j, c
