#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：色彩数学、色库完整性、别名、手选方案、生成器铁律。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import colorkit as ck  # noqa: E402
from engine import Catalog, generate, score_trio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)
        print("FAIL", msg)
    else:
        print(" ok ", msg)


def test_colorkit() -> None:
    check(abs(ck.contrast_ratio("#ffffff", "#000000") - 21.0) < 1e-6, "WCAG 白/黑 = 21")
    check(abs(ck.contrast_ratio("#767676", "#ffffff") - 4.54) < 0.02, "WCAG #767 临界 AA")
    lab = ck.rgb_to_lab(ck.hex_to_rgb("#ff0000"))
    check(abs(lab[0] - 53.24) < 0.05 and abs(lab[1] - 80.09) < 0.05, "Lab 纯红")
    de = ck.delta_e_2000((50, 2.5, 0.0), (50, 0.0, -2.5))
    check(abs(de - 4.3065) < 0.01, "CIEDE2000 Sharma")
    check(ck.hue_delta(350, 10) == 20.0, "色相夹角跨 0°")
    check(abs(ck.hue_mid(350, 10)) < 1e-6, "色相中点跨 0°")
    # 补色混合走 Lab，应得近中性而不是紫
    mix = ck.bridge("#c21f30", "#126e82")
    lch = ck.hex_to_lch(mix)
    check(lch[1] < 45, f"朱红×石青桥接应降彩，实际 C={lch[1]:.1f} {mix}")
    # 色域：L=100 带彩度必须被压成纯白
    fitted = ck.fit_gamut((100, 20, 100))
    check(fitted[1] < 1.0, f"L=100 降彩到近 0，实际 C={fitted[1]}")


def test_catalog() -> None:
    cat = Catalog()
    check(len(cat.colors) == 526, f"色库 526 条，实际 {len(cat.colors)}")
    hexes = [c.hex for c in cat.colors]
    check(len(set(hexes)) == 526, "hex 唯一")
    check(len({c.pinyin for c in cat.colors}) == 526, "pinyin 去重后唯一")
    # 以 hex 为准
    rose = cat.by_name["玫瑰灰"]
    check(rose.hex == "#4b2e2b", "玫瑰灰 hex 为准（原始 RGB 是错的）")
    check(tuple(rose.rgb) == (75, 46, 43), "rgb 由 hex 重算")
    # 浅底池不能空
    paper = [c for c in cat.colors if "浅底" in c.roles]
    check(len(paper) >= 20, f"浅底池 ≥20，实际 {len(paper)}")
    ink = [c for c in cat.colors if "墨色" in c.roles]
    check(len(ink) >= 40, f"墨色池 ≥40，实际 {len(ink)}")


def test_aliases() -> None:
    cat = Catalog()
    mapping = {
        "石青": "群青", "玄色": "可可棕", "胭脂": "苋菜红",
        "竹青": "瓦松绿", "天青": "霁青", "黛": "野葡萄紫",
        "漆黑": "燕颔蓝", "墨色": "战舰灰",
    }
    for alias, target in mapping.items():
        got = cat.resolve(alias)
        check(got is not None and got.name == target, f"别名 {alias} -> {target}，实得 {got.name if got else None}")
    # 输出 hex 必须在色库
    for a in cat.aliases.values():
        check(a["target_hex"] in cat.by_hex, f"别名 {a['alias']} 的 target_hex 必须在库内")


def test_curated() -> None:
    cat = Catalog()
    check(len(cat.curated) >= 18, f"手选方案 ≥18，实际 {len(cat.curated)}")
    scores = []
    for e in cat.curated:
        for k in ("dominant", "secondary", "accent"):
            check(e[k] in cat.by_name, f"手选 {e['name']} 的 {k}={e[k]} 必须在库内")
        pal_score = score_trio(cat.by_name[e["dominant"]], cat.by_name[e["secondary"]], cat.by_name[e["accent"]], e.get("mood"))
        scores.append(pal_score["total"])
    check(sum(scores) / len(scores) >= 80, f"手选均分 ≥80，实际 {sum(scores)/len(scores):.1f}")
    # 退化案例必须明显低于手选
    bad = score_trio(cat.by_name["银朱"], cat.by_name["丽春红"], cat.by_name["极光红"], "艳")
    check(bad["total"] < 55, f"三色同色应低分，实际 {bad['total']}")
    clash = score_trio(cat.by_name["群青"], cat.by_name["月白"], cat.by_name["桔梗紫"])
    check(clash["total"] < 75, f"青间紫应低分，实际 {clash['total']}")


