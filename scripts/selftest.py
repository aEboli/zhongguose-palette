#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：色彩数学、色库完整性、别名、手选方案、生成器铁律。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import os  # noqa: E402
import shutil  # noqa: E402

import colorkit as ck  # noqa: E402
from engine import Catalog, generate, score_trio, tokens, visual_areas  # noqa: E402
from handoff import TOKEN_KEYS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAILS: list[str] = []
PASSES = 0


def check(cond: bool, msg: str) -> None:
    global PASSES
    if not cond:
        FAILS.append(msg)
        print("FAIL", msg)
    else:
        PASSES += 1
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
        "竹青": "瓦松绿", "天青": "井天蓝", "黛": "野葡萄紫",
        "漆黑": "燕颔蓝", "墨色": "战舰灰",
        # 这三条原先是纯色差最近邻或与自身 reason 矛盾，已作文化校正
        "乌金": "苍黄", "玉色": "玉簪绿",
    }
    for alias, target in mapping.items():
        got = cat.resolve(alias)
        check(got is not None and got.name == target, f"别名 {alias} -> {target}，实得 {got.name if got else None}")
    # 输出 hex 必须在色库
    for a in cat.aliases.values():
        check(a["target_hex"] in cat.by_hex, f"别名 {a['alias']} 的 target_hex 必须在库内")

    # 铁律 13 的内部一致性：reason 里说了「不是鲜蓝」「青中带灰」这类低彩承诺，
    # target 就必须真的低彩。之前 天青 的 reason 写「不是鲜蓝」而 target 是
    # C27.9 的明亮青蓝——技能自己立了规矩又违反它，这种矛盾要靠断言挡住。
    LOW_CHROMA_WORDS = ("带灰", "不是鲜", "灰调", "失透", "淡灰")
    for a in cat.aliases.values():
        reason = a.get("reason", "")
        if any(w in reason for w in LOW_CHROMA_WORDS):
            t = cat.by_name[a["target"]]
            check(t.C <= 20,
                  f"别名 {a['alias']} 的 reason 承诺低彩，target {t.name} 实测 C{t.C:.1f} 应 ≤20")


def test_curated() -> None:
    cat = Catalog()
    check(len(cat.curated) >= 21, f"手选方案 ≥21，实际 {len(cat.curated)}")
    names = {e["name"] for e in cat.curated}
    # 三套「以彩为地」的手选：与各自的纸地读法并列，不是替代
    for nm, ground in (("宫墙压境", "苋菜红"), ("莫高土壁", "赭石"), ("蓝釉为地", "景泰蓝")):
        check(nm in names, f"手选应含「{nm}」")
        e = next(x for x in cat.curated if x["name"] == nm)
        check(e["dominant"] == ground, f"{nm} 的底应是 {ground}，实得 {e['dominant']}")
        check("彩底" in cat.by_name[ground].roles, f"{nm} 的底 {ground} 必须是彩底")
    # 旧的纸地读法一套都不许被顶掉
    for nm in ("紫禁朱墙", "景泰蓝铜"):
        check(nm in names, f"旧读法「{nm}」必须还在——两种读法并列，不是替代")
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


def test_chroma_ground() -> None:
    """彩底：深而彩的矿物色可以整片铺开，红墙是主场而不是 16% 的一块。

    这里锁三件事，缺任何一件「气势」都会悄悄退回纸地：
    1. 角色切得对——苋菜红/赭石/景泰蓝进，朱红/银朱/大红（白字 3.6~3.8）不进；
    2. 算法路径真的出得来——不只手选方案里有；
    3. 雅/清冷/空灵/古朴 一套都不许翻成彩底，缺省读法不变。
    """
    from engine import can_ground, complete_pair, wants_chroma_ground
    cat = Catalog()
    cb = [c for c in cat.colors if "彩底" in c.roles]
    check(len(cb) >= 40, f"彩底池 ≥40，实际 {len(cb)}")
    for c in cb:
        check(c.C >= 40, f"彩底 {c.name} C={c.C:.1f} 必须 ≥40")
        check(c.contrast_white >= 4.5,
              f"彩底 {c.name} 白字 {c.contrast_white:.2f}:1 必须 ≥4.5——铺满了写不上字就不是底")
        # 白字 4.5 的门槛已隐含「不是中调」。这条把结论钉住：一旦有彩底 L*>52
        # 冒出来，说明 contrast_white 的算法或色库变了，得回来重看判据。
        check(c.L <= 52, f"彩底 {c.name} L*={c.L:.1f} 应 ≤52（白字门槛的推论）")
    for n in ("苋菜红", "赭石", "景泰蓝", "群青", "殷红"):
        check("彩底" in cat.by_name[n].roles, f"{n} 应是彩底：深而彩的矿物色，本来就整片铺")
    for n in ("朱红", "银朱", "大红"):
        c = cat.by_name[n]
        check("彩底" not in c.roles,
              f"{n} 白字仅 {c.contrast_white:.2f}:1，不许进彩底——铺成底就没有能写正文的色")
        check(not can_ground(cat, c), f"{n} 是中调高彩（L*{c.L:.0f} C{c.C:.0f}），can_ground 应为假")
    for n in ("苋菜红", "赭石", "景泰蓝", "汉白玉", "月白"):
        check(can_ground(cat, n and cat.by_name[n]), f"{n} 应能做底")

    # 算法路径：故宫 n=5 里至少一套底是 C>=40 的深彩色。
    # 这条是整个改动的验收——手选方案里有红底不算，用户换个说法就见不到了。
    pals = generate(cat, scene="故宫", n=5)
    hot = [p for p in pals if p.dominant.C >= 40]
    check(hot, "故宫 n=5 至少一套底 C≥40，否则「宫墙为局」只存在于手选里，"
               f"实得底 {[(p.dominant.name, round(p.dominant.C)) for p in pals]}")
    check(any("彩底" in p.dominant.roles for p in pals), "故宫 n=5 至少一套底是彩底")
    # 前两位仍是素底：彩底是第二读法，不是新的缺省
    check(all("彩底" not in p.dominant.roles for p in pals[:2]),
          f"前两套应仍是素底，实得 {[p.dominant.name for p in pals[:2]]}")

    # 静的四档一套都不许出彩底。满天星紫/石竹紫 同时是 深底 与 彩底，
    # 会靠 深底 合法进 古朴 的池——若「留名额」按颜色标签判而不按 dom 判，
    # 古朴 就会被连坐：84.6 分的紫底顶到第三位，挤掉 89.5 分的可可棕。
    for mood in ("雅", "清冷", "空灵", "古朴"):
        check(not wants_chroma_ground(mood), f"{mood} 的 dom 里没有彩底，不该留名额")
        for dark in (False, True):
            got = generate(cat, mood=mood, n=6, dark=dark)
            bad = [p.dominant.name for p in got if "彩底" in p.dominant.roles]
            check(not bad, f"{mood} dark={dark} 不许出彩底做底，实得 {bad}")
    for mood in ("艳", "浓烈", "市井"):
        check(wants_chroma_ground(mood), f"{mood} 的 dom 里有彩底，应留名额")
        got = generate(cat, mood=mood, n=5)
        check(any("彩底" in p.dominant.roles for p in got),
              f"{mood} n=5 应有一套彩底做底，实得 {[p.dominant.name for p in got]}")
    check(not wants_chroma_ground("艳", dark=True),
          "dark 走 (深底, 墨色)、不读 dom，深色方案由深底承担，不另留彩底名额")

    # complete 两种读法并列
    pair = complete_pair(cat, "苋菜红", "汉白玉", mood="艳")
    doms = {p.dominant.name for p in pair}
    check("汉白玉" in doms and "苋菜红" in doms,
          f"complete(苋菜红,汉白玉) 应同时给白地与红地两种读法，实得 {doms}")
    check(len(pair) == 6, f"两种读法各留 3 套，共 6 条，实得 {len(pair)}")
    check(all("彩底" not in p.dominant.roles for p in pair[:3]),
          "素底读法排在前，彩底读法在后")
    # 翻不过来的就只给一种，不许硬凑第二种
    zh = complete_pair(cat, "朱红", "汉白玉", mood="艳")
    zh_doms = {p.dominant.name for p in zh}
    check(zh_doms == {"汉白玉"},
          f"朱红 不能做底，complete 只该出白地一种读法，实得 {zh_doms}")


def test_generate() -> None:
    cat = Catalog()
    for scene, must_have in [
        ("故宫", {"汉白玉", "酪黄", "朱红", "姜黄", "银朱", "茶褐", "苋菜红", "金盏黄"}),
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
    from engine import contrast, delta_e, tokens
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
                    "secondary", "secondary_fg", "accent", "accent_fg",
                    "accent_hover", "accent_active",
                    "success", "success_fg", "warning", "warning_fg",
                    "error", "error_fg", "info", "info_fg", "disabled", "ring"):
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
        # 断言**已输出的** *_fg，不再临时 pick_text 一个从不交付的色。
        # 原先这 20 条断言验的正是 pick_semantic 算完就丢掉的那个 on——
        # 全过，却与交付物无关（下游拿到徽章色后只有 --color-text 可用）。
        for key in ("success", "warning", "error", "info"):
            fg = tok[key + "_fg"]
            check(contrast(fg, tok[key]) >= 4.5,
                  f"{label} {key} 徽章上放不下字：交付的 {key}_fg={fg.name} 实测 "
                  f"{contrast(fg, tok[key]):.2f}:1")
        # 块上的字：块的落位是「卡片与导航」，下游一定在它上面放字。
        # 死区色（库内不存在 4.5 的搭配）不硬断言 4.5——那不是修好，是把缺陷藏起来。
        # 所以断言分两条：能达标的必须达标；达不到的必须仍在大字额度内，
        # 且库内确实换不出更好的（否则就是挑错了，不是死区）。
        sec_fg, sec = tok["secondary_fg"], tok["secondary"]
        got = contrast(sec_fg, sec)
        best = max(contrast(x, sec) for x in cat.colors if x.name != sec.name)
        if best >= 4.5:
            check(got >= 4.5,
                  f"{label} 块上的字 {sec_fg.name} 实测 {got:.2f}:1 应 ≥4.5"
                  f"（库内最高 {best:.2f}:1，够用却没挑到）")
        else:
            check(got >= 3.0,
                  f"{label} {sec.name} 是死区色（库内最高 {best:.2f}:1），"
                  f"块上的字仍须落在大字额度内，实测 {got:.2f}:1")
            check(abs(got - best) < 0.01,
                  f"{label} 死区色 {sec.name} 上应交出库内最好的那个字色，"
                  f"实测 {got:.2f}:1 vs 最高 {best:.2f}:1")
        check(contrast(tok["accent_fg"], tok["accent_hover"]) >= 4.5,
              f"{label} hover 必须可读，库内无安全变体时可以沿用原色")


