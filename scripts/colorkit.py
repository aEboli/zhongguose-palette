#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""色彩数学工具箱：sRGB / HSL / HSV / CIELAB / LCH / WCAG / APCA / CIEDE2000。

只用标准库，不依赖第三方包，便于在任何环境直接运行。
所有函数以 hex 字符串（"#rrggbb"）或 (r, g, b) 0-255 元组为输入。

设计取舍说明：
- 混色、求中间色、算距离一律走 LCH / Lab，不用 HSL。HSL 的 L 不是感知明度，
  在 HSL 里插值会掉进灰泥里（尤其黄蓝之间），Lab 才与人眼一致。
- 对比度以 WCAG 2.2 为准（法规基线），同时给出 APCA 近似值作为感知参考，
  因为 WCAG 公式对黄、橙、青偏乐观，对深色底偏悲观。
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------- 基础转换

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """"#f9f4dc" -> (249, 244, 220)。容忍缺省 # 与 3 位简写。"""
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"非法 hex 颜色值: {value!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    """(249, 244, 220) -> "#f9f4dc"，越界值自动夹紧。"""
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02x}" for c in rgb)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


# ---------------------------------------------------------------- HSL / HSV

def rgb_to_hsl(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """返回 (H 0-360, S 0-100, L 0-100)。"""
    r, g, b = (c / 255.0 for c in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    d = mx - mn
    if d == 0:
        return 0.0, 0.0, l * 100.0
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d) % 6.0
    elif mx == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    return h * 60.0, s * 100.0, l * 100.0


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    """(H 0-360, S 0-100, L 0-100) -> (r, g, b) 0-255。"""
    h = h % 360.0
    s, l = s / 100.0, l / 100.0
    c = (1.0 - abs(2.0 * l - 1.0)) * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = l - c / 2.0
    idx = int(h // 60.0) % 6
    table = [(c, x, 0.0), (x, c, 0.0), (0.0, c, x), (0.0, x, c), (x, 0.0, c), (c, 0.0, x)]
    r, g, b = table[idx]
    return tuple(int(round((v + m) * 255)) for v in (r, g, b))  # type: ignore[return-value]


def rgb_to_hsv(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """返回 (H 0-360, S 0-100, V 0-100)。"""
    r, g, b = (c / 255.0 for c in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = (((g - b) / d) % 6.0) * 60.0
    elif mx == g:
        h = ((b - r) / d + 2.0) * 60.0
    else:
        h = ((r - g) / d + 4.0) * 60.0
    s = 0.0 if mx == 0 else d / mx
    return h, s * 100.0, mx * 100.0


# ---------------------------------------------------------------- CIELAB / LCH

_D65 = (0.95047, 1.00000, 1.08883)


def _srgb_to_linear(c: float) -> float:
    """sRGB 反伽马（IEC 61966-2-1 分段函数）。"""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb_to_xyz(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c / 255.0) for c in rgb)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    return x, y, z


def xyz_to_rgb(xyz: tuple[float, float, float]) -> tuple[int, int, int]:
    x, y, z = xyz
    r = x * 3.2404542 + y * -1.5371385 + z * -0.4985314
    g = x * -0.9692660 + y * 1.8760108 + z * 0.0415560
    b = x * 0.0556434 + y * -0.2040259 + z * 1.0572252
    return tuple(int(round(_clamp(_linear_to_srgb(c)) * 255)) for c in (r, g, b))  # type: ignore[return-value]


def _f_lab(t: float) -> float:
    return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29


def _f_lab_inv(t: float) -> float:
    return t ** 3 if t ** 3 > 216 / 24389 else (108 / 841) * (t - 4 / 29)


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """返回 (L* 0-100, a*, b*)，D65 白点。"""
    x, y, z = rgb_to_xyz(rgb)
    fx, fy, fz = (_f_lab(v / w) for v, w in zip((x, y, z), _D65))
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def lab_to_rgb(lab: tuple[float, float, float]) -> tuple[int, int, int]:
    l, a, b = lab
    fy = (l + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    xyz = tuple(_f_lab_inv(f) * w for f, w in zip((fx, fy, fz), _D65))
    return xyz_to_rgb(xyz)  # type: ignore[arg-type]


def lab_to_lch(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    """(L*, a*, b*) -> (L 0-100, C 彩度, H 色相角 0-360)。"""
    l, a, b = lab
    c = math.hypot(a, b)
    h = math.degrees(math.atan2(b, a)) % 360.0
    return l, c, h


def lch_to_lab(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    l, c, h = lch
    rad = math.radians(h)
    return l, c * math.cos(rad), c * math.sin(rad)


def rgb_to_lch(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    return lab_to_lch(rgb_to_lab(rgb))


def lch_to_rgb(lch: tuple[float, float, float]) -> tuple[int, int, int]:
    return lab_to_rgb(lch_to_lab(lch))


def hex_to_lch(value: str) -> tuple[float, float, float]:
    return rgb_to_lch(hex_to_rgb(value))


# ---------------------------------------------------------------- 色相角运算

def hue_delta(h1: float, h2: float) -> float:
    """两个色相角的最短夹角，0-180。"""
    d = abs((h1 - h2) % 360.0)
    return 360.0 - d if d > 180.0 else d


def hue_mid(h1: float, h2: float) -> float:
    """沿最短弧取中点色相，避免跨 0 度时跑到对面去。"""
    d = ((h2 - h1 + 540.0) % 360.0) - 180.0
    return (h1 + d / 2.0) % 360.0


# ---------------------------------------------------------------- 对比度

def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.x 相对亮度 0-1。"""
    r, g, b = (_srgb_to_linear(c / 255.0) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str | tuple[int, int, int], b: str | tuple[int, int, int]) -> float:
    """WCAG 2.2 对比度，1.0-21.0。入参可为 hex 或 rgb 元组。"""
    ra = a if isinstance(a, tuple) else hex_to_rgb(a)
    rb = b if isinstance(b, tuple) else hex_to_rgb(b)
    la, lb = relative_luminance(ra), relative_luminance(rb)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def wcag_level(ratio: float, large_text: bool = False) -> str:
    """把对比度翻译成合规等级标签。"""
    if large_text:
        if ratio >= 4.5:
            return "AAA"
        if ratio >= 3.0:
            return "AA"
    else:
        if ratio >= 7.0:
            return "AAA"
        if ratio >= 4.5:
            return "AA"
        if ratio >= 3.0:
            return "AA-large"
    return "fail"


