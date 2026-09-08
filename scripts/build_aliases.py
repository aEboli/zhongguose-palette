#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成经典色名 -> 526 色库的别名表。

两套中国色数据经常被混用：
- zhongguose.com 526 色（本 skill 的唯一输出色库，GB/T 风格测量色）
- 网络流传的 ~161 色文学色名（zerosoul/chinese-colors，含胭脂、玄色、石青、黛）

用户会说"给我石青+月白"。石青不在 526 里，zerosoul 还给了一个薄荷绿——
那是把"石青"误当成了青绿。真正的石青是蓝铜矿，应该落到群青/花青/景泰蓝。

本脚本：先按 CIEDE2000 找最近邻，再用 CULTURAL_OVERRIDE 覆盖文化错配。
输出的 hex 永远是 526 色库里的，绝不发明新色，也不采用 zerosoul 的 hex 作为输出。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import colorkit as ck  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references" / "colors.json"
ZEROSOUL = Path(__file__).resolve().parents[2] / "_scratch" / "zerosoul_flat.json"
OUT = ROOT / "references" / "aliases.json"

# 文化校正：zerosoul hex 或色差最近邻会给出错误文化指向时，强制改到正确的 526 色。
CULTURAL_OVERRIDE = {
    "石青": ("群青", "石青为蓝铜矿，正色是深蓝；网络色卡常误作薄荷绿，不可用"),
    "天青": ("霁青", "汝窑『雨过天青云破处』，青中带灰的天色，不是鲜蓝"),
    "牙白": ("菊蕾白", "牙白/牙色是带黄的暖白，近菊蕾白而非纯白"),
    "茶白": ("粉白", "茶白为微黄的暖白，如茶汤渍过的绢"),
    "米白": ("米色", "米色即米白"),
    "秋香": ("新禾绿", "秋香色是浅橄榄黄绿，不是纯黄"),
    "秋香色": ("新禾绿", "秋香色是浅橄榄黄绿"),
    "绛": ("枣红", "绛是深正红，比朱红沉、比殷红暖"),
    "黛": ("野葡萄紫", "黛为青黑色画眉颜料，不是鲜紫"),
    "竹青": ("瓦松绿", "竹青是竹子外皮的灰绿，不是鲜绿"),
    "缃色": ("鹦鹉冠黄", "缃是浅黄，汉代染名"),
    "琥珀": ("槟榔综", "琥珀是透明棕橙，近槟榔综/火砖红"),
    "靛蓝": ("鷃蓝", "靛蓝是菘蓝染出的深青蓝，近黑"),
    "藏青": ("鷃蓝", "藏青蓝而近黑"),
    "漆黑": ("燕颔蓝", "526 色无纯黑，燕颔蓝是最接近的极深色"),
    "墨色": ("战舰灰", "墨色在水墨里是蓝灰，不是纯黑"),
    "玄色": ("可可棕", "玄是赤黑，黑中带红，周礼正色"),
    "胭脂": ("苋菜红", "胭脂是红花/红蓝花染出的暗红，国画颜料"),
    "缟": ("粉白", "缟是未经染色的绢白"),
    "素": ("月白", "素是无染色的本色，偏冷的浅"),
    "荼白": ("月白", "如荼之白，冷白"),
    "霜色": ("云峰白", "霜是冷白微蓝"),
    "铅白": ("芡食白", "铅粉的冷白"),
    "牙色": ("菊蕾白", "象牙的暖黄白"),
    "精白": ("雪白", "极白，近海参灰/雪白/象牙白"),
    "赤金": ("甘草黄", "足金的颜色"),
    "金色": ("芒果黄", "平均深黄带光泽"),
    "鸭卵青": ("月白", "极淡的青灰白"),
    "蟹壳青": ("穹灰", "深灰绿，蟹壳内侧"),
    "鸦青": ("黄昏灰", "鸦羽的黑而带紫绿光"),
    "松花": ("苹果绿", "松花粉的浅黄绿"),
    "松花色": ("苹果绿", "松花粉色，《红楼梦》松花配桃红"),
    "宝蓝": ("飞燕草蓝", "皇室蓝，宜小面积配金"),
    "绯红": ("鹤顶红", "艳丽的深红"),
    "黛蓝": ("鲸鱼灰", "深蓝色的黛"),
    "黛绿": ("飞泉绿", "墨绿"),
    "黛紫": ("紫灰", "深紫"),
}