def test_ui_components() -> None:
    """检查真实组件的配对及交接一致性，覆盖原自检通过但实际失败的方案。"""
    from unittest.mock import patch
    import handoff as ho
    from engine import Palette, apply_family_lock, contrast

    cat = Catalog()
    cases = [
        ("江南", False, ("粉白", "瓦松绿", "苋菜红")),
        ("青花", False, ("雪白", "群青", "鷃蓝")),
        ("宋瓷", False, ("月白", "霁青", "战舰灰")),
        ("水墨", True, ("苍蝇灰", "芦灰", "夕阳红")),
        ("宋瓷", True, ("云杉绿", "飞泉绿", "淡灰绿")),
        (None, True, ("长石灰", "萝兰紫", "灰绿")),
        ("敦煌", False, ("赭石", "群青", "甘草黄")),
    ]
    pairs = [
        ("text", "surface", 4.5), ("muted", "surface", 4.5),
        ("accent_fg", "accent_hover", 4.5), ("accent_fg", "accent_active", 4.5),
        ("border_strong", "surface", 3.0), ("ring", "bg", 3.0),
        ("ring", "surface", 3.0),
    ]
    for scene, dark, names in cases:
        cols = [cat.by_name[n] for n in names]
        pal = Palette(*cols, score_trio(*cols), scene=scene, dark=dark, media="ui")
        raw = tokens(cat, pal)
        fixed, _ = apply_family_lock(cat, raw, scene)
        data = ho.build(cat, pal)
        label = f"{scene or '默认'} dark={dark}"
        for role, key in (("dominant", "bg"), ("secondary", "secondary"), ("accent", "accent")):
            check(data["roles"][role]["hex"] == data["tokens_light"][key]["hex"],
                  f"{label} {role} 的色卡与交接必须一致")
        check(all(raw[k].hex == fixed[k].hex for k in raw),
              f"{label} 直接导出与交接颜色必须一致")
        for fg, bg, need in pairs:
            got = contrast(fixed[fg], fixed[bg])
            check(got >= need, f"{label} {fg}/{bg}={got:.3f} 应 ≥{need}")
            check(f"{fg}_on_{bg}" in data["verify"], f"{label} 交接必须检查 {fg}/{bg}")
        for key in ("accent_hover", "accent_active"):
            anchor, state = fixed["accent"], fixed[key]
            coherent = (state.C <= 14 if anchor.C < 12 else
                        state.C >= anchor.C * 0.5 and ck.hue_delta(state.H, anchor.H) <= 25)
            check(coherent, f"{label} {key} 必须沿用按钮的色相方向")
        check(fixed["surface"].C <= 12, f"{label} 普通面层应保持低彩")
    # 阈值不能用显示值判定：4.499 显示为 4.50，仍然不通过。
    with patch("handoff.contrast", return_value=4.499):
        report = ho._verify(raw)
    check(any(f["check"] == "text_on_bg" for f in report["fail"]),
          "4.499:1 不得四舍五入为合格的 4.5:1")

    # 显式指定的场景外颜色必须保留，问题应可见。
    pinned = Palette(cat.by_name["雪白"], cat.by_name["群青"], cat.by_name["苋菜红"],
                     {}, scene="青花", media="ui")
    fixed, issues = apply_family_lock(cat, tokens(cat, pinned), "青花")
    check(fixed["accent"].name == "苋菜红", "色族检查不得静默换掉指定的按钮色")
    check(any(i["token"] == "accent" and i.get("kept") for i in issues),
          "指定色与场景冲突时要保留并报告")

    paired = ho.build(cat, pal, dark_pal=pal)
    check("verify_dark" in paired, "深色交接必须有实际配对校验")
    check(paired.get("verify_dark") == paired["verify"], "相同颜色的亮暗校验结果应一致")
    quiet = generate(cat, mood="雅", media="ui", n=1)[0]
    check(max(quiet.secondary.C, quiet.accent.C) <= 50,
          "默认素雅 UI 不应优先高彩方案")
    check(min(quiet.secondary.C, quiet.accent.C) < 12 or
          ck.hue_delta(quiet.secondary.H, quiet.accent.H) <= 45,
          "默认素雅 UI 优先同色系或中性色承托")


