#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中国传统色配色 CLI。

用法示例：
    python palette.py search 月白
    python palette.py search --family 青 --role 浅底
    python palette.py generate --mood 雅 --n 5
    python palette.py generate --scene 故宫
    python palette.py generate --seed 朱红 --mood 艳
    python palette.py complete 月白 群青
    python palette.py info 石青          # 别名会解析到群青
    python palette.py preview --scene 青花 --out ../assets/preview.html
"""

from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render as rd  # noqa: E402
from engine import (  # noqa: E402
    MEDIA, MOODS, SCENES, Catalog, Color, Palette, SeedNotFound,
    as_dict, cliche_check, complete_pair, contrast, css_vars, family_lock, generate,
    tokens, tailwind_extend, visual_areas,
)
from vernacular import Vernacular  # noqa: E402


def _print_color(c: Color, indent: str = "") -> None:
    roles = ",".join(c.roles[:4])
    print(f"{indent}{c.name:8s} {c.hex}  RGB{tuple(c.rgb)}  "
          f"L*{c.L:.0f} C{c.C:.0f} H{c.H:.0f}  "
          f"{c.family}/{c.wuxing}/{c.season}/{c.temperature}  {roles}")


def _print_palette(p: Palette, cat: Catalog, show_tokens: bool = True) -> None:
    flags = []
    if p.dark:
        flags.append("暗色")
    if p.media:
        flags.append(f"媒材={p.media}")
    suffix = ("  " + "  ".join(flags)) if flags else ""
    print(f"\n评分 {p.score['total']:.1f}  氛围={p.mood or '—'}  场景={p.scene or '—'}{suffix}")
    print(f"  主场  {p.dominant.name:8s} {p.dominant.hex}  {p.dominant.family} {p.dominant.chroma_band}")
    print(f"  结构  {p.secondary.name:8s} {p.secondary.hex}  {p.secondary.family} {p.secondary.chroma_band}")
    print(f"  点缀  {p.accent.name:8s} {p.accent.hex}  {p.accent.family} {p.accent.chroma_band}")
    for line in p.rationale:
        print(f"    · {line}")
    areas = visual_areas(p)["pixel_pct"]
    print(f"  建议铺色面积  主场 {areas['dominant']}  结构 {areas['secondary']}  点缀 {areas['accent']}  （高彩点缀宜更小）")
    if show_tokens:
        tok = tokens(cat, p)
        print("  tokens:")
        for k in ("bg", "surface", "text", "muted", "border", "border_strong",
                  "secondary", "secondary_fg", "accent", "accent_fg",
                  "accent_hover", "accent_active",
                  "success", "success_fg", "warning", "warning_fg",
                  "error", "error_fg", "info", "info_fg", "disabled", "ring"):
            c = tok[k]
            print(f"    {k:14s} {c.name:8s} {c.hex}")


ROLE_FALLBACK = ("大面积铺的底", "成块的那层", "最小面积、最响的一点")


def _role_labels(media: str | None) -> tuple[str, str, str]:
    """角色的白话说法。仓库里已有四套落位词，不新造。"""
    cfg = MEDIA.get(media or "", {})
    labels = cfg.get("labels")
    return tuple(labels) if labels else ROLE_FALLBACK  # type: ignore[return-value]


def _print_plain(p: Palette, cat: Catalog, vern: Vernacular, bar: bool = True,
                 label: str | None = None) -> None:
    """给用户念的白话输出。

    不说场景名、氛围名、主场/结构/点缀、五行、荆浩、彩度带。只说：
    什么色、什么 hex、铺在哪、多大面积、字用什么、一条禁令。
    """
    areas = visual_areas(p)["pixel_pct"]
    l1, l2, l3 = _role_labels(p.media)
    head = label or "一套"
    print(f"\n{head}")
    if bar:
        print(rd.area_bar([("底", p.dominant.hex, areas["dominant"]),
                           ("块", p.secondary.hex, areas["secondary"]),
                           ("点", p.accent.hex, areas["accent"])]))
    print(f"  {l1:8s} {p.dominant.name:6s} {p.dominant.hex}   约 {areas['dominant']:.0f}%")
    print(f"  {l2:8s} {p.secondary.name:6s} {p.secondary.hex}   约 {areas['secondary']:.0f}%")
    print(f"  {l3:8s} {p.accent.name:6s} {p.accent.hex}   约 {areas['accent']:.0f}%")
    tok = tokens(cat, p)
    text = tok["text"]
    ratio = contrast(text, p.dominant)
    grade = "AAA" if ratio >= 7 else ("AA" if ratio >= 4.5 else "不够")
    print(f"  正文用    {text.name:6s} {text.hex}   对比 {ratio:.1f}:1 {grade}")
    if p.media == "ui":
        from handoff import _verify
        print(f"  卡片底    {tok['surface'].name:6s} {tok['surface'].hex}   普通内容卡片用这个色")
        for label, fg, bg_key in (("说明字", "muted", "surface"),
                                  ("彩块字", "secondary_fg", "secondary"),
                                  ("按钮字", "accent_fg", "accent")):
            c = tok[fg]
            print(f"  {label:6s}  {c.name:6s} {c.hex}   对比 {contrast(c, tok[bg_key]):.2f}:1")
        for issue in _verify(tok, cat)["fail"]:
            print(f"  提醒      {issue['label']}对比不足 {issue['need']}:1，不能按普通界面直接使用")
    # 出处与注意事项照带，但用白话版——术语版留给 --voice tech
    if p.origin_plain:
        print(f"  来处      {p.origin_plain}")
    if p.caution_plain:
        print(f"  当心      {p.caution_plain}")
    print(f"  别做      不要把 {p.accent.name} 铺成整条顶栏或大色带，它只有 {areas['accent']:.0f}% 的量")


def _plain_palette_dict(p: Palette, cat: Catalog) -> dict:
    areas = visual_areas(p)["pixel_pct"]
    l1, l2, l3 = _role_labels(p.media)
    text = tokens(cat, p)["text"]
    return {
        "id": f"{p.dominant.name}+{p.secondary.name}+{p.accent.name}",
        "slots": [
            {"where": l1, "name": p.dominant.name, "hex": p.dominant.hex, "area_pct": areas["dominant"]},
            {"where": l2, "name": p.secondary.name, "hex": p.secondary.hex, "area_pct": areas["secondary"]},
            {"where": l3, "name": p.accent.name, "hex": p.accent.hex, "area_pct": areas["accent"]},
        ],
        "text": {"name": text.name, "hex": text.hex,
                 "ratio": round(__import__("engine").contrast(text, p.dominant), 2)},
    }


def cmd_ask(cat: Catalog, args: argparse.Namespace) -> int:
    """白话主入口。用户原话进，能用的配色出，零提问。

    模型必须把用户原话一字不改地传进来。自己先翻译成 --scene/--mood 是这条路
    唯一会静默失效的地方：映射漂了，症状看起来像「颜色选得不好」，你会去调
    评分权重，而真正错的是意图识别。
    """
    vern = Vernacular()
    it = vern.resolve(args.text, catalog=cat)
    print(f"解读: {' · '.join(it.echo)}")
    if it.defaulted:
        print(f"      （{'、'.join(it.defaulted)} 没说，用了缺省）")
    if it.unheard:
        # 静默失败是最伤的一种：用户说了个接不住的词，却拿到一套看着合理的方案，
        # 他分不清是自己没说清还是技能没听懂。所以要说出来。
        print(f"没接住: {'、'.join(it.unheard)} —— 这几个词没对上任何取色规则，"
              f"下面这几套没把它算进去。要紧的话换个说法再讲一次。")

    # 信号厚就出同方向两套；信号薄就按轴铺开几个方向，避免两套撞脸
    directions: list[tuple[str, dict]] = []
    base = dict(media=it.media, dark=it.dark, seed=it.seed)
    if it.scene:
        directions.append((vern.out["scene"].get(it.scene, it.scene), dict(base, scene=it.scene)))
        for alt in it.alt_scenes:
            directions.append((vern.out["scene"].get(alt, alt), dict(base, scene=alt)))
    if it.mood and len(directions) < 2:
        directions.append((vern.out["mood"].get(it.mood, it.mood), dict(base, mood=it.mood)))
    if it.signal_axes <= 1 and not it.scene:
        for extra in ("空灵", "古朴"):
            if extra != it.mood and len(directions) < 3:
                directions.append((vern.out["mood"].get(extra, extra), dict(base, mood=extra)))

    # 方向数少于要给的套数时，从同一方向多取几套；方向够就每个方向各取一套，
    # 这样两套之间一定拉得开——generate --n 2 本身不保证方向有差异。
    per_direction = max(1, -(-args.n // max(1, len(directions))))
    shown = 0
    seen_trios: set[tuple[str, str, str]] = set()
    for name, kwargs in directions:
        if shown >= args.n:
            break
        try:
            pals = generate(cat, n=per_direction + 2, **kwargs)
        except SeedNotFound as exc:
            print(f"\n{exc}")
            print("  换一个色名或直接给 hex，我把它吸附到库内最近的具名色。")
            return 1
        taken = 0
        for p in pals:
            if shown >= args.n or taken >= per_direction:
                break
            key = (p.dominant.name, p.secondary.name, p.accent.name)
            if key in seen_trios:
                continue
            seen_trios.add(key)
            _print_plain(p, cat, vern, bar=not args.no_bar, label=f"方案 {shown + 1} · {name}")
            shown += 1
            taken += 1
    if shown == 0:
        print("没配出合格的方案。说得再具体一点，或者给我一个你想要的色名。")
        return 1

    if it.motifs or it.motif_notes:
        print()
        for m in it.motifs:
            borrow = m["borrows_token"][0] if m.get("borrows_token") else "border"
            ink = f"墨量约 {m['ink_pct']}%" if m.get("ink_pct") else "墨量 —"
            if m.get("ink_note"):
                ink += f"（{m['ink_note']}）"
            print(f"点缀  {m['name']}（{m['form']}）")
            print(f"      借 {borrow} 的颜色画，不加新色；{ink}")
            print(f"      放在 {m['placement']}")
            if m.get("css_hint"):
                print(f"      尺寸 {m['css_hint']}")
            if m.get("culture_note"):
                print(f"      当心 {m['culture_note']}")
        for n in it.motif_notes:
            print(f"      提醒 {n}")

    if it.ambiguity == "响/静":
        print("\n歧义:响/静 —— 先按素净那条给的。问一句：那个红是想铺开来一眼看见，还是只留一点点？")
    if args.css:
        pals = generate(cat, n=1, **directions[0][1])
        if pals:
            tok = tokens(cat, pals[0])
            print()
            print(css_vars(tok))
    print(f"\n下一步: 说「就第 1 套」定妆，或者说「太素了 / 红少一点 / 改深色」我来调。")
    return 0


def cmd_resolve(cat: Catalog, args: argparse.Namespace) -> int:
    """只输出白话到参数的映射，不生成配色。给 selftest 与调试用。"""
    it = Vernacular().resolve(args.text, catalog=cat)
    print(json.dumps(it.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_snap(cat: Catalog, args: argparse.Namespace) -> int:
    """把任意 hex 吸附到库内最近的具名色。下游要库外新色时回来跑这个。"""
    near = cat.nearest(args.hex, n=args.n)
    for c, d in near:
        print(f"{c.name:8s} {c.hex}  ΔE {d:.2f}  {c.family}")
    return 0


def _parse_pin(specs: list | None) -> dict:
    """`--pin dominant=枫叶红` 解析。格式错抛 ValueError，由调用方打印。

    抽出来是因为 cmd_generate 和 cmd_tweak 各有一份，而 tweak 那份漏了校验：
    `--pin 枫叶红`（漏写 role=）会得到 `{'枫叶红': ''}`，然后把这个 dict 原样
    打给用户，接着报「色库里没有「」」——一个空色名。
    """
    pin: dict = {}
    for spec in (specs or []):
        role, _, name = spec.partition("=")
        role = role.strip()
        if role not in ("dominant", "secondary", "accent") or not name.strip():
            raise ValueError(f"--pin 要写成 dominant|secondary|accent=<色名>，收到的是「{spec}」")
        pin[role] = name.strip()
    return pin


def _find_by_id(cat: Catalog, pal_id: str) -> tuple[Color, Color, Color]:
    """方案 id 就是三个色名拼接，无状态，不需要会话记忆。"""
    parts = [p.strip() for p in pal_id.replace("＋", "+").split("+")]
    if len(parts) != 3:
        raise ValueError(f"方案 id 要写成「底色名+块色名+点色名」，收到的是「{pal_id}」")
    cols = []
    for p in parts:
        c = cat.resolve(p)
        if c is None:
            raise ValueError(f"色库里没有「{p}」")
        cols.append(c)
    return tuple(cols)  # type: ignore[return-value]


def cmd_pick(cat: Catalog, args: argparse.Namespace) -> int:
    """定妆：把选定的一套写成下游能读的文件。"""
    import handoff as ho
    from engine import score_trio

    try:
        dom, sec, acc = _find_by_id(cat, args.id)
    except ValueError as exc:
        # 报错文案本身是可读的，但没人接住就成了 traceback。
        # cmd_tweak 的 --from 已经这样接了，pick 漏了。
        print(exc)
        return 1
    pal = Palette(dom, sec, acc, score_trio(dom, sec, acc, args.mood),
                  args.mood, args.scene, media=args.media or "ui")
    pal.rationale = []
    dark_pal = None
    if args.pair_dark:
        dpals = generate(cat, scene=args.scene, mood=args.mood, media=args.media or "ui",
                         dark=True, n=1)
        dark_pal = dpals[0] if dpals else None

    data = ho.build(cat, pal, dark_pal=dark_pal, chosen_from=args.id,
                    motif_ids=args.motif)
    out_dir = Path(args.out) if args.out else Path(".palette")
    j, c = ho.write(data, out_dir)
    print(f"已定妆：{args.id}")
    print(f"  {j}")
    print(f"  {c}")
    print("\n六个槽（给做前端的技能读）:")
    for slot, v in data["named6"].items():
        print(f"  {slot}  {v['name']:6s} {v['hex']}")
    print(f"\n建议铺色面积: 底 {data['roles']['dominant']['area_pct']}%  "
          f"块 {data['roles']['secondary']['area_pct']}%  "
          f"点 {data['roles']['accent']['area_pct']}%")
    v = data["verify"]
    # 「块上的字」必须在这一行里。原先打的四个数字（正文/次级/按钮字/描边）
    # 一个都不是块上的字，而块的落位是「卡片与导航」——下游一定在它上面放字。
    print(f"实测对比: 正文 {v['text_on_bg']}:1  次级 {v['muted_on_bg']}:1  "
          f"块上的字 {v['secondary_fg_on_secondary']}:1  "
          f"按钮字 {v['accent_fg_on_accent']}:1  描边 {v['border_strong_on_bg']}:1")
    print(f"          徽章上的字 成功 {v['success_fg_on_success']}:1  "
          f"警示 {v['warning_fg_on_warning']}:1  错误 {v['error_fg_on_error']}:1  "
          f"信息 {v['info_fg_on_info']}:1")
    orn = data.get("ornament") or {}
    if orn.get("unknown_ids"):
        # 拼错的 id 要报出来，不许静默交出一个没有纹样的文件
        print(f"\n纹样 id 不存在：{'、'.join(orn['unknown_ids'])}"
              f"　跑 palette.py motifs 看清单，这几个没写进交接文件")
    if orn.get("chosen"):
        print("\n点缀（借色，不占配比）:")
        for m in orn["chosen"]:
            ink = f"墨量 {m['ink_pct']}%" if m.get("ink_pct") else ""
            if m.get("ink_note"):
                ink += f"（{m['ink_note']}）"
            print(f"  · {m['name']}  借 {m['borrows_var']}  {ink}  "
                  f"alpha {m['alpha_suggested']}")
            print(f"    {m['placement']}")
    # 纹样自己的问题也要打。原先只打 data["issues"]，
    # 彩度闸门、alpha 上限、借色白名单、场景不合全都算出来了却没人看见——
    # 用户要打开 JSON 才知道刚才那个纹样是不合规的。
    if orn.get("issues"):
        print("\n纹样的问题（同样不许静默交付）:")
        for i in orn["issues"]:
            print(f"  · {i['motif']}: {i['problem']}")
            if i.get("fix"):
                print(f"    改法: {i['fix']}")
    if data["cliche"]:
        print("\n撞车提示:")
        for x in data["cliche"]:
            print(f"  · {x['detail']}")
            print(f"    处置: {x['handle']}")
    if data["issues"]:
        print("\n未解决的问题（要向用户明说，不许静默交付）:")
        for i in data["issues"]:
            print(f"  · {i['token']}: {i['problem']}")
    return 0


def cmd_tweak(cat: Catalog, args: argparse.Namespace) -> int:
    """白话微调。词义与首轮相反，走 vernacular.tweak 的独立词表。"""
    vern = Vernacular()
    tw = vern.tweak(args.text, current_mood=args.mood, current_dark=args.dark)
    try:
        pin = _parse_pin(args.pin)
    except ValueError as exc:
        print(exc)
        return 2
    if args.from_id:
        try:
            dom, sec, acc = _find_by_id(cat, args.from_id)
        except ValueError as exc:
            print(exc)
            return 1
        # 「换个底其他别动」——把没被点到的两个钉住
        if args.keep:
            for role in args.keep:
                pin.setdefault(role, {"dominant": dom, "secondary": sec, "accent": acc}[role].name)
    print(f"听到: {args.text}")
    for what, how in tw["actions"]:
        print(f"照做: {what} —— {how}")
    for note in tw["note"]:
        print(f"要说明: {note}")
    if not tw["actions"]:
        print("照做: 没听出明确的调整方向，按原方向重跑（读 references/tweaks.md 对一下词）")
    for role, name in (tw.get("pin") or {}).items():
        pin.setdefault(role, name)
    if pin:
        print(f"钉住: {pin}")
    scene = args.scene or tw.get("scene_hint")
    try:
        pals = generate(cat, scene=scene, mood=tw["mood"], media=args.media or "ui",
                        dark=tw["dark"], n=args.n, pin=pin or None)
    except SeedNotFound as exc:
        print(exc)
        return 1
    if not pals:
        print("这个方向没有合格候选。要么放宽一点，要么换个方向——我不会为了凑数偷偷换色。")
        return 1
    for i, p in enumerate(pals):
        _print_plain(p, cat, vern, bar=not args.no_bar, label=f"改后 {i + 1}")
    return 0


def cmd_motifs(cat: Catalog, args: argparse.Namespace) -> int:
    """列出可用的纹样。纹样是点缀，借已有 token 的色，不占配比。"""
    import handoff as ho
    data = ho._load_motifs()
    ms = data.get("motifs", [])
    cross = []
    if args.scene:
        # 「适配」要按纹样自己的 fits_scenes 算，不是「没被 avoid_scenes 排除」。
        # 后者会把年画场景下 12 条列成适配，而其中 11 条自己写的适配场景里没有年画。
        fitted, crossed = [], []
        for m in ms:
            if args.scene in (m.get("avoid_scenes") or []):
                continue
            fits = m.get("fits_scenes") or []
            (fitted if (not fits or args.scene in fits) else crossed).append(m)
        ms, cross = fitted, crossed
    if args.category:
        ms = [m for m in ms if m["category"] == args.category]
        cross = [m for m in cross if m["category"] == args.category]
    label = {"flora": "花卉", "landscape": "风景", "geometric": "几何"}
    print(f"{len(ms)} 个纹样" + (f"（适配 {args.scene}）" if args.scene else ""))
    for m in ms:
        borrow = (m.get("borrows_token") or ["border"])[0]
        season = m.get("season", "无季")
        rig = {"high": "季节要紧", "mid": "季节略要紧", "none": ""}.get(
            m.get("season_rigidity", ""), "")
        ink = f"墨量 {m['ink_pct']}%" if m.get("ink_pct") else "墨量 —"
        if m.get("ink_note"):
            ink += f"（{m['ink_note']}）"
        print()
        print(f"  {m['id']:18s} {m['name']}  [{label.get(m['category'], m['category'])}]"
              f"  {season}{'·' + rig if rig else ''}")
        print(f"    {m['form']} · 借 {borrow} · {ink}")
        print(f"    {m['placement']}")
        if m.get("culture_note"):
            print(f"    当心 {m['culture_note'][:88]}")
    if cross:
        # 跨场景借用不是禁止，是要说明。静默丢掉会让用户以为库里没有梅花。
        print()
        print(f"能用但不是{args.scene}的语汇（跨场景借用，要向用户说明）:")
        for m in cross:
            print(f"  {m['id']:18s} {m['name']}　本是 {'、'.join(m.get('fits_scenes') or [])} 的东西")
    if data.get("sets"):
        print()
        print("成套（不可混、不可拆）:")
        for name, spec in data["sets"].items():
            names = [x["name"] for x in data["motifs"] if x["id"] in (spec.get("members") or [])]
            print(f"  {name}: {'、'.join(names)}")
    return 0


def cmd_search(cat: Catalog, args: argparse.Namespace) -> int:
    hits = cat.search(
        query=args.query or "", family=args.family, wuxing=args.wuxing,
        season=args.season, role=args.role, temperature=args.temperature,
        tone=args.tone, chroma_band=args.chroma, limit=args.limit,
    )
    print(f"{len(hits)} 条")
    for c in hits:
        _print_color(c)
    return 0


def cmd_info(cat: Catalog, args: argparse.Namespace) -> int:
    alias = cat.aliases.get(args.query)
    c = cat.resolve(args.query)
    if alias:
        print(f"「{args.query}」是别名 -> {alias['target']} {alias['target_hex']}")
        print(f"  原因：{alias['reason']}")
        if alias.get("literary_intro"):
            print(f"  典故：{alias['literary_intro'][:120]}")
        if alias.get("literary_hex"):
            print(f"  文学色卡 hex {alias['literary_hex']} 仅作参考，输出必须用 {alias['target_hex']}")
    if c is None:
        print("色库中没有这条。试试 search。")
        return 1
    rec = c.rec
    print(f"{c.name}  {c.pinyin}  {c.hex}")
    print(f"  RGB {c.rgb}  CMYK {c.cmyk}")
    print(f"  HSL {rec['hsl']}  HSV {rec['hsv']}  Lab {rec['lab']}  LCH {rec['lch']}")
    print(f"  色系 {c.family}（名义 {rec['family_by_name']} / 色值 {rec['family_by_hue']}）")
    print(f"  五行 {c.wuxing}（{rec['wuxing_direction']}） 季节 {c.season}")
    print(f"  明度带 {c.tone}  彩度带 {c.chroma_band}  冷暖 {c.temperature} ({c.warmth:+.2f})")
    print(f"  物象 {c.source_category}  角色 {', '.join(c.roles)}")
    print(f"  对比 白底 {rec['contrast_white']}  黑底 {rec['contrast_black']}  乳白底 {rec['contrast_paper']}")
    print(f"  APCA 白底 Lc={rec['apca_on_white']}  黑底 Lc={rec['apca_on_black']}")
    return 0


def cmd_generate(cat: Catalog, args: argparse.Namespace) -> int:
    try:
        pin = _parse_pin(args.pin)
    except ValueError as exc:
        print(exc)
        return 2
    try:
        pals = generate(cat, mood=args.mood, scene=args.scene, seed=args.seed, n=args.n,
                        dark=args.dark, media=args.media, pin=pin or None)
    except SeedNotFound as exc:
        print(exc)
        return 1
    if not pals:
        print("没有生成出合格的配色。试着放宽氛围，或换一个种子色。")
        return 1
    for p in pals:
        _print_palette(p, cat)
        if args.json:
            print(json.dumps(as_dict(p, tokens(cat, p)), ensure_ascii=False, indent=2))
        if args.css:
            print(css_vars(tokens(cat, p)))
        if args.tailwind:
            print(tailwind_extend(tokens(cat, p)))
    return 0


def cmd_complete(cat: Catalog, args: argparse.Namespace) -> int:
    pals = complete_pair(cat, args.color_a, args.color_b, mood=args.mood)
    if not pals:
        print("无法补全。检查色名是否在色库或别名表中。")
        return 1
    for p in pals:
        _print_palette(p, cat)
    return 0


def cmd_preview(cat: Catalog, args: argparse.Namespace) -> int:
    pals = generate(cat, mood=args.mood, scene=args.scene, seed=args.seed, n=args.n,
                    dark=args.dark, media=args.media)
    if not pals:
        print("没有可预览的配色。")
        return 1
    html = _preview_html(cat, pals)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"已写入 {out.resolve()}")
    return 0


def _preview_html(cat: Catalog, pals: list[Palette]) -> str:
    from handoff import _verify
    blocks, styles = [], []
    for i, p in enumerate(pals):
        tok = tokens(cat, p)
        styles.append(css_vars(tok, f".scheme-{i}"))
        areas = visual_areas(p)["pixel_pct"]
        labels = _role_labels(p.media)
        swatches = "".join(
            f'<div style="flex:{pct};background:{c.hex}" title="{label} {c.name} {c.hex} · {pct:.0f}%"></div>'
            for pct, label, c in ((areas["dominant"], labels[0], p.dominant),
                                  (areas["secondary"], labels[1], p.secondary),
                                  (areas["accent"], labels[2], p.accent))
        )
        token_row = "".join(
            f'<div class="tk"><i style="background:{c.hex}"></i><span>{k}</span><span>{c.name}</span><code>{c.hex}</code></div>'
            for k, c in tok.items()
        )
        legend = "".join(f'<span><i style="background:{c.hex}"></i>{c.name} <code>{c.hex}</code>'
                         f' · {areas[r]:.0f}%</span>'
                         for r, c in (("dominant", p.dominant), ("secondary", p.secondary), ("accent", p.accent)))
        verify = _verify(tok, cat)
        checks = "".join(f'<span>{label} <b>{verify[key]:.2f}:1</b></span>' for key, label in (
            ("text_on_surface", "卡片正文"), ("muted_on_surface", "卡片说明"),
            ("accent_fg_on_accent_hover", "悬停文字"), ("accent_fg_on_accent_active", "按下文字"),
            ("border_strong_on_surface", "输入轮廓")))
        issues = "".join(f'<li>{escape(f["label"])} {f["got"]}:1，需 ≥{f["need"]}:1</li>'
                         for f in verify["fail"])
        title = escape(p.curated_name or p.scene or p.mood or "中国色")
        component = f'''
          <div class="demo">
            <nav aria-label="示例导航"><strong>山间茶事</strong><span class="nav-current">茶单</span><span>产地</span><span>关于</span></nav>
            <div class="demo-grid">
              <section class="intro"><p class="eyebrow">本季 · 山间新茶</p>
                <h3>一盏清茶，<br>留一点从容。</h3>
                <p class="description">慢一点，感受茶叶舒展的时间。<br>从一份清晰的茶单，找到今天的味道。</p>
                <div class="actions"><button type="button" class="primary">查看茶单</button><button type="button" class="quiet">了解产地</button></div>
              </section>
              <section class="content-card"><h4>春日茶单</h4><p class="muted">本季新采 · 两款风味</p>
                <div class="tea-row"><span>明前龙井</span><span class="muted">清鲜 · 豆香</span></div>
                <div class="tea-row"><span>正山小种</span><span class="muted">温润 · 花香</span></div>
                <label for="search-{i}">寻找一款茶</label><input id="search-{i}" placeholder="输入茶名" type="text">
              </section>
            </div>
            <div class="states" aria-label="按钮状态对照"><span class="muted">按钮状态</span>
              <button type="button" class="primary">默认</button><button type="button" class="primary hover-state">悬停</button><button type="button" class="primary active-state">按下</button>
            </div>
          </div>''' if p.media in (None, "ui") else ""
        blocks.append(f'''
          <article class="scheme-{i}">
            <header class="scheme-heading"><h2>{i+1:02d} · {title}</h2><span>{"深色" if p.dark else "浅色"}方案</span></header>
            {component}
            <div class="bar" aria-label="建议铺色面积">{swatches}</div><div class="legend">{legend}</div>
            <div class="checks">{checks}</div>{f'<ul class="issues">{issues}</ul>' if issues else ''}
            <details><summary>查看完整颜色与用途</summary><div class="tokens">{token_row}</div></details>
          </article>''')
    paper, ink = cat.by_name["鱼肚白"], cat.by_name["长石灰"]
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>中国色 · 组件配色预览</title>
<style>
  {''.join(styles)}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: {paper.hex}; color: {ink.hex}; font: 15px/1.6 system-ui,"Microsoft YaHei",sans-serif; }}
  main {{ max-width: 1080px; margin: auto; padding: 40px 24px; }}
  h1 {{ font-size: 24px; margin: 0; font-weight: 500; }}
  .lead {{ margin: 8px 0 32px; }}
  article {{ margin-bottom: 48px; }}
  .scheme-heading {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 16px 0; }}
  h2 {{ font-size: 17px; font-weight: 500; margin: 0; }}
  .demo {{ background: var(--color-bg); color: var(--color-text); padding: 28px 36px; border-radius: 8px; }}
  nav {{ display: flex; gap: 24px; align-items: center; }}
  nav strong {{ margin-right: auto; font-weight: 600; letter-spacing: .14em; }}
  .nav-current {{ background: var(--color-secondary); color: var(--color-secondary-fg); padding: 3px 14px; border-radius: 4px; }}
  .demo-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 48px; margin: 32px 0; align-items: center; }}
  .eyebrow, .muted, .description {{ color: var(--color-muted); }}
  .eyebrow {{ font-size: 13px; margin: 0 0 12px; }}
  h3 {{ margin: 0; font: 500 36px/1.4 "Noto Serif SC","SimSun",serif; }}
  .description {{ font-size: 14px; margin: 20px 0; }}
  .actions, .states {{ display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }}
  button, input {{ font: inherit; }}
  button {{ cursor: pointer; min-height: 42px; padding: 8px 18px; border-radius: 4px; border: 0; }}
  .primary {{ background: var(--color-accent); color: var(--color-accent-fg); }}
  .primary:hover, .hover-state {{ background: var(--color-accent-hover); }}
  .primary:active, .active-state {{ background: var(--color-accent-active); transform: translateY(1px); }}
  .quiet {{ background: var(--color-bg); color: var(--color-text); text-decoration: underline; text-underline-offset: 4px; }}
  .demo :focus-visible {{ outline: 2px solid var(--color-ring); outline-offset: 3px; }}
  .content-card {{ background: var(--color-surface); color: var(--color-text); padding: 24px; border-radius: 6px; }}
  h4 {{ margin: 0; font-size: 19px; font-weight: 500; }}
  .content-card p {{ margin: 5px 0 16px; font-size: 13px; }}
  .tea-row {{ display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-top: 1px solid var(--color-border); }}
  label {{ display: block; font-size: 13px; margin: 16px 0 6px; }}
  input {{ width: 100%; min-width: 0; padding: 9px 12px; border: 1px solid var(--color-border-strong); border-radius: 4px; background: var(--color-surface); color: var(--color-text); }}
  input::placeholder {{ color: var(--color-muted); opacity: 1; }}
  .states {{ border-top: 1px solid var(--color-border); padding-top: 20px; font-size: 13px; }}
  .states button {{ min-height: 36px; padding: 6px 16px; }}
  .bar {{ display: flex; height: 10px; margin-top: 20px; overflow: hidden; }}
  .legend, .checks {{ display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 12px 0; font-size: 13px; }}
  .legend span {{ display: inline-flex; gap: 6px; align-items: center; }}
  .legend i, .tk i {{ display: inline-block; flex-shrink: 0; width: 14px; height: 14px; }}
  code {{ font: 12px/1.5 ui-monospace,monospace; }}
  summary {{ cursor: pointer; font-size: 13px; }}
  .tokens {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(290px,1fr)); gap: 8px 24px; margin-top: 16px; }}
  .tk {{ display: flex; align-items: center; gap: 8px; font-size: 12px; }}
  .tk span:first-of-type {{ min-width: 104px; }}
  .issues {{ padding-left: 20px; }}
  @media(max-width:680px) {{ main {{ padding: 24px 16px; }} .demo {{ padding: 24px 20px; }} .demo-grid {{ grid-template-columns: 1fr; gap: 28px; }} nav {{ gap: 12px; font-size: 13px; }} h3 {{ font-size: 30px; }} .tokens {{ grid-template-columns: 1fr; }} }}
</style></head><body><main>
<h1>中国色 · 组件配色预览</h1><p class="lead">在实际文字、卡片和按钮上看配色。悬停、按下按钮，或用 Tab 检查焦点。</p>
{''.join(blocks)}
</main></body></html>
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="中国传统色配色")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="白话入口：把用户原话原样传进来")
    a.add_argument("text", help="用户的原话，一字不改")
    a.add_argument("--n", type=int, default=2, help="给几套（默认 2）")
    a.add_argument("--css", action="store_true", help="附 CSS 变量")
    a.add_argument("--no-bar", action="store_true", help="不画色条")
    a.set_defaults(func=cmd_ask)

    r = sub.add_parser("resolve", help="只看白话映射结果，不生成配色")
    r.add_argument("text")
    r.set_defaults(func=cmd_resolve)

    sn = sub.add_parser("snap", help="任意 hex -> 库内最近具名色")
    sn.add_argument("hex")
    sn.add_argument("--n", type=int, default=3)
    sn.set_defaults(func=cmd_snap)

    tw = sub.add_parser("tweak", help="白话微调：把用户的反馈原话传进来")
    tw.add_argument("text")
    tw.add_argument("--from", dest="from_id", help="从哪一套改起，写「底+块+点」")
    tw.add_argument("--keep", action="append", choices=["dominant", "secondary", "accent"],
                    help="钉住不动的角色，可多次")
    tw.add_argument("--pin", action="append", help="钉死某个角色，如 accent=枫叶红")
    tw.add_argument("--scene", choices=list(SCENES))
    tw.add_argument("--mood", choices=list(MOODS), help="当前这一套的档位，用于升降一档")
    tw.add_argument("--media", choices=list(MEDIA))
    tw.add_argument("--dark", action="store_true", help="当前是暗色方案")
    tw.add_argument("--n", type=int, default=2)
    tw.add_argument("--no-bar", action="store_true")
    tw.set_defaults(func=cmd_tweak)

    pk = sub.add_parser("pick", help="定妆：写 .palette/handoff.json 与 palette.css")
    pk.add_argument("id", help="选定的那套，写「底+块+点」")
    pk.add_argument("--scene", choices=list(SCENES))
    pk.add_argument("--mood", choices=list(MOODS))
    pk.add_argument("--media", choices=list(MEDIA))
    pk.add_argument("--pair-dark", action="store_true", help="同时推导暗色一套")
    pk.add_argument("--motif", action="append",
                    help="纹样 id，可多次。用 palette.py motifs 看清单")
    pk.add_argument("--out", help="输出目录，默认 .palette")
    pk.set_defaults(func=cmd_pick)

    mo = sub.add_parser("motifs", help="列出中国风纹样点缀")
    mo.add_argument("--scene", choices=list(SCENES))
    # vessel（器物）在数据 schema 里保留，但当前 22 条纹样一条都没有。
    # 放进 choices 会让用户照 --help 跑出「0 个纹样」——空选项是陷阱。
    # 有器物纹样进表时再加回来，selftest 会守「choices 里每一档都有货」。
    mo.add_argument("--category", choices=["flora", "landscape", "geometric"])
    mo.set_defaults(func=cmd_motifs)

    s = sub.add_parser("search", help="检索色库")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--family"); s.add_argument("--wuxing"); s.add_argument("--season")
    s.add_argument("--role"); s.add_argument("--temperature"); s.add_argument("--tone")
    s.add_argument("--chroma"); s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_search)

    i = sub.add_parser("info", help="查看单色（支持别名）")
    i.add_argument("query")
    i.set_defaults(func=cmd_info)

    g = sub.add_parser("generate", help="按氛围/场景/种子生成配色")
    g.add_argument("--mood", choices=list(MOODS))
    g.add_argument("--scene", choices=list(SCENES))
    g.add_argument("--seed", help="色名、拼音或 hex（软锚，不保证进三色）")
    g.add_argument("--pin", action="append",
                   help="钉死角色，如 accent=枫叶红（硬钉，必出现）。可多次")
    g.add_argument("--n", type=int, default=5)
    g.add_argument("--dark", action="store_true", help="暗色方案：深底做场，不整页反相")
    g.add_argument("--media", choices=list(MEDIA), help="媒材：ui / poster / fashion / interior")
    g.add_argument("--json", action="store_true")
    g.add_argument("--css", action="store_true")
    g.add_argument("--tailwind", action="store_true")
    g.set_defaults(func=cmd_generate)

    c = sub.add_parser("complete", help="两色补全为一套三色")
    c.add_argument("color_a"); c.add_argument("color_b")
    c.add_argument("--mood", choices=list(MOODS))
    c.set_defaults(func=cmd_complete)

    v = sub.add_parser("preview", help="生成 HTML 预览")
    v.add_argument("--mood", choices=list(MOODS))
    v.add_argument("--scene", choices=list(SCENES))
    v.add_argument("--seed")
    v.add_argument("--n", type=int, default=4)
    v.add_argument("--dark", action="store_true")
    v.add_argument("--media", choices=list(MEDIA))
    v.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "assets" / "preview.html"))
    v.set_defaults(func=cmd_preview)

    return p


def main() -> int:
    args = build_parser().parse_args()
    cat = Catalog()
    return args.func(cat, args)


if __name__ == "__main__":
    raise SystemExit(main())