def nearest(hex_value: str, colors: list[dict], n: int = 3) -> list[tuple[dict, float]]:
    ranked = sorted(colors, key=lambda c: ck.delta_e_hex(hex_value, c["hex"]))
    return [(c, ck.delta_e_hex(hex_value, c["hex"])) for c in ranked[:n]]


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    colors = catalog["colors"]
    by_name = {c["name"]: c for c in colors}
    zerosoul = json.loads(ZEROSOUL.read_text(encoding="utf-8")) if ZEROSOUL.exists() else []

    aliases: list[dict] = []
    same_name: list[dict] = []

    for z in zerosoul:
        if z["name"] in by_name:
            zg = by_name[z["name"]]
            de = round(ck.delta_e_hex(z["hex"], zg["hex"]), 1)
            if de >= 8:
                same_name.append({
                    "name": z["name"],
                    "catalog_hex": zg["hex"],
                    "literary_hex": z["hex"],
                    "delta_e": de,
                    "literary_intro": z.get("intro") or "",
                    "note": "同名异色：输出必须用 catalog_hex，literary_hex 仅作典故参考",
                })
            continue

        top = nearest(z["hex"], colors, 3)
        target_name = CULTURAL_OVERRIDE[z["name"]][0] if z["name"] in CULTURAL_OVERRIDE else top[0][0]["name"]
        target = by_name[target_name]
        reason = CULTURAL_OVERRIDE[z["name"]][1] if z["name"] in CULTURAL_OVERRIDE else "按 CIEDE2000 最近邻落入 526 色库"
        aliases.append({
            "alias": z["name"],
            "target": target["name"],
            "target_hex": target["hex"],
            "target_pinyin": target["pinyin"],
            "literary_hex": z["hex"],
            "literary_intro": (z.get("intro") or "").strip(),
            "literary_family": z.get("family") or "",
            "delta_e_to_literary": round(ck.delta_e_hex(z["hex"], target["hex"]), 1),
            "override": z["name"] in CULTURAL_OVERRIDE,
            "reason": reason,
            "alternates": [
                {"name": c["name"], "hex": c["hex"], "delta_e": round(de, 1)}
                for c, de in top
            ],
        })

    # 文学色名不在 zerosoul 里、但用户常说的
    extra = {
        "天青": "汝窑天青",
        "牙白": "牙白",
        "茶白": "茶白",
        "米白": "米白",
        "秋香": "秋香",
        "绛": "绛",
        "松花": "松花",
    }
    existing = {a["alias"] for a in aliases}
    for name, _ in extra.items():
        if name in existing or name in by_name:
            continue
        if name not in CULTURAL_OVERRIDE:
            continue
        target = by_name[CULTURAL_OVERRIDE[name][0]]
        aliases.append({
            "alias": name,
            "target": target["name"],
            "target_hex": target["hex"],
            "target_pinyin": target["pinyin"],
            "literary_hex": None,
            "literary_intro": "",
            "literary_family": "",
            "delta_e_to_literary": None,
            "override": True,
            "reason": CULTURAL_OVERRIDE[name][1],
            "alternates": [],
        })

    aliases.sort(key=lambda a: a["alias"])
    payload = {
        "meta": {
            "catalog_count": len(colors),
            "alias_count": len(aliases),
            "same_name_variant_count": len(same_name),
            "rule": "输出颜色必须是 526 色库中的 target_hex，禁止使用 literary_hex，禁止发明新 hex。",
            "note": "literary_hex 来自网络 161 色文学色卡，仅用于理解典故与提示用户『你说的石青在本色库叫群青』。",
        },
        "aliases": aliases,
        "same_name_variants": same_name,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"别名 {len(aliases)} 条，同名异色 {len(same_name)} 条 -> {OUT}")
    print("文化校正:")
    for a in aliases:
        if a["override"]:
            print(f"  {a['alias']:6s} -> {a['target']:6s} {a['target_hex']}  {a['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