def test_vernacular() -> None:
    """白话映射必须受回归检验。

    映射规则写在数据文件里而不是提示词散文里，就是为了能跑这组用例——
    换模型或改线索词后，映射漂了会立刻在这里失败，而不是变成
    「颜色好像选得不太对」这种查不出源头的症状。
    """
    from vernacular import Vernacular
    cases_path = ROOT / "references" / "vernacular_cases.jsonl"
    check(cases_path.exists(), "vernacular_cases.jsonl 必须存在")
    if not cases_path.exists():
        return
    cat = Catalog()
    v = Vernacular()
    cases = [json.loads(l) for l in cases_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    check(len(cases) >= 75, f"白话用例 ≥75 条，实际 {len(cases)}")
    bad = 0
    for case in cases:
        it = v.resolve(case["say"], catalog=cat)
        got = {"media": it.media, "mood": it.mood, "scene": it.scene,
               "dark": it.dark, "seed": it.seed, "ambiguity": it.ambiguity}
        for key, want in (case.get("expect") or {}).items():
            if got.get(key) != want:
                bad += 1
                check(False, f"「{case['say']}」{key} 期望 {want} 实得 {got.get(key)}")
        for forbidden in (case.get("forbid_mood") or []):
            if got["mood"] == forbidden:
                bad += 1
                check(False, f"「{case['say']}」不该判成 {forbidden}")
        # 纹样断言：纹样与配色是两条轴，用例可以只断言其中一条
        want_motif = case.get("motif")
        if want_motif:
            ids = [m["id"] for m in it.motifs]
            if want_motif not in ids:
                bad += 1
                check(False, f"「{case['say']}」应命中纹样 {want_motif}，实得 {ids}")
        want_note = case.get("motif_note_contains")
        if want_note:
            if not any(want_note in n for n in it.motif_notes):
                bad += 1
                check(False, f"「{case['say']}」的提醒里应含「{want_note}」，实得 {it.motif_notes}")
        # 「不该命中」也要能断言。撞名（荷花白）与误触（画龙点睛）这两类
        # 只能用反向断言表达——没有它，修好的东西下次会被静默改回去。
        if case.get("no_motif"):
            if it.motifs:
                bad += 1
                check(False, f"「{case['say']}」不该命中任何纹样，实得 "
                             f"{[m['id'] for m in it.motifs]}")
        if case.get("no_motif_note"):
            if it.motif_notes:
                bad += 1
                check(False, f"「{case['say']}」不该带出纹样提醒，实得 {it.motif_notes}")
        forbid_note = case.get("forbid_note_contains")
        if forbid_note:
            hit = [n for n in it.motif_notes if forbid_note in n]
            if hit:
                bad += 1
                check(False, f"「{case['say']}」的提醒里不该含「{forbid_note}」，实得 {hit}")
        if case.get("no_unheard"):
            if it.unheard:
                bad += 1
                check(False, f"「{case['say']}」不该报没接住，实得 {it.unheard}")
    check(bad == 0, f"白话映射全部命中（{len(cases)} 条用例，{bad} 条不符）")

    # 每个进表的线索词都要有用例覆盖，否则表会长成没人验证过的样子
    covered = " ".join(c["say"] for c in cases)
    axes = {a: 0 for a in ("media", "mood", "scene")}
    for axis, value, word, _w in v.cues:
        if axis in axes and word in covered:
            axes[axis] += 1
    for axis, hit in axes.items():
        check(hit >= 8, f"{axis} 轴至少 8 个线索词被用例覆盖，实际 {hit}")


def test_tweak_moods() -> None:
    """微调的终点。两族词的去处与起点无关，逐档爬到不了，所以单独锁。

    louder_map 只认当前档位，不认用户说了哪个词。这对「太素了」够用，
    对整族有固定去处的词不够：「不够气派」从雅爬一格只到艳（要的是压得住），
    「更喜庆」从艳爬一格会到浓烈（要的是红配绿的市井）。louder_to 写死这两族
    的终点，先于 louder_map。反过来不能把终点塞回 louder_map——那会连坐同档位
    的其他词，「太素了，再艳一点」会得到更旧更沉的一路，正是 map_note 要避开的错。
    """
    from vernacular import Vernacular
    v = Vernacular()
    cfg = v.data["tweak"]
    to = cfg.get("louder_to") or {}
    check(to, "tweak.louder_to 必须存在：没有它，整族固定终点的词只能靠改 louder_map，"
              "而那会连坐同档位的其他词")
    for dest, words in to.items():
        check(dest in cfg["louder_map"],
              f"louder_to 的终点「{dest}」必须是真档位（louder_map 的键之一）")
        for w in words:
            check(w in cfg["louder"], f"louder_to 里的「{w}」也必须在 louder 里，"
                                      "否则 hit('louder') 不成立，这一族根本不触发")

    # 气势族：任何起点都直落浓烈。原报告的症状就是它从雅只走到艳。
    for cur in ("空灵", "清冷", "雅", "古朴", "艳", "市井"):
        got = v.tweak("不够有气势，撑不住场", cur)["mood"]
        check(got == "浓烈", f"气势族抱怨从 {cur} 出发应落浓烈，实得 {got}")
    top = v.tweak("不够有气势，撑不住场", "浓烈")
    check(top["mood"] == "浓烈" and not top["actions"] and top["note"],
          f"浓烈已是气势族的顶，应只出提示不出动作，实得 {top['actions']} / {top['note']}")

    # 喜庆族：任何起点都落市井，不是浓烈。市井只从这一路进（tweaks.md 那一行）。
    for txt in ("更喜庆", "要年味", "更喜庆一点"):
        for cur in ("雅", "艳", "浓烈"):
            got = v.tweak(txt, cur)["mood"]
            check(got == "市井", f"「{txt}」从 {cur} 出发应落市井，实得 {got}——"
                                 "把要红配绿的人送进浓烈是给了他没要的东西")
    check(v.tweak("更喜庆", "市井")["mood"] == "市井", "市井已是喜庆族的顶")

    # 素艳轴逐档爬的老行为一条都不许被上面两族连坐
    for txt, cur, want in (("太素了，再艳一点", "雅", "艳"), ("太素", "空灵", "雅"),
                           ("太素", "清冷", "艳"), ("太素", "古朴", "浓烈"),
                           ("太素", "艳", "浓烈"), ("太艳", "艳", "雅"),
                           ("太重", "浓烈", "古朴"), ("太艳", "市井", "艳"),
                           ("太艳", "古朴", "雅")):
        got = v.tweak(txt, cur)["mood"]
        check(got == want, f"「{txt}」从 {cur} 出发应到 {want}，实得 {got}")

    # 带抱怨标记的词绝不进 in.mood：「不够气派」在首轮会被读成「要气派」，词义正好反。
    # 不带标记的方向词（更喜庆、年味、热闹一点）两处同义，允许两边都在——
    # 但两边指的必须是同一个终点，否则首轮和改稿会把同一句话送去两个地方。
    MARKS = ("不够", "太", "没", "寡", "闷")
    mood_words = {w for axis, _val, w, _wt in v.cues if axis == "mood"}
    complaints = [w for w in cfg["louder"] + cfg["quieter"] if any(m in w for m in MARKS)]
    check(len(complaints) >= 15, f"抱怨词该占多数，实得 {len(complaints)} 条")
    leaked = [w for w in complaints if w in mood_words]
    check(not leaked, f"带抱怨标记的词不许出现在 in.mood 里，实得 {leaked}——"
                      "首轮会把「不够气派」读成「要气派」，词义反过来")
    for w in cfg["louder"]:
        if w in mood_words:
            dest = next((d for d, ws in to.items() if w in ws), None)
            axis_moods = {val for axis, val, word, _wt in v.cues
                          if axis == "mood" and word == w}
            check(dest in axis_moods,
                  f"「{w}」两表都在，首轮落 {axis_moods} 而改稿落 {dest}——"
                  "同一句话被送去两个地方，必须对齐")

    # louder 与 quieter 不许互为子串：一句话同时命中两边会被当成没说
    clash = [(a, b) for a in cfg["louder"] for b in cfg["quieter"]
             if a in b or b in a]
    check(not clash, f"louder 与 quieter 互为子串会误触成「方向冲突」，实得 {clash}")


def test_unheard() -> None:
    """接不住的词必须说出来——静默给出一套无关方案是最难被用户察觉的失败。

    同时不能误报：复合词残渣（「茶」命中后剩下的「叶小店」）和中性词
    （中国风、色板）都不是没听懂。
    """
    from vernacular import Vernacular
    cat = Catalog()
    v = Vernacular()
    should_report = ["要有仙气的网站", "做个赛博朋克感觉的界面", "哑光温润的紫砂质感", "要侘寂风"]
    should_not = ["茶叶小店的网站，安静一点", "配个中国风的颜色", "过年活动页，要喜庆",
                  "青花瓷风格的官网", "给个色板", "券商的后台系统，要稳重可信",
                  "博物馆海报要有分量", "新中式民宿的墙面配色", "敦煌展览的主视觉",
                  "做个后台仪表盘，深色模式", "汉服店的电商首页", "婚礼请柬，别太艳"]
    for say in should_report:
        got = v.resolve(say, catalog=cat).unheard
        check(bool(got), f"「{say}」应报出没接住的词，实得 {got}")
    for say in should_not:
        got = v.resolve(say, catalog=cat).unheard
        check(not got, f"「{say}」不该报没接住，误报了 {got}")


def test_airy_areas() -> None:
    """留白型必须真的能大面留白。

    技能自己把空灵说成「几乎是纸」、水墨说成「大面留白」，但目标份额若仍按
    60/30/10 归一化，主场永远到不了 85%——那句话就只是文案。
    """
    from engine import AIRY_MOODS, AIRY_SCENES, visual_areas
    cat = Catalog()
    for kw, label in ((dict(mood="空灵"), "空灵"), (dict(scene="水墨"), "水墨"),
                      (dict(scene="宋瓷"), "宋瓷")):
        pals = generate(cat, media="ui", n=1, **kw)
        check(bool(pals), f"{label} 应有方案")
        if not pals:
            continue
        area = visual_areas(pals[0])
        check(area["airy"] is True, f"{label} 应判定为留白型")
        dom = area["pixel_pct"]["dominant"]
        check(dom >= 88.0, f"{label} 主场应 ≥88%，实得 {dom}%")
        # 但点缀仍要可点、结构仍要成块，不能被留白挤成 0
        check(area["pixel_pct"]["accent"] >= 2.0, f"{label} 点缀不得小于 2%（要点得着）")
        check(area["pixel_pct"]["secondary"] >= 6.0, f"{label} 结构不得小于 6%")
    # 常规方案不受影响
    for kw, label in ((dict(scene="年画"), "年画"), (dict(scene="敦煌"), "敦煌")):
        pals = generate(cat, media="ui", n=1, **kw)
        if not pals:
            continue
        area = visual_areas(pals[0])
        check(area["airy"] is False, f"{label} 不该判定为留白型")
        check(area["pixel_pct"]["secondary"] >= 16.0,
              f"{label} 结构下限仍应是 16%，实得 {area['pixel_pct']['secondary']}%")


def test_gold_names() -> None:
    """金白名单里不许有橙。名字带金不等于是金属色。"""
    from engine import GOLD_NAMES
    cat = Catalog()
    for name in GOLD_NAMES:
        c = cat.by_name.get(name)
        check(c is not None, f"金名单里的 {name} 必须在库内")
        if c is None:
            continue
        check(70 <= c.H <= 100, f"{name} 实测 H{c.H:.1f}，金必须落在黄区 70–100")
    for name in ("金黄", "金驼", "金莲花橙", "金鱼紫"):
        check(name not in GOLD_NAMES, f"{name} 实测不在黄区，不该进金名单")


def test_motifs() -> None:
    """纹样是点缀，不是第四个配比色。这组断言守的就是这条。"""
    from engine import SCENES
    from vernacular import SEASON_CUES, Vernacular
    path = ROOT / "references" / "motifs.json"
    check(path.exists(), "motifs.json 必须存在")
    if not path.exists():
        return

    def no_dup(pairs):
        seen = set()
        for k, _ in pairs:
            if k in seen:
                raise ValueError("DUPLICATE KEY: " + k)
            seen.add(k)
        return dict(pairs)

    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_dup)
    ms = data["motifs"]
    check(len(ms) >= 16, f"纹样 ≥16 条，实际 {len(ms)}")
    ids = [m["id"] for m in ms]
    check(len(set(ids)) == len(ids), "纹样 id 必须唯一")
    # CLI 的 --category 选项必须每档都有货。空选项是陷阱：用户照 --help
    # 跑 `motifs --category vessel` 会得到「0 个纹样」。
    from collections import Counter
    cats = Counter(m["category"] for m in ms)
    check("flora" in cats and "landscape" in cats and "geometric" in cats,
          f"三类主分类都必须有货，实得 {dict(cats)}")
    check("vessel" not in cats,
          f"vessel 当前无货（{cats.get('vessel', 0)} 条），不该出现在 --category 选项里")
    # CLI 与文档都不该提当前无货的类别。问 --help 比读源码字符串稳。
    import subprocess as _sp
    env0 = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", NO_COLOR="1")
    h = _sp.run([sys.executable, str(ROOT / "scripts" / "palette.py"), "motifs", "--help"],
                capture_output=True, text=True, encoding="utf-8", env=env0, cwd=str(ROOT))
    for cat_name in ("flora", "landscape", "geometric"):
        check(cat_name in h.stdout, f"--help 里应有类别 {cat_name}")
    for empty in [c for c in ("vessel",) if c not in cats]:
        check(empty not in h.stdout,
              f"--help 里不该有空类别 {empty}——用户照它跑会得到「0 个纹样」")
        for doc in ("README.md", "references/motifs.md"):
            txt = (ROOT / doc).read_text(encoding="utf-8")
            check(empty not in txt, f"{doc} 里不该提空类别 {empty}")

    # 核心约束：资产里不许有任何色值，只许借 token
    # `set(TOKEN_KEYS)` 会让每个新加的 token 自动变成纹样可借的合法源——
    # 前景色（块上/徽章上的字）绝不能这样默认放行：它们各欠一份 4.5:1 的对比义务，
    # 借给装饰层等于让纹样跟着字色走。所以显式减掉，白名单以 ink_sources 为准。
    FG_TOKENS = {"secondary_fg", "success_fg", "warning_fg", "error_fg", "info_fg"}
    LEGAL = (set(TOKEN_KEYS) - FG_TOKENS) | {"bg"}
    for k in FG_TOKENS:
        check(k in TOKEN_KEYS, f"{k} 应是已交付的 token（这条守住上面的减法不是空操作）")
        check(k not in LEGAL, f"{k} 是前景色，不许成为纹样的合法借色源")
    for m in ms:
        blob = json.dumps(m, ensure_ascii=False)
        check("#" not in blob, f"{m['id']} 里不许出现 hex——纹样借色，不带色")
        borrows = m.get("borrows_token") or []
        check(bool(borrows), f"{m['id']} 必须写明借哪个 token")
        for b in borrows:
            check(b in LEGAL, f"{m['id']} 借的 {b} 不是合法 token")
        for key in ("fits_scenes", "avoid_scenes"):
            bad = [s for s in (m.get(key) or []) if s not in SCENES]
            check(not bad, f"{m['id']} 的 {key} 含非法场景 {bad}")

    # 成套引用必须闭合
    for name, spec in (data.get("sets") or {}).items():
        miss = [x for x in (spec.get("members") or []) if x not in ids]
        check(not miss, f"成套「{name}」引用了不存在的纹样 {miss}")
    refs = {p for m in ms for p in (m.get("pairs_with") or [])}
    check(not (refs - set(data.get("sets") or {})),
          f"pairs_with 引用了未定义的套 {refs - set(data.get('sets') or {})}")

    # pairs_with 不许是死数据：声明属于某套却既不在 members 里、也没给
    # stands_for 折算到正位的，那条声明永远不参与判定。
    # 实测过 6 处（疏影横斜、兰叶小丛、折枝竹叶、竹石一角），于是
    # 「疏影横斜配折枝竹叶」这种梅竹无松一声不响——那正是 SKILL.md 承诺会拦的。
    for m in ms:
        for s in (m.get("pairs_with") or []):
            members = set((data["sets"].get(s) or {}).get("members") or [])
            stands = m.get("stands_for")
            check(m["id"] in members or (stands and stands in members),
                  f"{m['id']} 声明属于「{s}」，却既不在其 members 也没 stands_for 折算——"
                  f"这条声明是死数据")
        if m.get("stands_for"):
            check(m["stands_for"] in ids, f"{m['id']} 的 stands_for 指向不存在的 {m['stands_for']}")
            check(m["stands_for"] != m["id"], f"{m['id']} 的 stands_for 不该指向自己")

    # 别名必须 ≥2 字，且不得是现有线索词的子串——否则会误触发。
    # 实测过的三个坑：荷 会在「薄荷绿」里命中，松 会在「轻松」里命中，
    # 石 被「石窟/石青」占满。
    v = Vernacular()

    # 落在色名里的线索词不许选轴。词表有 40 条单字线索，
    # 冬（→清冷）、漆（→漆器）、夜（→dark）、野（→市井）这类会落进
    # 任何含该字的色名。实测伤害：「用漆黑做底」判成漆器场景 3.0 分，
    # 「夜灰做底色」判成深色模式——夜灰是浅底方案里的一个色名。
    cat_s = Catalog()
    for say, seed_want in [("用漆黑做底", "漆黑"), ("夜灰做底色", "夜灰"),
                           ("主色野葡萄紫", "野葡萄紫"), ("茶褐色的页面", "茶褐")]:
        it_s = v.resolve(say, catalog=cat_s)
        check(it_s.seed == seed_want, f"「{say}」应解析出 seed {seed_want}，实得 {it_s.seed}")
        check(it_s.scene is None, f"「{say}」的色名不该选出场景，实得 {it_s.scene}")
        check(not it_s.dark, f"「{say}」的色名不该判成深色，实得 dark={it_s.dark}")
    # 遮蔽不许过头：色名之外真说了那个轴仍要命中
    it_s = v.resolve("用漆黑做底，走漆器那套", catalog=cat_s)
    check(it_s.seed == "漆黑" and it_s.scene == "漆器",
          f"色名外真说了场景仍要命中，实得 seed={it_s.seed} scene={it_s.scene}")
    it_s = v.resolve("古朴一点，用淡灰绿", catalog=cat_s)
    check(it_s.mood == "古朴" and it_s.seed == "淡灰绿",
          f"色名外真说了氛围仍要命中，实得 mood={it_s.mood} seed={it_s.seed}")
    for m in ms:
        for al in (m.get("aliases") or []):
            check(len(al) >= 2, f"{m['id']} 的别名「{al}」太短，会误触发")
            hit = [c for _a, _v, c, _w in v.cues if al != c and al in c]
            check(not hit, f"{m['id']} 的别名「{al}」是现有线索词 {hit[:2]} 的子串，会误触发")

    # 别名不许夹带**方向相反**的单字线索。纹样别名不进色名遮蔽
    # （纹样与场景是互补的两条轴，「竹子多的院子」该同时得到竹纹与江南），
    # 代价就是纹样名自己不能夹带反方向的单字线索。
    #
    # 只查氛围的冷暖冲突。场景与场景不算冲突——`梅`→江南 与 水墨/宋瓷 是同族
    # 文人语汇，评分自会挑一个。真正的伤害是暖场景被判成冷：忍冬纹 里的
    # `冬`→清冷 会把敦煌的暖矿物色推冷，而用户说的是一种卷草。撞了改同义名
    # （忍冬纹 -> 卷草纹）。反过来 冰裂纹 的 `冰`→清冷 与宋瓷一致，不算夹带。
    WARM = {"敦煌", "年画", "唐三彩", "故宫", "漆器", "王府"}
    COLD_MOODS = ("清冷", "空灵")
    for m in ms:
        fits = set(m.get("fits_scenes") or [])
        if not (fits & WARM) or (fits - WARM):
            continue  # 只管纯暖场景的纹样；跨冷暖的本就两头沾
        for al in (m.get("aliases") or []):
            for axis, value, cue, _w in v.cues:
                if len(cue) == 1 and cue in al and axis == "mood" and value in COLD_MOODS:
                    check(False, f"{m['id']} 的别名「{al}」夹带单字线索「{cue}」"
                                 f"（→{value}），而它只适配暖场景 {sorted(fits)}——"
                                 f"改用不含该字的同义名")

    # ink_pct 必须是可打印的纯区间串，ink_range 必须是可计算的数值对。
    # 混在一起会同时坏两头：打印出「墨量 框内着墨 ≤8%」（拼死一个 %），
    # 且 charge_rule 的公式没法算，「纹样不占配比」就只是文案。
    for m in ms:
        pct = m.get("ink_pct")
        check(isinstance(pct, str) and re.fullmatch(r"(≤\s*)?[0-9.]+(\s*-\s*[0-9.]+)?", pct or ""),
              f"{m['id']} 的 ink_pct「{pct}」不是纯区间串，散文要放 ink_note")
        rng = m.get("ink_range")
        check(isinstance(rng, list) and len(rng) == 2
              and all(isinstance(x, (int, float)) for x in rng)
              and rng[0] <= rng[1],
              f"{m['id']} 的 ink_range 必须是 [lo, hi] 数值对，实得 {rng}")
        if isinstance(rng, list) and len(rng) == 2 and isinstance(pct, str):
            hi = pct.split("-")[-1].replace("≤", "").strip()
            check(abs(float(hi) - float(rng[1])) < 1e-9,
                  f"{m['id']} 的 ink_range 上界与 ink_pct 不一致：{rng[1]} vs {hi}")

    # 撞名：纹样别名不许是色名或色别名的子串。实测四处
    # 荷花 ⊂ 荷花白、莲花 ⊂ 金莲花橙、荷叶 ⊂ 荷叶绿、远山 ⊂ 远山紫。
    # 数据侧不强制它们消失（荷花本来就该是荷花的线索词），代码侧按
    # 「更长的色名遮蔽更短的纹样别名」处理，这里验那个遮蔽真的生效。
    cat0 = Catalog()
    allnames = [n for n in list(cat0.by_name) + list(cat0.aliases) if len(n) >= 2]
    collide = [(m["id"], al, n) for m in ms for al in (m.get("aliases") or [])
               for n in allnames if al in n and al != n]
    for mid, al, name in collide:
        it0 = v.resolve(f"用{name}做底色的网站", catalog=cat0)
        check(mid not in [x["id"] for x in it0.motifs],
              f"「{name}」是色名，不该唤出纹样 {mid}（别名「{al}」被它整段盖住）")
        check(not it0.motif_notes,
              f"「{name}」是色名，不该带出纹样提醒：{it0.motif_notes[:1]}")
    # 遮蔽不许过头：色名之外单说别名仍要命中
    for mid, al, _name in collide:
        it0 = v.resolve(f"页面上加一点{al}", catalog=cat0)
        check(mid in [x["id"] for x in it0.motifs],
              f"单说「{al}」应仍命中纹样 {mid}，遮蔽做过头了")

    # 禁忌与成套的 match 键不许落进普通产品话。全是实测踩过的：
    # 画龙→画龙点睛、四爪→四爪抓手、圆补/方补→圆补丁、填金/满金→填金色/满金币、
    # 龙凤→龙凤胎、三友→三友咖啡。这一组是那些短键的回归。
    INNOCENT = [
        "画龙点睛的落地页", "三友咖啡的网站", "会员按等级解锁功能的后台",
        "四爪的抓手图标", "圆补丁风格的卡片", "填金色的按钮", "方补丁样式的标签",
        "满金币充值页", "龙凤胎母婴用品店", "巨蟒健身房的官网",
    ]
    for say in INNOCENT:
        tb = [x["what"] for x in v.taboo_check(say)]
        st = [n for n, _ in v.match_sets(say)]
        check(not tb, f"「{say}」不该触发礼制禁忌 {tb}")
        check(not st, f"「{say}」不该触发成套提醒 {st}")
    # 反面：真提到了就必须拦住
    MUST = [("想用五爪龙做 logo", "五爪龙"), ("四爪龙的图腾", "四爪龙"),
            ("龙凤呈祥的婚庆页", "龙凤"), ("十二章纹的博物馆页", "十二章"),
            ("大面积填金的封面", "填金")]
    for say, want in MUST:
        tb = [x["what"] for x in v.taboo_check(say)]
        check(any(want in w for w in tb), f"「{say}」应触发禁忌，实得 {tb}")
    for say, want in [("梅兰竹菊四条屏", "四君子"), ("岁寒三友的插画", "岁寒三友"),
                      ("三远法的山水页", "三远")]:
        st = [n for n, _ in v.match_sets(say)]
        check(want in st, f"「{say}」应触发成套 {want}，实得 {st}")

    # alpha 上限必须覆盖所有可压文字的纹样所借的 token
    ceil = data.get("alpha_ceilings") or {}
    for m in ms:
        if not m.get("under_text"):
            continue
        for b in (m.get("borrows_token") or []):
            check(b in ceil, f"{m['id']} 可压文字却没给 {b} 的 alpha 上限")

    # 借色白名单：交互态、语义徽章、失能态、焦点环不许借给装饰层
    allowed = set((data.get("ink_sources") or {}).get("allowed") or [])
    check(bool(allowed), "必须给出合法借色源白名单")
    for forbidden in ("accent_fg", "accent_hover", "success", "warning", "disabled", "ring",
                      # 块上与徽章上的字：前景色不许借给装饰层
                      "secondary_fg", "success_fg", "warning_fg", "error_fg", "info_fg"):
        check(forbidden not in allowed, f"{forbidden} 不该在借色白名单里")
    for m in ms:
        for b in (m.get("borrows_token") or []):
            check(b in allowed, f"{m['id']} 借的 {b} 不在白名单")

    # 彩度闸门：压文字的纹样不许把合成彩度抬起来变成第四个色块
    import handoff as ho
    gate = (data.get("chroma_gate") or {}).get("max_delta_c")
    check(gate is not None, "必须给出彩度抬升上限")
    cat2 = Catalog()
    for scene in ("水墨", "青花", "故宫", "年画"):
        pals = generate(cat2, scene=scene, media="ui", n=1)
        if not pals:
            continue
        # 锁后的 token 才是 production 用的那一套（build() 里的 tok_light）。
        # 锁前锁后能差很远：故宫 border_strong 锁前鲛青 C=31.6、锁后锌灰 C=2.9，
        # 用锁前的验会把一条正常纹样判成超额。
        tok = ho.apply_family_lock(cat2, tokens(cat2, pals[0]), pals[0].scene)[0]
        accent_pct = visual_areas(pals[0])["pixel_pct"]["accent"]
        for m in ms:
            if scene in (m.get("avoid_scenes") or []):
                continue
            probs = [p for p in ho.check_ornament(cat2, tok, m, 0.08, scene=scene,
                                                  accent_pct=accent_pct)
                     if not p.get("soft")]
            check(not probs, f"{scene} 的 {m['id']} 在默认 alpha 下应合规：{probs[:1]}")
        # 反例必须被抓住
        bad = {"id": "x", "borrows_token": ["accent"], "under_text": True}
        if tok["accent"].C >= 40:
            check(bool(ho.check_ornament(cat2, tok, bad, 0.20)),
                  f"{scene} 压文字借高彩 accent 应被彩度闸门挡住")
        # avoid_scenes 必须在这里也被拦住。ask 那条路会解释后丢弃，
        # pick 原先直接照出——同一条规则两个入口给不同答案。
        for m in ms:
            if scene not in (m.get("avoid_scenes") or []):
                continue
            probs = ho.check_ornament(cat2, tok, m, 0.08, scene=scene)
            check(any("气质不合" in p["problem"] for p in probs),
                  f"{m['id']} avoid 了 {scene}，check_ornament 应拦住，实得 {probs[:1]}")
        # 备选借色也要过闸门，不能只验首选
        alt = {"id": "alt", "borrows_token": ["border", "accent"], "under_text": True}
        if tok["accent"].C >= 40:
            probs = ho.check_ornament(cat2, tok, alt, 0.20)
            check(any("accent" in p["problem"] for p in probs),
                  f"{scene} 的备选借色 accent 也该过闸门，实得 {probs}")

    # 禁忌必须有显式 match 词表与替代方案
    for item in (data.get("taboo") or {}).get("items", []):
        check(bool(item.get("match")), f"禁忌「{item['what']}」缺 match 词表")
        check(bool(item.get("instead")), f"禁忌「{item['what']}」缺替代路径——拒绝要给出路")

    # 纹样表读不出来必须响亮地失败，两个加载点行为要一致。
    # 回落成空表的症状是「你输的纹样 id 不存在」或「我没听懂你说的荷花」——
    # 把数据文件的语法错报成用户的错，那是错得没有症状。
    import importlib
    import tempfile
    import handoff as ho2
    bad_json = Path(tempfile.gettempdir()) / "zgs-bad-motifs.json"
    bad_json.write_text("{ not json", encoding="utf-8")
    for mod, attr in ((ho2, "MOTIFS_PATH"), (importlib.import_module("vernacular"), "MOTIFS_PATH")):
        orig = getattr(mod, attr)
        cache_attr = "_MOTIFS_CACHE" if mod is ho2 else None
        orig_cache = getattr(mod, cache_attr) if cache_attr else None
        try:
            setattr(mod, attr, bad_json)
            if cache_attr:
                setattr(mod, cache_attr, None)
                raised = False
                try:
                    mod._load_motifs()
                except SystemExit:
                    raised = True
                check(raised, f"{mod.__name__}._load_motifs 读到坏 JSON 应 SystemExit，不许回落空表")
            else:
                v2 = Vernacular()
                raised = False
                try:
                    v2._load_motifs()
                except SystemExit:
                    raised = True
                check(raised, f"{mod.__name__}._load_motifs 读到坏 JSON 应 SystemExit，不许回落空表")
        finally:
            setattr(mod, attr, orig)
            if cache_attr:
                setattr(mod, cache_attr, orig_cache)
    bad_json.unlink(missing_ok=True)

    # 季节冲突要能被抓到
    cat = Catalog()
    it = v.resolve("岁末的活动页，加点荷花", catalog=cat)
    check(any("夏" in n for n in it.motif_notes),
          f"冬季配夏季纹样应报季节冲突，实得 {it.motif_notes}")
    # 纹样词不许再报成没接住
    for say in ("荷花", "水墨远山", "来点竹子", "页脚加一条远山"):
        it = v.resolve(say, catalog=cat)
        check(bool(it.motifs), f"「{say}」应命中纹样")
        check(not it.unheard or all("远山" not in u and "荷花" not in u and "竹子" not in u
                                    for u in it.unheard),
              f"「{say}」的纹样词不该报成没接住：{it.unheard}")
    # 礼制纹样要挡住并给替代
    it = v.resolve("想用五爪龙做 logo", catalog=cat)
    check(any("五爪龙" in n and "改法" in n for n in it.motif_notes),
          "五爪龙应被挡住并给替代方案")
    # 季节线索必须真能读出——每一个词，不只是首词。
    # 只测首词的话，「消暑」「重阳」「金秋」「过年」这类长尾说法从未被读过一次，
    # 而它们才是真实说法，也是这一轴的价值所在。
    for season, cues in SEASON_CUES.items():
        for cue in cues:
            got = v.season_of(cue)
            check(got == season, f"季节线索「{cue}」应读出 {season}，实得 {got}")
    # 跨季节不许有子串冲突：season_of 取最长匹配，若「小春」进了冬档
    # 就会污染「春」的判定。加词时这条会先红。
    for s1, c1 in SEASON_CUES.items():
        for s2, c2 in SEASON_CUES.items():
            if s1 == s2:
                continue
            clash = [(a, b) for a in c1 for b in c2 if a in b or b in a]
            check(not clash, f"季节词跨档相撞：{s1} 与 {s2} 之间 {clash[:2]}")
    # 最常见的冬季说法必须能驱动季节提醒
    for say in ("过年活动页，加点菊花", "春节的页面，加折枝菊"):
        it = v.resolve(say, catalog=cat)
        check(any("秋" in n for n in it.motif_notes),
              f"「{say}」应报季节冲突（菊属秋），实得 {it.motif_notes}")

    # season_rigidity 的每个档位都要有可观测行为。mid 原先与 none 同路，
    # 等于那一档白填：折枝梅标着 mid，「盛夏加一枝梅花」却一声不响。
    rigs = {m.get("season_rigidity") for m in ms}
    for rig in rigs:
        check(rig in ("high", "mid", "none"), f"未知的季节刚性档 {rig}")
    it = v.resolve("盛夏的活动页，加一枝梅花", catalog=cat)
    check(any("季节" in n or "花" in n and "夏" in n for n in it.motif_notes),
          f"mid 档纹样季节错也要提醒（梅开盛夏），实得 {it.motif_notes}")
    it = v.resolve("春天的海报，加折枝菊", catalog=cat)
    check(any("最容易被看出来" in n for n in it.motif_notes),
          f"high 档要硬提醒，实得 {it.motif_notes}")

    # 被场景挡掉的纹样词不许既解释又报没接住——那是同一个矛盾换了方向
    it = v.resolve("年画风格的活动页，加点荷花", catalog=cat)
    check(any("气质不合" in n for n in it.motif_notes),
          f"年画配荷花应解释被挡的原因，实得 {it.motif_notes}")
    check(not any("荷花" in u for u in it.unheard),
          f"已解释过的纹样词不该再报成没接住：{it.unheard}")

    # 季节只在真起作用时才算听懂。没纹样时说了「秋天」而我们什么都没做，
    # 那就该报没接住——静默吞掉是把一次失败伪装成成功。
    it = v.resolve("秋天的网站", catalog=cat)
    check(not it.motifs, "「秋天的网站」不该凭空生出纹样")
    check(any("秋天" in u for u in it.unheard),
          f"没纹样时季节没起作用，应报没接住，实得 {it.unheard}")
    # 起作用时要回读进解读行
    it = v.resolve("岁末的活动页，加点荷花", catalog=cat)
    check(any("冬" in e for e in it.echo),
          f"季节起了作用就要回读，实得 {it.echo}")