# APCA 0.1.9 常数（W3C Silver 草案）。此处为近似实现，仅作感知参考，
# 正式无障碍验收仍以 WCAG 2.2 的 contrast_ratio 为准。
_APCA = dict(
    trc=2.4, rco=0.2126729, gco=0.7151522, bco=0.0721750,
    norm_bg=0.56, norm_txt=0.57, rev_bg=0.65, rev_txt=0.62,
    blk_thrs=0.022, blk_clmp=1.414, scale=1.14, lo_offset=0.027, delta_min=0.0005,
)


def _apca_y(rgb: tuple[int, int, int]) -> float:
    r, g, b = ((c / 255.0) ** _APCA["trc"] for c in rgb)
    y = _APCA["rco"] * r + _APCA["gco"] * g + _APCA["bco"] * b
    if y < _APCA["blk_thrs"]:
        y += (_APCA["blk_thrs"] - y) ** _APCA["blk_clmp"]
    return y


def apca_lc(text: str | tuple[int, int, int], bg: str | tuple[int, int, int]) -> float:
    """APCA 感知对比 Lc，约 -108..108。绝对值 60 上下相当于正文可读。"""
    rt = text if isinstance(text, tuple) else hex_to_rgb(text)
    rb = bg if isinstance(bg, tuple) else hex_to_rgb(bg)
    yt, yb = _apca_y(rt), _apca_y(rb)
    if abs(yb - yt) < _APCA["delta_min"]:
        return 0.0
    if yb > yt:  # 浅底深字
        s = (yb ** _APCA["norm_bg"] - yt ** _APCA["norm_txt"]) * _APCA["scale"]
        return 0.0 if s < 0.035 else (s - _APCA["lo_offset"]) * 100.0
    s = (yb ** _APCA["rev_bg"] - yt ** _APCA["rev_txt"]) * _APCA["scale"]
    return 0.0 if s > -0.035 else (s + _APCA["lo_offset"]) * 100.0


