#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端里把配色画出来。

最难讲清的那条规矩——三色不等权——不用文字解释。按建议铺色面积等比画一条
色条，点缀实测只占 2~8%，在 54 字符宽的条上就是一两个字符。用户看见那一小格，
就再不会要求「三个色平分」。

两条正交的开关，不要绑在一起：
- color_mode() 只供 bg()/fg()：要不要发 ANSI 转义（truecolor / 256 / none）。
- bar_mode() 只回答色条怎么画（ANSI 背景 vs Unicode 方块），永不空白。
Claude Code 的工具输出进的是模型上下文，管道里发 ANSI 只会变成转义垃圾；
那种环境下画 █▓▒，模型才能原样复述给用户看。
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import colorkit as ck  # noqa: E402

RESET = "\033[0m"

# 块间不加 ▌/│：分隔符会吃掉 1 格宽度，点缀只占 2 格时比例直接被破坏。
# 用三级密度区分相邻块。
_BLOCKS = ("█", "▓", "▒")
# Windows 遗留代码页（cp936 等）编不出方块；技能文档通篇在教 PYTHONUTF8，
# 但写出前仍要能退到 ASCII，避免 UnicodeEncodeError 把整次 ask 打崩。
_BLOCKS_ASCII = ("#", "+", "-")

# xterm 256 的 6³ 立方级阶不是 0–255 等分，round(x/255*5) 会把 128 推到错误的格子。
_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def _xterm_256_cells() -> tuple[tuple[int, tuple[float, float, float]], ...]:
    """预建 240 格（16–231 立方 + 232–255 灰阶）的 Lab，供最近邻查询。"""
    cells = []
    idx = 16
    for r in _CUBE_LEVELS:
        for g in _CUBE_LEVELS:
            for b in _CUBE_LEVELS:
                cells.append((idx, ck.rgb_to_lab((r, g, b))))
                idx += 1
    for i in range(24):
        v = 8 + i * 10
        cells.append((232 + i, ck.rgb_to_lab((v, v, v))))
    return tuple(cells)


_XTERM_256 = _xterm_256_cells()


def color_mode() -> str:
    """判定要不要发 ANSI。面积怎么表达不归这里管。

    NO_COLOR 仍第一优先（selftest 全带 NO_COLOR=1，不会冒转义）。
    FORCE_COLOR=0 只表示「不强制」，不是再开一档 NO_COLOR。
    """
    if os.environ.get("NO_COLOR"):
        return "none"
    fc = os.environ.get("FORCE_COLOR")
    if fc is not None and fc != "" and fc != "0":
        return "truecolor"
    if not sys.stdout.isatty():
        return "none"
    colorterm = os.environ.get("COLORTERM", "").lower()
    if "truecolor" in colorterm or "24bit" in colorterm:
        return "truecolor"
    term = os.environ.get("TERM", "")
    # direct/24bit 必须排在「含 256」之前，否则 xterm-256color-direct 会被误降。
    if "direct" in term or "24bit" in term:
        return "truecolor"
    if term == "dumb":
        return "none"
    if "256" in term:
        return "256"
    if not term:
        # 空 TERM 只在非 Windows 上意味着「没有终端」。cmd.exe 的 TERM 本来就是空的。
        if os.name == "nt":
            if (os.environ.get("WT_SESSION")
                    or os.environ.get("ConEmuANSI")
                    or os.environ.get("TERM_PROGRAM")):
                return "truecolor"
            # ANSICON 只做 16 色仿真，不要把它抬成 truecolor。
            if os.environ.get("ANSICON"):
                return "256"
            return "truecolor" if _win_vt_ok() else "none"
        return "none"
    return "truecolor"


@functools.lru_cache(maxsize=1)
def _win_vt_ok() -> bool:
    """探一次 Windows VT。SetConsoleMode 有副作用，且每条 bg()/fg() 都会问 color_mode。

    仅 isatty 时才探：管道下连控制台都不碰。失败一律当不能发转义。
    """
    try:
        if not sys.stdout.isatty():
            return False
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def bar_mode() -> str:
    """色条怎么画。不发转义 ≠ 不表达面积。"""
    m = color_mode()
    return m if m in ("truecolor", "256") else "block"


@functools.lru_cache(maxsize=1024)
def _rgb_to_256(r: int, g: int, b: int) -> int:
    lab = ck.rgb_to_lab((r, g, b))
    best_i, best_d = 16, 1e9
    for idx, cell_lab in _XTERM_256:
        d = ck.delta_e_2000(lab, cell_lab)
        if d < best_d:
            best_d, best_i = d, idx
            if d == 0.0:
                break
    return best_i


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


def _blocks() -> tuple[str, str, str]:
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "".join(_BLOCKS).encode(enc)
        return _BLOCKS
    except (LookupError, UnicodeEncodeError, TypeError):
        return _BLOCKS_ASCII


def area_bar(entries: list[tuple[str, str, float]], width: int = 54,
             mode: str | None = None) -> str:
    """按面积等比画一条色条。entries = [(标签, hex, 百分比), ...]

    宽度必须来自真实的建议铺色面积，不能硬编码 6/3/1——那等于在视觉上
    违反「面积 ≠ 视觉重量」这条自己立的规矩。

    legend 只留角色与方块的对应。hex 与百分比的真源是 palette.py 落位那三行，
    这里再写一遍会变成两套「约 78%」。
    """
    mode = mode or bar_mode()
    total = sum(max(p, 0.0) for _, _, p in entries) or 1.0
    cells = []
    for _, hexv, pct in entries:
        n = max(1, round(width * max(pct, 0.0) / total))
        cells.append((hexv, n))
    # 修正取整误差，从最宽的那块里补/扣
    diff = width - sum(n for _, n in cells)
    if diff and cells:
        idx = max(range(len(cells)), key=lambda i: cells[i][1])
        cells[idx] = (cells[idx][0], max(1, cells[idx][1] + diff))
    if mode in ("truecolor", "256"):
        bar = "".join(bg(h, mode) + " " * n for h, n in cells) + RESET
        # 浅底用前景 ■ 在浅色主题上接近 1.01:1，改成背景铺的空格块才看得见。
        legend = "  ".join(
            f"{bg(hexv, mode)}   {RESET} {label}" for label, hexv, _pct in entries
        )
        return bar + "\n" + legend
    glyphs = _blocks()
    bar = "".join(glyphs[i % 3] * n for i, (_, n) in enumerate(cells))
    legend = "  ".join(
        f"{glyphs[i % 3]} {label}" for i, (label, _h, _p) in enumerate(entries)
    )
    return bar + "\n" + legend


if __name__ == "__main__":
    print("color_mode:", color_mode(), "bar_mode:", bar_mode())
    print(area_bar([("底", "#f7f4ed", 78), ("块", "#495c69", 19), ("点", "#f43e06", 3)]))