def test_ornament_handoff() -> None:
    """交接段：下游只能拿到「借哪个变量」，不能拿到可以随手改的 hex 渲染入口。"""
    import handoff as ho
    cat = Catalog()
    pals = generate(cat, scene="水墨", media="ui", n=1)
    # 先断言再 return。裸 `if not pals: return` 会让整个函数 0 条断言静默通过——
    # 水墨出不了方案时，这一整组纹样交接的检查就凭空消失了，而末行仍写「全部通过」。
    check(bool(pals), "水墨应能出方案（否则下面整组纹样交接断言全部跳过）")
    if not pals:
        return
    data = ho.build(cat, pals[0], motif_ids=["mei-zhezhi", "yuanshan-yixian"])
    orn = data.get("ornament")
    check(bool(orn), "handoff 必须有 ornament 段")
    if not orn:
        return
    for seg in ("prime_rule", "chosen", "suggestions", "render", "alpha_ceilings",
                "budget", "sets", "taboo", "a11y"):
        check(seg in orn, f"ornament 缺 {seg}")
    check(len(orn["chosen"]) == 2, f"应选中 2 个纹样，实得 {len(orn['chosen'])}")
    for c in orn["chosen"]:
        check(c["borrows_var"].startswith("--color-"),
              f"{c['name']} 必须借 CSS 变量，实得 {c['borrows_var']}")
        check(c.get("ink_pct") is not None, f"{c['name']} 缺墨量")
        check(c.get("placement"), f"{c['name']} 缺落位")
        # 画法细则要一起交。form 只有两字，反俗硬规则全在 form_detail 里。
        check(c.get("form_detail"), f"{c['name']} 缺画法细则（form_detail）")
    check(orn["render"]["preferred"] == "mask", "渲染首选应是 mask")
    check(len(orn["render"]["must_not"]) >= 3, "必须列出禁止的渲染形态")
    # 墨量预算与配比额度是两套账，但要给出耦合规则
    check("charge" in orn["budget"] and orn["budget"]["charge"],
          "必须给出彩度型借色的计费规则")
    check(orn["budget"].get("accent_pct") is not None, "必须给出 accent 额度供计费")

    # 计费必须真算出来，不能只发公式。散文式的 charge_rule 谁也执行不了：
    # 「纹样不占配比」这句话的兑现就在这个数上。
    #
    # 必须在彩色场景里验。水墨的 accent 自己就是银灰 C=10.8（<12 的中性档），
    # 那里所有纹样都零计费——在水墨里验「至少有一条算得出计费」永远失败，
    # 而失败原因与计费逻辑无关。
    motifs_all = {m["id"]: m for m in json.loads(
        (ROOT / "references" / "motifs.json").read_text(encoding="utf-8"))["motifs"]}
    cpals = generate(cat, scene="年画", media="ui", n=1)
    if cpals:
        # 用锁后的 token：production 走的是 build() 里的 tok_light，那是锁过的。
        # 锁前锁后能差很远（故宫 border_strong 锁前鲛青 C=31.6、锁后锌灰 C=2.9）。
        ctok = ho.apply_family_lock(cat, tokens(cat, cpals[0]), cpals[0].scene)[0]
        capct = visual_areas(cpals[0])["pixel_pct"]["accent"]
        charged = [ho.ink_charge(m, ctok, capct) for m in motifs_all.values()]
        real = [c for c in charged if c]
        check(bool(real), "彩色场景里至少要有一个纹样算得出计费（借彩度色的那些）")
        for c in real:
            check(isinstance(c["charge_pct"], float) and c["charge_pct"] >= 0,
                  f"计费必须是数，实得 {c['charge_pct']}")
            check(c["cap_pct"] > 0, "计费上限必须为正")
        # 中性借色零计费。判据是**实测彩度**，不是 token 叫什么名字：
        # 年画的 surface 是荔肉白 C=13.2、border 是菊蕾白 C=20.8，都在彩度档。
        # 按 token 名断言会在这里失败，而失败原因与计费逻辑无关。
        neutral_tok = next((k for k in ("text", "muted", "surface", "border")
                            if k in ctok and ctok[k].C < 12), None)
        check(neutral_tok is not None, "年画里应至少有一个中性 token 可供验零计费")
        if neutral_tok:
            neu = {"id": "neu", "borrows_token": [neutral_tok], "ink_range": [0, 99]}
            check(ho.ink_charge(neu, ctok, capct) is None,
                  f"借中性 {neutral_tok}（C={ctok[neutral_tok].C:.1f}）应零计费")
        # 反面：同一个纹样借彩度色就要计费
        chroma_tok = next((k for k in ("accent", "secondary", "border")
                           if k in ctok and ctok[k].C >= 12), None)
        if chroma_tok:
            ch = {"id": "ch", "borrows_token": [chroma_tok], "ink_range": [0, 1]}
            check(ho.ink_charge(ch, ctok, capct) is not None,
                  f"借彩度 {chroma_tok}（C={ctok[chroma_tok].C:.1f}）必须计费")
        # 超额必须被 issues 抓住
        greedy = {"id": "greedy", "borrows_token": ["accent"], "ink_range": [0, 99],
                  "under_text": False}
        probs = ho.check_ornament(cat, ctok, greedy, 0.08, accent_pct=capct)
        check(any("超过点缀额度" in p["problem"] for p in probs),
              f"墨量 99% 借 accent 应被计费上限挡住，实得 {probs}")

    # suggestions 必须真适配场景，不能只是「没被明确排除」。
    # 年画场景下曾经 8 条推荐里 7 条自己的 fits_scenes 都没写年画。
    for scene in ("年画", "水墨", "敦煌", "唐三彩"):
        ps = generate(cat, scene=scene, media="ui", n=1)
        if not ps:
            continue
        sug = ho.build(cat, ps[0])["ornament"]["suggestions"]
        for mid in sug:
            fits = motifs_all[mid].get("fits_scenes") or []
            check(not fits or scene in fits,
                  f"{scene} 的推荐 {mid} 自己的适配场景是 {fits}，不该出现在这里")

    # 拼错的 id 必须报出来。早先 JSON 里带了 unknown_ids 但 CLI 不打印，
    # 只查 JSON 的断言抓不到——所以这里连 CLI 输出一起验。
    d2 = ho.build(cat, pals[0], motif_ids=["mei-zhezhi", "no-such-motif"])
    check(d2["ornament"]["unknown_ids"] == ["no-such-motif"],
          f"未知纹样 id 应被记录，实得 {d2['ornament'].get('unknown_ids')}")
    import subprocess
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", NO_COLOR="1")
    tmp = ROOT / ".selftest-orn"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "palette.py"), "pick",
                        "鱼肚白+战舰灰+银朱", "--scene", "水墨", "--media", "ui",
                        "--motif", "mei-zhezhi", "--motif", "no-such-motif",
                        "--out", str(tmp)],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
    # 退出码要先验。只查 stdout 的话，子进程崩了会报成
    # 「pick 应打印选中的纹样」——把 traceback 伪装成一条内容缺失。
    check(r.returncode == 0, f"pick 应正常退出，实得 {r.returncode}：{r.stderr[-300:]}")
    check("折枝梅" in r.stdout, "pick 应打印选中的纹样")
    check("不存在" in r.stdout, "pick 应报出拼错的纹样 id")
    check("借 --color-" in r.stdout, "pick 应说明纹样借哪个变量")
    check("墨量" in r.stdout and "框内着墨" not in r.stdout,
          "墨量要打成纯百分数，限定说明另起（原先打出「墨量 框内着墨 ≤8%」）")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)

    # 纹样自己的问题必须打到用户面前。锦地开光 avoid 了水墨，
    # pick 原先照出还不报——彩度闸门、alpha 上限全算了却没人看见。
    r2 = subprocess.run([sys.executable, str(ROOT / "scripts" / "palette.py"), "pick",
                         "鱼肚白+战舰灰+银朱", "--scene", "水墨", "--media", "ui",
                         "--motif", "jindi-kaiguang", "--out", str(tmp)],
                        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
    check(r2.returncode == 0, f"pick 应正常退出，实得 {r2.returncode}")
    check("气质不合" in r2.stdout,
          f"pick 用了 avoid_scenes 的纹样必须报出来，实得尾部 {r2.stdout[-200:]}")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)


