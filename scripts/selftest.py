#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：色彩数学、色库完整性、别名、手选方案、生成器铁律。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import os  # noqa: E402
import shutil  # noqa: E402

import colorkit as ck  # noqa: E402
from engine import Catalog, generate, score_trio, tokens  # noqa: E402

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
    check(len(cases) >= 60, f"白话用例 ≥60 条，实际 {len(cases)}")
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
    check(bad == 0, f"白话映射全部命中（{len(cases)} 条用例，{bad} 条不符）")

    # 每个进表的线索词都要有用例覆盖，否则表会长成没人验证过的样子
    covered = " ".join(c["say"] for c in cases)
    axes = {a: 0 for a in ("media", "mood", "scene")}
    for axis, value, word, _w in v.cues:
        if axis in axes and word in covered:
            axes[axis] += 1
    for axis, hit in axes.items():
        check(hit >= 8, f"{axis} 轴至少 8 个线索词被用例覆盖，实际 {hit}")


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
        ["search", "--family", "青", "--role", "浅底"],
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
    ]
    for argv in cases:
        r = subprocess.run([sys.executable, script] + argv, capture_output=True,
                           text=True, encoding="utf-8", env=env, cwd=str(ROOT))
        check(r.returncode == 0,
              f"README 命令应可跑: palette.py {' '.join(argv[:3])} … "
              f"（退出码 {r.returncode}）")
    # --pin 写错格式要给可读的报错而不是 traceback
    r = subprocess.run([sys.executable, script, "generate", "--pin", "枫叶红"],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
    check(r.returncode != 0 and "Traceback" not in r.stderr,
          "--pin 格式错应给可读报错，不是 traceback")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)


def test_plain_output() -> None:
    """给用户看的输出里不许出现内部术语。靠机制而不是靠自觉。"""
    import subprocess
    from vernacular import Vernacular
    v = Vernacular()
    script = ROOT / "scripts" / "palette.py"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", NO_COLOR="1")
    for say in ("茶叶小店的网站，安静一点", "做个后台仪表盘，深色模式", "过年活动页，要喜庆"):
        r = subprocess.run([sys.executable, str(script), "ask", say, "--no-bar"],
                           capture_output=True, text=True, encoding="utf-8", env=env,
                           cwd=str(ROOT))
        check(r.returncode == 0, f"ask「{say}」应正常退出，实得 {r.returncode}")
        leaked = v.check_plain(r.stdout)
        check(not leaked, f"ask「{say}」输出泄露术语 {leaked}")


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
            # 对比义务不许被换色破坏
            for key, (partner, need) in TOKEN_OBLIGATIONS.items():
                got = contrast(fixed[key], fixed[partner])
                check(got >= need,
                      f"{scene} dark={dark} 换色后 {key}({fixed[key].name}) 对 "
                      f"{partner} 只有 {got:.2f}:1，应 ≥{need}")
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


def main() -> int:
    test_colorkit()
    test_catalog()
    test_aliases()
    test_curated()
    test_generate()
    test_tokens()
    test_vernacular()
    test_unheard()
    test_airy_areas()
    test_gold_names()
    test_dark_ground()
    test_token_family()
    test_seed_errors()
    test_handoff()
    test_documented_commands()
    test_plain_output()
    print()
    if FAILS:
        print(f"{len(FAILS)} 项失败")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
