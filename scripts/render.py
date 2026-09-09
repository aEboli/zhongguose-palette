#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端里把配色画出来。

最难讲清的那条规矩——三色不等权——不用文字解释。按建议铺色面积等比画一条
色条，点缀实测只占 2~8%，在 54 字符宽的条上就是一两个字符。用户看见那一小格，
就再不会要求「三个色平分」。

三档降级：24 位真彩 -> 256 色 -> 无色表格。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RESET = "\033[0m"


def color_mode() -> str:
    """判定顺序：NO_COLOR 优先于一切，然后看是不是终端。

    不看 COLORTERM——它在很多终端里缺失，据它降级会让本来能显示真彩的环境
    掉到 256 色。
    """
    if os.environ.get("NO_COLOR"):
        return "none"
    if os.environ.get("FORCE_COLOR"):
        return "truecolor"
    if not sys.stdout.isatty():
        return "none"
    term = os.environ.get("TERM", "")
    if term in ("dumb", ""):
        return "none"
    if "256" in term and "truecolor" not in term:
        return "256"
    return "truecolor"


def _rgb_to_256(r: int, g: int, b: int) -> int:
    if abs(r - g) < 12 and abs(g - b) < 12:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + round((r - 8) / 247 * 23)
    return 16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)


def bg(hex_value: str, mode: str | None = None) -> str:
    mode = mode or color_mode()
    h = hex_value.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if mode == "truecolor":
        return f"\033[48;2;{r};{g};{b}m"
    if mode == "256":
        return f"\033[48;5;{_rgb_to_256(r, g, b)}m"
    return ""


def fg(hex_value: str, mode: str | None = None) -> str:
    mode = mode or color_mode()
    h = hex_value.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if mode == "truecolor":
        return f"\033[38;2;{r};{g};{b}m"
    if mode == "256":
        return f"\033[38;5;{_rgb_to_256(r, g, b)}m"
    return ""


def area_bar(entries: list[tuple[str, str, float]], width: int = 54,
             mode: str | None = None) -> str:
    """按面积等比画一条色条。entries = [(标签, hex, 百分比), ...]

    宽度必须来自真实的建议铺色面积，不能硬编码 6/3/1——那等于在视觉上
    违反「面积 ≠ 视觉重量」这条自己立的规矩。
    """
    mode = mode or color_mode()
    if mode == "none":
        return "\n".join(f"  {label:4s} {hexv}  约 {pct:.0f}%" for label, hexv, pct in entries)
    total = sum(max(p, 0.0) for _, _, p in entries) or 1.0
    cells = []
    for i, (_, hexv, pct) in enumerate(entries):
        n = max(1, round(width * max(pct, 0.0) / total))
        cells.append((hexv, n))
    # 修正取整误差，从最宽的那块里补/扣
    diff = width - sum(n for _, n in cells)
    if diff and cells:
        idx = max(range(len(cells)), key=lambda i: cells[i][1])
        cells[idx] = (cells[idx][0], max(1, cells[idx][1] + diff))
    bar = "".join(bg(h, mode) + " " * n for h, n in cells) + RESET
    legend = "  ".join(f"{fg(h, mode)}■{RESET} {label} {h} {pct:.0f}%"
                       for (label, h, pct) in entries)
    return bar + "\n" + legend


def swatch(name: str, hex_value: str, note: str = "", mode: str | None = None) -> str:
    mode = mode or color_mode()
    block = bg(hex_value, mode) + "    " + RESET if mode != "none" else "[    ]"
    tail = f"  {note}" if note else ""
    return f"{block} {name:8s} {hex_value}{tail}"


def ladder(colors: list[tuple[str, str]], mode: str | None = None) -> str:
    """一排色阶。用于 ladder / sequential 输出。"""
    mode = mode or color_mode()
    if mode == "none":
        return "  " + "  ".join(f"{n} {h}" for n, h in colors)
    top = "".join(bg(h, mode) + "      " + RESET for _, h in colors)
    names = "".join(f"{n[:6]:<6s}" for n, _ in colors)
    return top + "\n" + names


if __name__ == "__main__":
    print("mode:", color_mode())
    print(area_bar([("场", "#f7f4ed", 80.1), ("面", "#495c69", 16.0), ("眼", "#f43e06", 3.9)]))
    print()
    print(swatch("鱼肚白", "#f7f4ed", "页面背景"))