def test_documented_commands() -> None:
    """README 里写出来的命令必须都能跑。

    文档里的命令是给人照抄的，抄了跑不通比没写更糟。这一组曾经抓到
    README 的 generate 旗标表里写了 --pin 而 CLI 没实现。
    """
    import subprocess
    script = str(ROOT / "scripts" / "palette.py")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", NO_COLOR="1")
    tmp = ROOT / ".selftest-tmp"
    cases = [
        ["ask", "茶叶小店的网站，安静一点", "--no-bar", "--n", "1"],
        ["ask", "配个中国风的颜色", "--no-bar", "--n", "1", "--css"],
        ["resolve", "券商的后台系统，要稳重可信"],
        ["tweak", "太素了，再艳一点", "--mood", "雅", "--no-bar", "--n", "1"],
        ["tweak", "换个底，其他别动", "--from", "鱼肚白+战舰灰+银朱",
         "--keep", "secondary", "--keep", "accent", "--no-bar", "--n", "1"],
        ["pick", "鱼肚白+战舰灰+银朱", "--scene", "水墨", "--media", "ui",
         "--pair-dark", "--out", str(tmp)],
        ["info", "石青"],
        ["info", "中国红"],
        ["snap", "#c1272d"],
        ["search", "--family", "青", "--role", "点缀"],
        ["search", "--wuxing", "木", "--season", "春", "--limit", "10"],
        ["generate", "--scene", "青花", "--n", "1"],
        ["generate", "--scene", "补服", "--media", "ui", "--n", "1"],
        ["generate", "--seed", "朱红", "--mood", "艳", "--n", "1"],
        ["generate", "--pin", "accent=枫叶红", "--media", "ui", "--n", "1"],
        ["generate", "--scene", "水墨", "--media", "ui", "--dark", "--n", "1"],
        ["generate", "--mood", "雅", "--media", "ui", "--n", "1", "--tailwind"],
        ["complete", "月白", "群青"],
        ["preview", "--scene", "水墨", "--media", "ui", "--n", "2",
         "--out", str(tmp / "p.html")],
        ["motifs"],
        ["motifs", "--scene", "水墨"],
        ["motifs", "--category", "landscape"],
        ["motifs", "--scene", "年画"],
    ]
    for argv in cases:
        r = subprocess.run([sys.executable, script] + argv, capture_output=True,
                           text=True, encoding="utf-8", env=env, cwd=str(ROOT))
        check(r.returncode == 0,
              f"README 命令应可跑: palette.py {' '.join(argv[:3])} … "
              f"（退出码 {r.returncode}）")
        if argv[0] == "search":
            # 文档里的检索示例不许返回空。空结果会让读者以为库里没有那种色，
            # 而真正原因往往是筛选维度按字面太窄（「青」按字面只有 9 条）。
            # 注意别写成 `"0 条" not in stdout`——「10 条」里含「0 条」。
            n = re.match(r"(\d+) 条", r.stdout)
            check(bool(n) and int(n.group(1)) > 0,
                  f"文档里的 search 示例不该返回空：{' '.join(argv)} -> {r.stdout[:20]}")
        if argv == ["motifs", "--scene", "水墨"]:
            check("适配 水墨" in r.stdout, "motifs --scene 应声明适配场景")
            check("能用但不是" not in r.stdout.split("适配 水墨")[0],
                  "适配列表里不该混入跨场景借用")
        if argv == ["motifs", "--scene", "年画"]:
            # 年画的适配纹样很少，表头必须按 fits_scenes 算，不能把 12 条都写成适配
            m = re.search(r"(\d+) 个纹样（适配 年画）", r.stdout)
            check(bool(m) and int(m.group(1)) <= 4,
                  f"年画适配数应按 fits_scenes 算（≤4），实得 {m.group(0) if m else r.stdout[:80]}")
    # --pin 写错格式要给可读的报错而不是 traceback
    r = subprocess.run([sys.executable, script, "generate", "--pin", "枫叶红"],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
    check(r.returncode != 0 and "Traceback" not in r.stderr,
          "--pin 格式错应给可读报错，不是 traceback")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)


