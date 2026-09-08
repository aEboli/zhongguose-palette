#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 zhongguose.com 的原始 526 色加工成带完整计算属性与分类的检索色库。

用法：
    python build_catalog.py --src colors_raw.json --out ../references/colors.json
    python build_catalog.py --fetch --out ../references/colors.json   # 直接联网抓取

数据来源：https://zhongguose.com/colors.json（字段 name / pinyin / hex / RGB / CMYK）

原始数据的两处已知问题，此脚本统一处理：
1. 8 条记录的 hex 与 RGB 字段不一致（如"玫瑰灰" hex #4b2e2b 对 RGB [175,46,43]）。
   以 hex 为准——网站色卡渲染用的是 hex，那才是大家看到并复制的颜色；
   原始 RGB 保留在 rgb_source 字段里，便于追溯。
2. 7 组拼音重复（鼬黄/柚黄 同为 youhuang 等）。加数字后缀去重，
   原始拼音保留在 pinyin_source。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import colorkit as ck  # noqa: E402
import taxonomy as tx  # noqa: E402

SOURCE_URL = "https://zhongguose.com/colors.json"
PAPER = "#f9f4dc"  # 乳白，作为"宣纸底"参考色算对比度


def fetch_source() -> list[dict]:
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "zhongguose-palette/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_source(path: Path | None, fetch: bool) -> list[dict]:
    if fetch or path is None:
        return fetch_source()
    return json.loads(path.read_text(encoding="utf-8"))


def dedupe_pinyin(records: list[dict]) -> None:
    """同拼音的按出现顺序加 2、3… 后缀，保证 pinyin 可作唯一键。"""
    seen: dict[str, int] = {}
    for rec in records:
        base = rec["pinyin_source"]
        seen[base] = seen.get(base, 0) + 1
        rec["pinyin"] = base if seen[base] == 1 else f"{base}{seen[base]}"


def build(raw: list[dict]) -> dict:
    records: list[dict] = []
    mismatches: list[dict] = []

    for idx, item in enumerate(raw):
        hex_value = item["hex"].lower()
        if not hex_value.startswith("#"):
            hex_value = "#" + hex_value
        rgb = ck.hex_to_rgb(hex_value)
        rgb_source = list(item.get("RGB") or rgb)
        if list(rgb) != rgb_source:
            mismatches.append(dict(name=item["name"], hex=hex_value,
                                   hex_rgb=list(rgb), rgb_source=rgb_source))

        h_hsl, s_hsl, l_hsl = ck.rgb_to_hsl(rgb)
        h_hsv, s_hsv, v_hsv = ck.rgb_to_hsv(rgb)
        lab = ck.rgb_to_lab(rgb)
        lch = ck.lab_to_lch(lab)
        lum = ck.relative_luminance(rgb)
        cw = ck.contrast_ratio(rgb, (255, 255, 255))
        cb = ck.contrast_ratio(rgb, (0, 0, 0))
        cp = ck.contrast_ratio(rgb, ck.hex_to_rgb(PAPER))
        warm = ck.warmth(rgb)

        name = item["name"]
        family, name_family, hue_family = tx.family_of(name, lch[2], lch[1], lch[0])
        wuxing = tx.wuxing_of(family, lch[0], lch[1], name)

        records.append({
            "index": idx,
            "name": name,
            "pinyin_source": item["pinyin"],
            "hex": hex_value,
            "rgb": list(rgb),
            "cmyk": list(item.get("CMYK") or []),
            "hsl": [round(h_hsl, 1), round(s_hsl, 1), round(l_hsl, 1)],
            "hsv": [round(h_hsv, 1), round(s_hsv, 1), round(v_hsv, 1)],
            "lab": [round(v, 2) for v in lab],
            "lch": [round(v, 2) for v in lch],
            "luminance": round(lum, 4),
            "contrast_white": round(cw, 2),
            "contrast_black": round(cb, 2),
            "contrast_paper": round(cp, 2),
            "apca_on_white": round(ck.apca_lc(rgb, (255, 255, 255)), 1),
            "apca_on_black": round(ck.apca_lc(rgb, (0, 0, 0)), 1),
            "family": family,
            "family_by_name": name_family,
            "family_by_hue": hue_family,
            "wuxing": wuxing,
            "wuxing_direction": tx.WUXING_MERIDIAN[wuxing]["direction"],
            "season": tx.season_of(family, lch[0], lch[1], name),
            "tone": tx.tone_of(lch[0]),
            "chroma_band": tx.chroma_of(lch[1]),
            "warmth": round(warm, 3),
            "temperature": tx.temperature_of(warm),
            "source_category": tx.source_of(name),
            "roles": tx.roles_of(family, lch[0], lch[1], cw, cb, name),
            "cvd": {
                kind: ck.rgb_to_hex(ck.simulate_cvd(rgb, kind))
                for kind in ("protanopia", "deuteranopia", "tritanopia")
            },
        })

        if list(rgb) != rgb_source:
            records[-1]["rgb_source"] = rgb_source

    dedupe_pinyin(records)

    stats = {
        "count": len(records),
        "families": _tally(records, "family"),
        "wuxing": _tally(records, "wuxing"),
        "season": _tally(records, "season"),
        "tone": _tally(records, "tone"),
        "chroma_band": _tally(records, "chroma_band"),
        "temperature": _tally(records, "temperature"),
        "source_category": _tally(records, "source_category"),
        "roles": _tally_list(records, "roles"),
    }

    return {
        "meta": {
            "source": SOURCE_URL,
            "source_name": "中国色 zhongguose.com",
            "count": len(records),
            "canonical_field": "hex",
            "note": "hex 为准，rgb_source 保留原始 RGB 字段以便追溯；pinyin 已去重。",
            "hex_rgb_mismatches": mismatches,
            "color_space": "sRGB / D65；lab 与 lch 为 CIELAB 与 CIELCh",
            "contrast_basis": "WCAG 2.2 相对亮度；apca_* 为 APCA 0.1.9 近似值，仅作感知参考",
            "paper_reference": PAPER,
        },
        "stats": stats,
        "colors": records,
    }


def _tally(records: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for rec in records:
        out[rec[key]] = out.get(rec[key], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _tally_list(records: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for rec in records:
        for value in rec[key]:
            out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description="构建中国传统色检索色库")
    ap.add_argument("--src", type=Path, help="原始 colors.json 路径")
    ap.add_argument("--fetch", action="store_true", help="直接从 zhongguose.com 抓取")
    ap.add_argument("--out", type=Path, required=True, help="输出路径")
    args = ap.parse_args()

    raw = load_source(args.src, args.fetch)
    catalog = build(raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    meta, stats = catalog["meta"], catalog["stats"]
    print(f"已写入 {args.out}  共 {meta['count']} 色")
    print(f"hex/RGB 不一致 {len(meta['hex_rgb_mismatches'])} 条（以 hex 为准）")
    for key in ("families", "wuxing", "season", "tone", "chroma_band", "temperature"):
        pairs = " ".join(f"{k}:{v}" for k, v in stats[key].items())
        print(f"  {key:14s} {pairs}")
    print(f"  {'source':14s} " + " ".join(f"{k}:{v}" for k, v in stats["source_category"].items()))
    print(f"  {'roles':14s} " + " ".join(f"{k}:{v}" for k, v in stats["roles"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