def test_generate() -> None:
    cat = Catalog()
    for scene, must_have in [
        ("故宫", {"汉白玉", "酪黄", "朱红", "姜黄", "银朱", "茶褐"}),
        ("青花", {"雪白", "群青", "鷃蓝"}),
        ("水墨", {"鱼肚白", "汉白玉", "战舰灰", "银朱", "苋菜红"}),
    ]:
        pals = generate(cat, scene=scene, n=3)
        check(len(pals) >= 2, f"{scene} 至少 2 套")
        names = {p.dominant.name for p in pals} | {p.secondary.name for p in pals} | {p.accent.name for p in pals}
        check(len(names & must_have) >= 2, f"{scene} 应命中手选色名，命中 {names & must_have}")
        for p in pals:
            for c in p.trio:
                check(c.hex in cat.by_hex, f"{scene} 输出 {c.name} {c.hex} 必须在库内")
            # 故宫点缀不得是品红
            if scene == "故宫":
                check(not (p.accent.H < 15 or p.accent.H > 340),
                      f"故宫点缀 {p.accent.name} H={p.accent.H:.0f} 不应是品红")
    from engine import visual_areas
    qinghua = generate(cat, scene="青花", n=1)[0]
    area = visual_areas(qinghua)["pixel_pct"]
    check(16 <= area["secondary"] <= 32, f"结构色面积应有下限，实际 {area['secondary']}")
    check(2 <= area["accent"] <= 8, f"点缀面积应被收窄，实际 {area['accent']}")
    check(abs(area["dominant"] + area["secondary"] + area["accent"] - 100) < 0.2, "三面积之和为 100")

    darks = generate(cat, dark=True, n=3)
    check(len(darks) >= 2, f"--dark 至少 2 套，实际 {len(darks)}")
    for p in darks:
        check(p.dominant.L <= 40, f"暗色场必须深，{p.dominant.name} L*={p.dominant.L:.0f}")
        check(p.dark, "Palette.dark 标记")
    qinghua_dark = generate(cat, scene="青花", dark=True, n=2)
    check(len(qinghua_dark) >= 1, "青花暗色至少 1 套")
    for p in qinghua_dark:
        check(p.dominant.L <= 40, f"青花暗色场必须深，{p.dominant.name} L*={p.dominant.L:.0f}")
        check(p.dominant.family in ("蓝", "青", "灰", "黑"), f"青花暗色场应是青蓝灰，实为 {p.dominant.family}")
    interiors = generate(cat, media="interior", mood="雅", n=2)
    check(len(interiors) >= 1, "空间媒材至少 1 套")
    for p in interiors:
        check(p.dominant.C <= 28, f"墙面必须低彩，{p.dominant.name} C={p.dominant.C:.0f}")
        check(p.media == "interior", "media 标记")
    posters = generate(cat, media="poster", scene="敦煌", n=1)
    check(posters and posters[0].media == "poster", "海报媒材标记")
    uis = generate(cat, media="ui", scene="水墨", n=1)
    check(uis and uis[0].media == "ui", "UI 媒材标记")


def test_tokens() -> None:
    """UI token 必须能直接落地：WCAG 达标、层次可见、语义色相正确。"""
    from engine import contrast, delta_e, pick_text, tokens
    cat = Catalog()
    cases = [
        ("浅色-水墨", dict(media="ui", scene="水墨")),
        ("暗色", dict(media="ui", dark=True)),
        ("青花", dict(media="ui", scene="青花")),
        ("故宫", dict(media="ui", scene="故宫")),
        ("雅", dict(media="ui", mood="雅")),
    ]
    for label, kw in cases:
        pals = generate(cat, n=1, **kw)
        check(bool(pals), f"{label} 应生成方案")
        if not pals:
            continue
        tok = tokens(cat, pals[0])
        bg = tok["bg"]
        for key in ("bg", "surface", "text", "muted", "border", "border_strong",
                    "secondary", "accent", "accent_fg", "accent_hover", "accent_active",
                    "success", "warning", "error", "info", "disabled", "ring"):
            check(key in tok, f"{label} 缺 token {key}")
            check(tok[key].hex in cat.by_hex, f"{label} {key}={tok[key].hex} 必须在库内")
        check(contrast(tok["text"], bg) >= 4.5, f"{label} 正文 {contrast(tok['text'], bg):.2f} 应 ≥4.5")
        check(contrast(tok["muted"], bg) >= 4.5, f"{label} 次级 {contrast(tok['muted'], bg):.2f} 应 ≥4.5")
        check(tok["muted"].chroma_band in ("无彩", "微彩", "低彩"),
              f"{label} 次级不应是高彩，实为 {tok['muted'].chroma_band}")
        check(contrast(tok["accent_fg"], tok["accent"]) >= 4.5,
              f"{label} 点缀字 {contrast(tok['accent_fg'], tok['accent']):.2f} 应 ≥4.5")
        check(contrast(tok["border_strong"], bg) >= 3.0,
              f"{label} 强描边 {contrast(tok['border_strong'], bg):.2f} 应 ≥3.0")
        check(delta_e(tok["surface"], bg) >= 4.0,
              f"{label} 面层与底 ΔE {delta_e(tok['surface'], bg):.1f} 应 ≥4")
        check(110 <= tok["success"].H <= 170, f"{label} success 色相 {tok['success'].H:.0f} 应在绿区")
        check(70 <= tok["warning"].H <= 105, f"{label} warning 色相 {tok['warning'].H:.0f} 应在黄区")
        for key in ("success", "warning", "error", "info"):
            on = pick_text(cat, tok[key], 4.5)
            check(contrast(on, tok[key]) >= 4.5, f"{label} {key} 徽章上放不下字")
        check(tok["accent_hover"].name != tok["accent"].name, f"{label} hover 应区别于 accent")


def main() -> int:
    test_colorkit()
    test_catalog()
    test_aliases()
    test_curated()
    test_generate()
    test_tokens()
    print()
    if FAILS:
        print(f"{len(FAILS)} 项失败")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
