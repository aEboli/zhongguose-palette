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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import (  # noqa: E402
    MEDIA, MOODS, SCENES, Catalog, Color, Palette, as_dict, complete_pair, css_vars,
    generate, tokens, tailwind_extend, visual_areas,
)


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
                  "secondary", "accent", "accent_fg", "accent_hover", "accent_active",
                  "success", "warning", "error", "info", "disabled", "ring"):
            c = tok[k]
            print(f"    {k:14s} {c.name:8s} {c.hex}")


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
    pals = generate(cat, mood=args.mood, scene=args.scene, seed=args.seed, n=args.n,
                    dark=args.dark, media=args.media)
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
    blocks = []
    for i, p in enumerate(pals):
        tok = tokens(cat, p)
        swatches = "".join(
            f'<div class="sw" style="flex:{flex};background:{c.hex}" title="{label} {c.name} {c.hex}">'
            f'<span>{label} {c.name}<br>{c.hex}</span></div>'
            for flex, label, c in ((6, "主场", p.dominant), (3, "结构", p.secondary), (1, "点缀", p.accent))
        )
        token_row = "".join(
            f'<div class="tk"><i style="background:{c.hex}"></i><b>{k}</b><em>{c.name}</em><code>{c.hex}</code></div>'
            for k, c in tok.items()
        )
        why = "".join(f"<li>{line}</li>" for line in p.rationale)
        blocks.append(
            f'<article><header><h2>方案 {i+1} · {p.score["total"]:.0f} 分'
            f'{(" · "+p.mood) if p.mood else ""}{(" · "+p.scene) if p.scene else ""}</h2></header>'
            f'<div class="bar">{swatches}</div><div class="tokens">{token_row}</div>'
            f'<ul class="why">{why}</ul></article>'
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>中国色配色预览</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; font: 15px/1.6 "Songti SC","Noto Serif SC","Source Han Serif SC",serif;
         background: #f7f4ed; color: #2b2b2b; }}
  h1 {{ font-weight: 500; letter-spacing: .2em; text-align: center; padding: 2rem 1rem .5rem; }}
  article {{ max-width: 920px; margin: 0 auto 2.5rem; padding: 0 1.25rem; }}
  .bar {{ display: flex; height: 160px; border-radius: 2px; overflow: hidden; }}
  .sw {{ position: relative; }}
  .sw span {{ position: absolute; left: 12px; bottom: 10px; color: #111;
              background: rgba(255,255,255,.55); padding: 2px 8px; font-size: 12px; }}
  .tokens {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }}
  .tk {{ display: flex; align-items: center; gap: 8px; font-size: 12px; }}
  .tk i {{ width: 18px; height: 18px; display: inline-block; border: 1px solid #0001; }}
  .tk em {{ font-style: normal; }}
  .tk code {{ color: #666; }}
  .why {{ color: #555; }}
</style></head>
<body>
<h1>中国色 · 配色</h1>
{''.join(blocks)}
</body></html>
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="中国传统色配色")
    sub = p.add_subparsers(dest="cmd", required=True)

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
    g.add_argument("--seed", help="色名、拼音或 hex")
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