def test_plain_output() -> None:
    """给用户看的输出里不许出现内部术语。靠机制而不是靠自觉。

    只有 ask 与 tweak 的输出是「照着念」的白话。其余子命令的输出是给模型看的
    参考件，里面本来就有行话（五行、彩度、ΔE、LCH、token…）——那是引擎对模型
    说的话。这个区分原先只存在于「selftest 只查了 ask」这个事实里，
    SKILL.md 一个字没写，于是模型照念 info 石青 就会漏出五行与 LCH。
    现在两头都钉住：文档写明，测试守住边界。
    """
    import subprocess
    from vernacular import Vernacular
    v = Vernacular()
    script = ROOT / "scripts" / "palette.py"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", NO_COLOR="1")

    # 照念档：必须干净
    VERBATIM = [
        ["ask", "茶叶小店的网站，安静一点", "--no-bar"],
        ["ask", "做个后台仪表盘，深色模式", "--no-bar"],
        ["ask", "过年活动页，要喜庆", "--no-bar"],
        ["ask", "茶室的网站，加一枝梅花点缀", "--no-bar", "--n", "1"],
        ["ask", "岁末的活动页，加点荷花", "--no-bar", "--n", "1"],
        ["ask", "用荷花白做底色的网站", "--no-bar", "--n", "1"],
        ["tweak", "太素了，再艳一点", "--mood", "雅", "--no-bar", "--n", "1"],
        ["tweak", "红少一点", "--mood", "艳", "--no-bar", "--n", "1"],
    ]
    for argv in VERBATIM:
        r = subprocess.run([sys.executable, str(script)] + argv, capture_output=True,
                           text=True, encoding="utf-8", env=env, cwd=str(ROOT))
        label = f"{argv[0]}「{argv[1]}」"
        check(r.returncode == 0, f"{label} 应正常退出，实得 {r.returncode}")
        leaked = v.check_plain(r.stdout)
        check(not leaked, f"{label} 输出泄露术语 {leaked}")

    # 参考件档：SKILL.md 必须说明它们要翻，不能照念。
    # 不断言它们干净——那些行话是引擎对模型说的话，本来就该在。
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    check("哪些输出能照念" in skill, "SKILL.md 必须说明哪些输出能照念、哪些要翻")
    for cmd in ("info", "snap", "complete", "motifs", "search", "pick", "generate", "resolve"):
        check(cmd in skill, f"SKILL.md 的输出定位表里应有 {cmd}")
    # 反面守住：真有一天 ask 被改成输出行话，上面那组会红；
    # 而参考件档若被误当成白话，这条会提醒边界在哪。
    r = subprocess.run([sys.executable, str(script), "info", "石青"], capture_output=True,
                       text=True, encoding="utf-8", env=env, cwd=str(ROOT))
    check(bool(v.check_plain(r.stdout)),
          "info 的输出本就含行话（它是参考件）。若这条变绿，说明它已被改成白话档，"
          "那 SKILL.md 的输出定位表也要跟着改")


def test_render() -> None:
    """色条必须在 Claude Code 的默认环境里真的出现。

    原来 color_mode() 把「不要发 ANSI」和「不要表达面积」绑在一个开关上：
    宿主实测 NO_COLOR=1 且 stdout 是管道，于是那一档只打三行「底 #hex 约 N%」，
    与落位那三行重复，用户从来没看见过色条——「三色不等权」全靠文字解释。
    工具输出进的是模型上下文而不是用户终端，所以管道里的修法是 Unicode 方块，
    不是强发转义。
    """
    import contextlib
    import itertools
    import types
    import render as rd
    from vernacular import Vernacular

    class _FakeStdout:
        def __init__(self, tty: bool, encoding: str | None = "utf-8") -> None:
            self._tty, self.encoding = tty, encoding

        def isatty(self) -> bool:
            return self._tty

    @contextlib.contextmanager
    def fake_env(env: dict, tty: bool = False, osname: str = "posix",
                 encoding: str | None = "utf-8"):
        """替掉 render 模块里的 os/sys，才能在一台机器上跑完整张判定表。"""
        old_os, old_sys = rd.os, rd.sys
        rd.os = types.SimpleNamespace(environ=env, name=osname)
        rd.sys = types.SimpleNamespace(stdout=_FakeStdout(tty, encoding))
        if hasattr(rd._win_vt_ok, "cache_clear"):
            rd._win_vt_ok.cache_clear()  # 缓存过的探测结果会串到下一行判定表
        try:
            yield
        finally:
            rd.os, rd.sys = old_os, old_sys
            if hasattr(rd._win_vt_ok, "cache_clear"):
                rd._win_vt_ok.cache_clear()

    ENTRIES = [("底", "#f7f4ed", 78), ("块", "#495c69", 19), ("点", "#f43e06", 3)]

    # ---- 真彩档：转义要在，宽度要按真实面积
    tc = rd.area_bar(ENTRIES, mode="truecolor")
    bar, legend = tc.split("\n")
    check("\033[48;2;" in bar, "真彩色条应发 48;2 背景转义")
    widths = [len(m) for m in re.findall(r"(?:\033\[48;2;\d+;\d+;\d+m)( +)", bar)]
    check(widths == [42, 10, 2], f"78/19/3 @54 应落成 42/10/2，实得 {widths}")
    check("\033[38;2;" not in legend and "■" not in legend,
          "legend 不许再用前景 ■：浅底在浅色主题上只有 1.01:1，等于隐形")
    check(legend.count("\033[48;2;") == 3, "legend 三个方块都要用背景铺")
    check("%" not in legend and "#" not in legend,
          "legend 不带 hex 与百分比：数字真源是 palette.py 的落位三行")
    for label in ("底", "块", "点"):
        check(label in legend, f"legend 必须保留「{label}」标签，否则成了无标注色带")

    # ---- 方块档：没有转义，但面积照样看得见
    blk = rd.area_bar(ENTRIES, mode="block")
    bar, legend = blk.split("\n")
    check("\033" not in blk, "方块档不许冒任何转义——它进的是模型上下文")
    runs = [(ch, len(list(g))) for ch, g in itertools.groupby(bar)]
    check([n for _, n in runs] == [42, 10, 2],
          f"方块档宽度也要按真实面积，实得 {runs}")
    check(len({ch for ch, _ in runs}) == 3, f"相邻块要用三级密度区分，实得 {runs}")
    check(len(bar) == 54, f"方块条总宽应是 54，实得 {len(bar)}")
    check("▌" not in blk and "│" not in blk,
          "块间不许加分隔符：它吃掉 1 格宽度，点缀只有 2 格时比例直接崩")
    # 判 hex 要用模式而不是裸 "#"：遗留代码页下方块自己就退成了 "#"（_BLOCKS_ASCII），
    # 拿裸字符判会让兜底一生效就自己报错——不设 PYTHONUTF8 时 stdout 是 gbk，这条真的红。
    check(not re.search(r"#[0-9a-fA-F]{6}", blk) and "%" not in blk and "约" not in blk,
          "方块档不许再打「底 #hex 约 N%」——那与落位三行重复")
    for label in ("底", "块", "点"):
        check(label in legend, f"方块档 legend 必须保留「{label}」标签")
    check(rd.area_bar(ENTRIES, mode="none").split("\n")[0] == bar,
          "none 传进 area_bar 也要画方块，不能画出一条空白")
    v = Vernacular()
    check(not v.check_plain(blk), f"方块与角色标签不许算术语泄漏：{v.check_plain(blk)}")

    # ---- bar_mode 永不「什么都不画」
    for env, tty, osname in (({"NO_COLOR": "1"}, False, "posix"),
                             ({}, False, "posix"),
                             ({"TERM": "dumb"}, True, "posix"),
                             ({"NO_COLOR": "1", "FORCE_COLOR": "1"}, True, "posix")):
        with fake_env(env, tty, osname):
            check(rd.bar_mode() in ("truecolor", "256", "block"),
                  f"bar_mode 在 {env} tty={tty} 下不许返回 none")
            check(rd.color_mode() != "none" or rd.bar_mode() == "block",
                  f"不发转义时必须退到方块，实得 {rd.bar_mode()}")

    test_render_color_mode(rd, fake_env)