# ---------------------------------------------------------------- 色差

def delta_e_2000(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIEDE2000 色差。约 <1 肉眼难辨，<8 属同一色，>25 明显不同色。"""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    kl = kc = kh = 1.0
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    cbar = (c1 + c2) / 2.0
    g = 0.5 * (1.0 - math.sqrt(cbar ** 7 / (cbar ** 7 + 25.0 ** 7))) if cbar > 0 else 0.0
    a1p, a2p = (1.0 + g) * a1, (1.0 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360.0 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360.0 if (a2p or b2) else 0.0
    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    else:
        dh = h2p - h1p
        dhp = dh - 360.0 if dh > 180.0 else dh + 360.0 if dh < -180.0 else dh
    dhp_term = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2.0)
    lbar = (l1 + l2) / 2.0
    cbarp = (c1p + c2p) / 2.0
    if c1p * c2p == 0:
        hbarp = h1p + h2p
    else:
        s = h1p + h2p
        hbarp = s / 2.0 if abs(h1p - h2p) <= 180.0 else (s + 360.0) / 2.0 if s < 360.0 else (s - 360.0) / 2.0
    t = (1.0 - 0.17 * math.cos(math.radians(hbarp - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hbarp))
         + 0.32 * math.cos(math.radians(3.0 * hbarp + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hbarp - 63.0)))
    dtheta = 30.0 * math.exp(-(((hbarp - 275.0) / 25.0) ** 2))
    rc = 2.0 * math.sqrt(cbarp ** 7 / (cbarp ** 7 + 25.0 ** 7)) if cbarp > 0 else 0.0
    sl = 1.0 + (0.015 * (lbar - 50.0) ** 2) / math.sqrt(20.0 + (lbar - 50.0) ** 2)
    sc = 1.0 + 0.045 * cbarp
    sh = 1.0 + 0.015 * cbarp * t
    rt = -math.sin(math.radians(2.0 * dtheta)) * rc
    return math.sqrt(
        (dlp / (kl * sl)) ** 2
        + (dcp / (kc * sc)) ** 2
        + (dhp_term / (kh * sh)) ** 2
        + rt * (dcp / (kc * sc)) * (dhp_term / (kh * sh))
    )


def delta_e_hex(a: str, b: str) -> float:
    return delta_e_2000(rgb_to_lab(hex_to_rgb(a)), rgb_to_lab(hex_to_rgb(b)))


# ---------------------------------------------------------------- 混色与调色

def _xyz_to_linear_rgb(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    """XYZ -> 线性 sRGB，不做裁剪，用于精确判定色域边界。"""
    x, y, z = xyz
    return (
        x * 3.2404542 + y * -1.5371385 + z * -0.4985314,
        x * -0.9692660 + y * 1.8760108 + z * 0.0415560,
        x * 0.0556434 + y * -0.2040259 + z * 1.0572252,
    )


def in_gamut(lch: tuple[float, float, float], eps: float = 1e-4) -> bool:
    """判断 LCH 坐标是否落在 sRGB 色域内。

    直接检查未裁剪的线性 RGB 分量是否都在 [0,1]，这是精确判据。
    早先用"转回来再比误差"的写法会漏判：L=100 配任何彩度都出域，
    但往返误差恰好压在容差边缘，于是留下了不存在的彩度。
    """
    l, a, b = lch_to_lab(lch)
    fy = (l + 16.0) / 116.0
    xyz = tuple(_f_lab_inv(f) * w for f, w in
                zip((fy + a / 500.0, fy, fy - b / 200.0), _D65))
    return all(-eps <= c <= 1.0 + eps for c in _xyz_to_linear_rgb(xyz))  # type: ignore[arg-type]


def fit_gamut(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    """保明度、保色相，二分降彩度直到落回 sRGB 色域。

    比直接裁 RGB 通道好：硬裁会同时改变明度和色相（提亮乳白时会串成偏绿的白），
    降彩度只损失鲜艳度，视觉上仍是同一个颜色。
    """
    l, c, h = _clamp(lch[0], 0.0, 100.0), max(0.0, lch[1]), lch[2] % 360.0
    if in_gamut((l, c, h)):
        return l, c, h
    lo, hi = 0.0, c
    for _ in range(24):
        mid = (lo + hi) / 2.0
        if in_gamut((l, mid, h)):
            lo = mid
        else:
            hi = mid
    return l, lo, h


def mix_lch(a: str, b: str, ratio: float = 0.5, chroma_pull: float = 0.0) -> str:
    """在 LCH 空间沿最短色相弧混合两色，返回 hex。

    适用于同族或邻近色之间的渐变、层级派生——沿色相弧走能保住彩度，不发灰。
    补色（色相相距 >150°）请改用 mix_lab：绕弧会经过第三种色相，
    红配青会混出紫色，那不是这两色调出来的颜色。
    ratio=0 得 a，1 得 b；chroma_pull 为负可压彩度，让过渡色更像"调出来的"。
    """
    l1, c1, h1 = hex_to_lch(a)
    l2, c2, h2 = hex_to_lch(b)
    l = l1 + (l2 - l1) * ratio
    c = max(0.0, (c1 + (c2 - c1) * ratio) * (1.0 + chroma_pull))
    h = (h1 + (((h2 - h1 + 540.0) % 360.0) - 180.0) * ratio) % 360.0
    return rgb_to_hex(lch_to_rgb(fit_gamut((l, c, h))))


def mix_lab(a: str, b: str, ratio: float = 0.5) -> str:
    """在 Lab 直线上混合两色，返回 hex。

    这是求"居中调和色"的正解：一对补色在 Lab 上取中点会自然经过近中性灰，
    正是两色之间真实存在的过渡色（水墨里的"和色"、织物里的"间色"同理）。
    """
    l1, a1, b1 = rgb_to_lab(hex_to_rgb(a))
    l2, a2, b2 = rgb_to_lab(hex_to_rgb(b))
    lab = (l1 + (l2 - l1) * ratio, a1 + (a2 - a1) * ratio, b1 + (b2 - b1) * ratio)
    return rgb_to_hex(lab_to_rgb(lab))


def bridge(a: str, b: str, chroma_pull: float = -0.35) -> str:
    """求两色的调和过渡色：按色相距离自动选择 LCH 弧线或 Lab 直线。"""
    _, _, h1 = hex_to_lch(a)
    _, _, h2 = hex_to_lch(b)
    if hue_delta(h1, h2) > 150.0:
        return mix_lab(a, b, 0.5)
    return mix_lch(a, b, 0.5, chroma_pull)


def adjust(value: str, dl: float = 0.0, dc: float = 0.0, dh: float = 0.0) -> str:
    """在 LCH 上平移明度/彩度/色相，越域时保明度保色相地降彩度。"""
    l, c, h = hex_to_lch(value)
    return rgb_to_hex(lch_to_rgb(fit_gamut((l + dl, c + dc, h + dh))))


def warmth(rgb: tuple[int, int, int]) -> float:
    """冷暖倾向 -1（最冷）到 +1（最暖），已按彩度衰减，灰色趋近 0。

    暖轴取 LCH 色相 55°（橙黄），冷轴 235°（青蓝），符合传统"暖色向阳、
    冷色向阴"的直觉，也与 Itten 冷暖对比的轴向一致。
    """
    l, c, h = rgb_to_lch(rgb)
    return math.cos(math.radians(h - 55.0)) * min(1.0, c / 60.0)


def simulate_cvd(rgb: tuple[int, int, int], kind: str = "deuteranopia") -> tuple[int, int, int]:
    """色盲模拟（Brettel/Viénot 线性近似），用于校验点缀色是否仍可辨。"""
    m = {
        "protanopia": ((0.152, 1.053, -0.205), (0.115, 0.786, 0.099), (-0.004, -0.048, 1.052)),
        "deuteranopia": ((0.367, 0.861, -0.228), (0.280, 0.673, 0.047), (-0.012, 0.043, 0.969)),
        "tritanopia": ((1.256, -0.077, -0.179), (-0.078, 0.931, 0.148), (0.005, 0.691, 0.304)),
    }[kind]
    r, g, b = (_srgb_to_linear(c / 255.0) for c in rgb)
    out = [row[0] * r + row[1] * g + row[2] * b for row in m]
    return tuple(int(round(_clamp(_linear_to_srgb(v)) * 255)) for v in out)  # type: ignore[return-value]
