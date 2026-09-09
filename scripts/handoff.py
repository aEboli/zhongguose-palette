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


def build(cat: Catalog, pal: Palette, dark_pal: Palette | None = None,
          chosen_from: str = "") -> dict:
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
            "frontend-design": ["meta", "named6", "roles", "cliche", "bans"],
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