def test_render_color_mode(rd, fake_env) -> None:
    """color_mode() 的整张判定表。每一行都对应一个真实踩过的坑。"""
    CASES = [
        # (env, tty, os.name, 期望, 为什么)
        ({"NO_COLOR": "1"}, True, "posix", "none", "NO_COLOR 第一优先"),
        ({"NO_COLOR": "1", "FORCE_COLOR": "1"}, True, "posix", "none",
         "NO_COLOR 压得住 FORCE_COLOR"),
        ({"FORCE_COLOR": "1"}, False, "posix", "truecolor", "FORCE_COLOR 管道下也强开"),
        ({"FORCE_COLOR": "0"}, False, "posix", "none",
         "FORCE_COLOR=0 只是不强制，不该当成开"),
        ({"FORCE_COLOR": "0", "TERM": "xterm-256color"}, True, "posix", "256",
         "FORCE_COLOR=0 应落回正常判定而不是强开真彩"),
        ({"FORCE_COLOR": ""}, True, "posix", "none", "空 FORCE_COLOR 不算设过"),
        ({"TERM": "xterm-256color"}, False, "posix", "none", "管道不发转义"),
        ({"TERM": "dumb"}, True, "posix", "none", "dumb 仍是 none"),
        ({"TERM": ""}, True, "posix", "none", "非 Windows 的空 TERM 是 none"),
        ({"TERM": "xterm-256color"}, True, "posix", "256", "256 档"),
        ({"TERM": "xterm-256color-direct"}, True, "posix", "truecolor",
         "direct 必须排在「含 256 则回 256」之前，否则被误降"),
        ({"TERM": "xterm-24bit"}, True, "posix", "truecolor", "TERM 含 24bit 是真彩"),
        ({"TERM": "xterm-256color", "COLORTERM": "truecolor"}, True, "posix", "truecolor",
         "COLORTERM=truecolor 优先于 TERM 的 256"),
        ({"TERM": "xterm-256color", "COLORTERM": "24bit"}, True, "posix", "truecolor",
         "COLORTERM=24bit 也是真彩"),
        ({"TERM": "xterm"}, True, "posix", "truecolor", "普通 xterm 给真彩"),
        ({"TERM": "", "WT_SESSION": "x"}, True, "nt", "truecolor",
         "Windows Terminal 的 TERM 是空的，不该因此掉到 none"),
        ({"WT_SESSION": "x"}, True, "nt", "truecolor", "Windows 根本没有 TERM 也一样"),
        ({"ConEmuANSI": "ON"}, True, "nt", "truecolor", "ConEmu 认真彩"),
        ({"TERM_PROGRAM": "vscode"}, True, "nt", "truecolor", "VSCode 终端认真彩"),
        ({"ANSICON": "1"}, True, "nt", "256", "ANSICON 只做 16 色仿真，别抬成真彩"),
        ({"TERM": "dumb", "WT_SESSION": "x"}, True, "nt", "none", "Windows 上 dumb 也是 none"),
        ({}, False, "nt", "none", "Windows 管道下不碰控制台，一律 none"),
    ]
    for env, tty, osname, want, why in CASES:
        with fake_env(env, tty, osname):
            got = rd.color_mode()
        check(got == want, f"color_mode {env} tty={tty} os={osname} 应 {want}，实得 {got}（{why}）")

    # Windows 真 TTY 且什么标记都没有：走 _win_vt_ok()。管道下它必须不探控制台。
    with fake_env({}, False, "nt"):
        check(rd._win_vt_ok() is False, "管道下 _win_vt_ok 应直接 False，不碰 SetConsoleMode")
    check(hasattr(rd._win_vt_ok, "cache_clear"),
          "_win_vt_ok 必须带 lru_cache：SetConsoleMode 有副作用，不能每次 bg() 都探")
    # Windows 真 TTY、什么标记都没有：TERM 空不能直接 none，要问 _win_vt_ok。
    # 替换函数本身，避免测试去动真控制台。
    saved_vt = rd._win_vt_ok
    try:
        rd._win_vt_ok = lambda: True  # noqa: E731
        with fake_env({}, True, "nt"):
            check(rd.color_mode() == "truecolor",
                  "Windows 空 TERM + VT 可用 → truecolor，不能因 TERM 空掉到 none")
        rd._win_vt_ok = lambda: False  # noqa: E731
        with fake_env({}, True, "nt"):
            check(rd.color_mode() == "none",
                  "Windows 空 TERM + VT 不可用 → none")
    finally:
        rd._win_vt_ok = saved_vt
        rd._win_vt_ok.cache_clear()

    # ---- 256 量化：预建 240 格按 ΔE2000 最近邻，不是 round(x/255*5) 反推
    check(len(rd._XTERM_256) == 240, f"应预建 240 格，实得 {len(rd._XTERM_256)}")
    check(rd._rgb_to_256(255, 0, 0) == 196, f"纯红应是 196，实得 {rd._rgb_to_256(255, 0, 0)}")
    check(rd._rgb_to_256(0, 0, 0) == 16, f"纯黑应是 16，实得 {rd._rgb_to_256(0, 0, 0)}")
    check(rd._rgb_to_256(255, 255, 255) == 231,
          f"纯白应是 231，实得 {rd._rgb_to_256(255, 255, 255)}")
    # 128 不在立方级阶 [0,95,135,175,215,255] 上：老式 round(128/255*5)=3 会推成 135 的格子，
    # 而灰阶里 128 只差 2。这条是「反推」与「最近邻」的分水岭。
    check(rd._rgb_to_256(128, 128, 128) == 244,
          f"中灰应落灰阶 244，实得 {rd._rgb_to_256(128, 128, 128)}")
    check(rd._rgb_to_256(0, 95, 135) == 24, f"立方角点应精确命中 24，实得 {rd._rgb_to_256(0, 95, 135)}")
    for hexv in ("#f7f4ed", "#495c69", "#f43e06", "#a61b29", "#fcc307"):
        rgb = ck.hex_to_rgb(hexv)
        lab = ck.rgb_to_lab(rgb)
        best = min(rd._XTERM_256, key=lambda cell: ck.delta_e_2000(lab, cell[1]))[0]
        check(rd._rgb_to_256(*rgb) == best,
              f"{hexv} 应取 ΔE2000 最近的 {best}，实得 {rd._rgb_to_256(*rgb)}")
    check(hasattr(rd._rgb_to_256, "cache_info"), "_rgb_to_256 要缓存，否则每格都重算 240 次 ΔE")

    # ---- 遗留代码页兜底：cp936 编不出 █，写出前必须退到 ASCII
    import types
    old_sys = rd.sys
    try:
        for enc, want_first in (("utf-8", "█"), (None, "█"), ("cp936", "#"), ("ascii", "#")):
            rd.sys = types.SimpleNamespace(
                stdout=type("S", (), {"encoding": enc, "isatty": lambda self: False})())
            check(rd._blocks()[0] == want_first,
                  f"stdout.encoding={enc} 时首格应是 {want_first}，实得 {rd._blocks()[0]}")
            check(len(set(rd._blocks())) == 3, f"encoding={enc} 的兜底也要三级密度")
    finally:
        rd.sys = old_sys

    # ---- swatch/ladder 已删：全库只有 render 自己的 __main__ 在用
    check(not hasattr(rd, "swatch") and not hasattr(rd, "ladder"),
          "swatch/ladder 是死代码，应已删除")
    check(rd.bg("#f7f4ed", "none") == "" and rd.fg("#f7f4ed", "none") == "",
          "none 档的 bg/fg 仍应返回空串")

    test_render_pipe()


def test_render_pipe() -> None:
    """真跑一次宿主的默认环境：NO_COLOR=1 且 stdout 是管道。"""
    import subprocess
    import itertools
    script = str(ROOT / "scripts" / "palette.py")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", NO_COLOR="1")
    r = subprocess.run([sys.executable, script, "ask", "茶叶小店的网站，安静一点", "--n", "1"],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
    check(r.returncode == 0, f"NO_COLOR 管道下 ask 应正常退出，实得 {r.returncode}")
    check("\033" not in r.stdout, "管道输出不许含 ESC 转义——它会变成上下文里的垃圾")
    check("█" in r.stdout, "NO_COLOR + 管道下必须仍画出方块条（宿主的默认路径）")
    bar = next((ln for ln in r.stdout.splitlines() if ln.startswith("█")), "")
    runs = [len(list(g)) for _, g in itertools.groupby(bar)]
    check(len(runs) == 3 and runs[0] > runs[1] > runs[2],
          f"三段宽度必须底>块>点，实得 {runs}")
    check(sum(runs) == 54, f"方块条总宽应 54，实得 {sum(runs)}")
    check(r.stdout.count("约 ") == 3,
          f"「约 N%」只该出现在落位三行，实得 {r.stdout.count('约 ')} 次")
    from vernacular import Vernacular
    leaked = Vernacular().check_plain(r.stdout)
    check(not leaked, f"带方块条的 ask 输出仍不许泄露术语，实得 {leaked}")


def test_dark_ground() -> None:
    """暗色的场必须是安静的深色，不能塌成紫黑。"""
    from engine import DARK_GROUND_MAX_C, DARK_GROUND_MAX_L
    cat = Catalog()
    for mood in ("雅", "清冷", "空灵", "浓烈", "古朴"):
        pals = generate(cat, mood=mood, dark=True, n=1)
        check(bool(pals), f"暗色 {mood} 应有方案")
        if not pals:
            continue
        d = pals[0].dominant
        check(d.L <= DARK_GROUND_MAX_L, f"暗色 {mood} 的场 {d.name} L*{d.L:.0f} 应 ≤{DARK_GROUND_MAX_L}")
        check(d.C <= DARK_GROUND_MAX_C, f"暗色 {mood} 的场 {d.name} C{d.C:.0f} 应 ≤{DARK_GROUND_MAX_C}")
        check(d.family != "紫", f"暗色 {mood} 的场不该是紫（实得 {d.name}）")


def test_token_family() -> None:
    """派生 token 漏出场景色族要被抓住——青花配出紫描边是荆浩点名的死局。

    但可读性优先于色族纯度：场景语汇内找不到能保住对比义务的替代色时，
    保留原色并如实上报才是对的。所以断言分两条：
    (1) 对比义务在修补后必须全部成立；
    (2) 仍然出族的 token 必须带 kept 标记出现在问题列表里，不许静默。
    """
    from engine import TOKEN_OBLIGATIONS, apply_family_lock, contrast, family_lock
    cat = Catalog()
    for scene in ("青花", "水墨", "宋瓷", "补服", "故宫"):
        for dark in (False, True):
            pals = generate(cat, scene=scene, media="ui", dark=dark, n=1)
            if not pals:
                continue
            tok = tokens(cat, pals[0])
            fixed, remain = apply_family_lock(cat, tok, scene)
            # 对比义务不许被换色破坏。
            # 判据是「库内换得出来吗」而不是死数字 4.5：有 16 个色库内根本不存在
            # 4.5 的搭配，把它们硬断言成 4.5 只会把这条测试打挂，而那不是修好，
            # 是逼着代码去藏缺陷。库内换不出来时，仍要求交出库内最好的那一个。
            for key, (partner, need) in TOKEN_OBLIGATIONS.items():
                got = contrast(fixed[key], fixed[partner])
                base = fixed[partner]
                best = max(contrast(x, base) for x in cat.colors if x.name != base.name)
                if best >= need:
                    check(got >= need,
                          f"{scene} dark={dark} 换色后 {key}({fixed[key].name}) 对 "
                          f"{partner} 只有 {got:.2f}:1，应 ≥{need}（库内最高 {best:.2f}:1）")
                else:
                    check(abs(got - best) < 0.01,
                          f"{scene} dark={dark} 的 {partner}({base.name}) 是死区色"
                          f"（库内最高 {best:.2f}:1 < {need}），{key} 应交出库内最好的那个，"
                          f"实测 {got:.2f}:1")
            # 换不动的必须显式上报，且理由是对比义务
            leftover = family_lock(cat, fixed, scene)
            reported = {i["token"] for i in remain}
            for issue in leftover:
                check(issue["token"] in reported,
                      f"{scene} dark={dark} 的 {issue['token']} 仍出族却没上报")
                check(issue.get("kept") is True,
                      f"{scene} dark={dark} 的 {issue['token']} 出族但没标明是为保住对比而保留")


def test_seed_errors() -> None:
    """种子解析失败必须报错。静默回落是错得没有症状的那种错。"""
    from engine import SeedNotFound
    cat = Catalog()
    try:
        generate(cat, seed="米黄色", n=1)
        check(False, "库外色名应抛 SeedNotFound")
    except SeedNotFound as exc:
        check(bool(exc.suggestions), "报错要带最近邻建议")
    pals = generate(cat, seed="#c1272d", n=1)
    check(bool(pals), "hex 种子应能吸附并生成")
    pals = generate(cat, pin={"accent": "枫叶红"}, media="ui", n=1)
    check(bool(pals) and pals[0].accent.name == "枫叶红", "pin 的点缀必须真的出现")


def test_handoff() -> None:
    """交接文件的必备字段。下游只读文件，字段缺了它就自己发明 hex。"""
    import handoff as ho
    from engine import score_trio
    cat = Catalog()
    pals = generate(cat, scene="水墨", media="ui", n=1)
    check(bool(pals), "水墨应有方案")
    if not pals:
        return
    dark = generate(cat, scene="漆器", media="ui", dark=True, n=1)
    data = ho.build(cat, pals[0], dark_pal=dark[0] if dark else None, chosen_from="test")
    for seg in ("meta", "roles", "named6", "tokens_light", "css", "verify",
                "chart", "cliche", "bans", "issues", "read_map", "scope"):
        check(seg in data, f"handoff 缺段 {seg}")
    check(len(data["named6"]) == 6, f"named6 必须占满六槽，实际 {len(data['named6'])}")
    # 交付的 token 与闸门必须一一对上。CONTRAST_GATES 里每一项验的都得是
    # tokens_light 里真有的两个键——闸门验一个不交付的色，是这一族缺陷的根。
    for key in ho.CONTRAST_GATES:
        check(key in data["verify"], f"verify 缺闸门 {key}")
        fg, _, bgk = key.partition("_on_")
        for side in (fg, bgk):
            check(side in data["tokens_light"],
                  f"闸门 {key} 验的 {side} 不在交付的 token 里——闸门必须验交付物")
    for k in ("secondary_fg_on_secondary", "success_fg_on_success", "warning_fg_on_warning",
              "error_fg_on_error", "info_fg_on_info"):
        check(k in ho.CONTRAST_GATES, f"块上/徽章上的字必须有闸门：缺 {k}")
    # 达不到 4.5 的必须落进 issues，并说明是「库内换不出」还是「挑错了」
    for f in data["verify"]["fail"]:
        check(any(i["token"] == f["check"] for i in data["issues"]),
              f"闸门 {f['check']} 没达标却没进 issues——不许静默交付")
        if f.get("library_best") is not None:
            check("只放大字" in f["handle"],
                  f"{f['check']} 是库内换不出的死区，handle 必须明说只放大字")
    for slot, v in data["named6"].items():
        check(v["hex"] in cat.by_hex, f"named6 的 {slot} {v['hex']} 必须在库内")
    check(bool(data["bans"]), "bans 不能为空")
    # 亮暗两块不能都用 :root，直接拼会互相覆盖
    if "dark" in data["css"]:
        check(data["css"]["light"].startswith(":root"), "亮色块应挂 :root")
        check('[data-theme="dark"]' in data["css"]["dark"], "暗色块应挂 data-theme")
        check(set(data["tokens_light"]) == set(data["tokens_dark"]),
              "亮暗两套 token 键必须完全一致")
    # 图表段：分类色上限是色盲安全线定的，不是审美偏好
    cats = data["chart"]["categorical"]
    check(cats["max_safe_n"] <= 5, f"分类色上限 5，实际 {cats['max_safe_n']}")
    seq = data["chart"]["sequential"]
    if seq:
        ls = [s["L"] for s in seq]
        check(ls == sorted(ls), f"序列色明度必须单调，实得 {ls}")


def test_doc_numbers() -> None:
    """文档里的数量声明必须与真实数据一致。

    这一组是所有数字漂移的根因防线。之前 README 写「711 项断言」，改成
    「1085 项」，而真实值已经是 1225——没有断言盯着，这个数每加一批测试
    就错一次，而它出现在 README、INSTALL 和目录树四处。

    数字本身不重要，重要的是它出现在「这个项目有多少回归保护」这句话里。
    写错了会让读者以为覆盖面比实际小，或者以为大。
    """
    import io
    docs = {p.name: p.read_text(encoding="utf-8")
            for p in [ROOT / "README.md", ROOT / "INSTALL.md", ROOT / "SKILL.md"]
            if p.exists()}
    refs = ROOT / "references"

    def jload(name):
        return json.loads((refs / name).read_text(encoding="utf-8"))

    colors = jload("colors.json")
    colors = colors if isinstance(colors, list) else colors.get("colors", [])
    aliases = jload("aliases.json")
    motifs = jload("motifs.json")
    vern = jload("vernacular.json")

    def count_strings(x) -> int:
        if isinstance(x, list):
            return sum(1 if isinstance(i, str) else count_strings(i) for i in x)
        if isinstance(x, dict):
            return sum(count_strings(v) for v in x.values())
        return 0

    n_cases = sum(1 for line in io.open(refs / "vernacular_cases.jsonl", encoding="utf-8")
                  if line.strip())
    from engine import MEDIA, MOODS, SCENES
    role_counts: dict = {}
    for c in colors:
        for r in (c.get("roles") or c.get("design_roles") or []):
            role_counts[r] = role_counts.get(r, 0) + 1
    truth = {
        "色库条数": len(colors),
        "别名条数": len(aliases["aliases"]),
        "白话用例": n_cases,
        "纹样条数": len(motifs["motifs"]),
        "线索词条数": count_strings(vern["in"]),
        "场景数": len(SCENES),
        "氛围数": len(MOODS),
        "媒材数": len(MEDIA),
        "token 数": len(TOKEN_KEYS),
        "浅底池": role_counts.get("浅底", 0),
        "墨色池": role_counts.get("墨色", 0),
        "RGB 不一致": sum(1 for c in colors if "rgb_source" in c),
    }
    # 每个真实值都要能在文档里找到它的声明，且声明的数与真实值相等。
    # 正则要覆盖同一个数的**所有**写法——漏一种，那一处就会静默漂移。
    PATTERNS = {
        "色库条数": r"(\d+) ?(?:个中国传统色|条，每条含|色 \+|个具名色|个色平铺|条）|条` —— `co)",
        "别名条数": r"(\d+) 条(?:经典色名|别名做文化校正)",
        "白话用例": r"(\d+) 条(?:映射回归用例|回归用例|用例由)",
        "纹样条数": r"(?:全部 )?(\d+) 个纹样|全部 (\d+) 个",
        "线索词条数": r"(\d+) 条(?:线索词|白话线索词)",
        "场景数": r"(\d+) 个场景|这 (\d+) 个之一",
        "氛围数": r"(\d+) 种氛围",
        "媒材数": r"(\d+) 种媒材",
        "token 数": r"(\d+) 个可直接落地的 token",
        "浅底池": r"能当纸地的有哪 (\d+) 个",
        "墨色池": r"能当正文墨色的有哪 (\d+) 个",
        "RGB 不一致": r"(\d+) 条记录的 RGB",
    }
    for label, pat in PATTERNS.items():
        real = truth[label]
        found = []
        for fname, text in docs.items():
            for m in re.finditer(pat, text):
                # 有多分支的模式，取命中的那一组
                num = next((g for g in m.groups() if g), None)
                if num is not None:
                    found.append((fname, int(num)))
        check(bool(found), f"文档里应有「{label}」的声明（模式 {pat}）")
        wrong = [(f, n) for f, n in found if n != real]
        check(not wrong, f"{label} 真实是 {real}，文档写成 {wrong}")

    # 铁律条数：rules.md 的 ## N 小节数，与 README / SKILL 的声明比对
    rules = (refs / "rules.md").read_text(encoding="utf-8")
    n_rules = len(re.findall(r"^## \d+\.", rules, re.M))
    check(n_rules >= 14, f"铁律至少 14 条，实际 {n_rules}")
    for fname, text in docs.items():
        for m in re.finditer(r"(\d+) 条(?:铁律|与常见失败)", text):
            check(int(m.group(1)) == n_rules,
                  f"{fname} 写「{m.group(1)} 条铁律」，rules.md 实际 {n_rules} 条")

    # 别名解析必须真能走通：文档举的例子不许是死的
    cat = Catalog()
    for alias, want in [("石青", "群青"), ("玄色", "可可棕"), ("胭脂", "苋菜红")]:
        got = cat.aliases.get(alias)
        check(got is not None, f"文档举的别名「{alias}」应能解析")
        if got is not None:
            name = got.name if hasattr(got, "name") else got
            check(want in str(name), f"别名「{alias}」应解析到 {want}，实得 {name}")


def check_doc_assertion_count(real: int) -> None:
    """文档声明的断言总数必须等于实际跑出来的条数。

    放在所有测试之后，因为总数在最后一条断言跑完才定型。它自己不调用
    check()——那会改变它正在校验的那个数。

    这个数漂过两次（711 -> 1085，而真实已是 1225）。改成精确比对之后，
    加测试就必须同步改文档：一行的摩擦，换掉一个会静默骗人的数字。

    real 由调用方在调用前快照。不在函数内部现算：本函数自己会往 FAILS 里
    追加条目，现算会让「比对用的数」与「末行打印的数」差出自己的失败数。
    """
    for path in (ROOT / "README.md", ROOT / "INSTALL.md"):
        if not path.exists():
            continue
        for m in re.finditer(r"(\d{3,}) 项(?:回归|断言)", path.read_text(encoding="utf-8")):
            claimed = int(m.group(1))
            if claimed != real:
                FAILS.append(f"{path.name} 写的断言数 {claimed} 与实际 {real} 不符"
                             f"——把文档里这个数改成 {real}")
                print("FAIL", FAILS[-1])
            else:
                print(" ok ", f"{path.name} 断言数声明 {claimed} 与实际一致")


def main() -> int:
    test_colorkit()
    test_catalog()
    test_aliases()
    test_curated()
    test_chroma_ground()
    test_generate()
    test_tokens()
    test_ui_components()
    test_vernacular()
    test_tweak_moods()
    test_unheard()
    test_airy_areas()
    test_gold_names()
    test_dark_ground()
    test_token_family()
    test_seed_errors()
    test_handoff()
    test_motifs()
    test_ornament_handoff()
    test_documented_commands()
    test_plain_output()
    test_render()
    test_doc_numbers()
    total = PASSES + len(FAILS)  # 必须在文档校验之前快照：那一步自己会追加失败
    check_doc_assertion_count(total)
    print()
    print(f"共 {total} 项断言")
    if FAILS:
        print(f"{len(FAILS)} 项失败")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
