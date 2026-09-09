#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""白话 -> 内部轴的解析器。

用户不该被要求先知道「故宫 / 青花 / 雅 / 空灵 / --media ui」。他会说
「茶叶小店安静一点」。本模块把那句话翻成 engine 认得的参数。

设计要点：
- 映射规则全在 references/vernacular.json，不在代码里。改映射不改代码。
- 否定只做同轴减分，不硬置零：「喜庆但不要太艳」两者相减，不是互斥。
- 只输出 engine.SCENES 里真实存在的场景，否则 CLI 会 invalid choice。
- 歧义判定是可计算的（响极 vs 静极），不靠模型感觉。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
VERNACULAR_PATH = ROOT / "references" / "vernacular.json"

_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")


@dataclass
class Intent:
    """一句白话的解析结果。"""
    text: str
    media: str | None = None
    mood: str | None = None
    scene: str | None = None
    dark: bool = False
    seed: str | None = None
    n: int = 2
    scores: dict = field(default_factory=dict)
    hits: list = field(default_factory=list)
    echo: list = field(default_factory=list)
    ambiguity: str | None = None
    conflict: str | None = None
    defaulted: list = field(default_factory=list)
    signal_axes: int = 0
    alt_scenes: list = field(default_factory=list)
    explicit_light: bool = False
    unheard: list = field(default_factory=list)

    def to_cli(self) -> list[str]:
        """转成 palette.py generate 的参数。"""
        out: list[str] = []
        if self.scene:
            out += ["--scene", self.scene]
        if self.mood:
            out += ["--mood", self.mood]
        if self.media:
            out += ["--media", self.media]
        if self.dark:
            out += ["--dark"]
        if self.seed:
            out += ["--seed", self.seed]
        out += ["--n", str(self.n)]
        return out

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "media": self.media,
            "mood": self.mood,
            "scene": self.scene,
            "dark": self.dark,
            "seed": self.seed,
            "n": self.n,
            "signal_axes": self.signal_axes,
            "alt_scenes": self.alt_scenes,
            "unheard": self.unheard,
            "echo": self.echo,
            "hits": self.hits,
            "scores": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in self.scores.items()},
            "ambiguity": self.ambiguity,
            "conflict": self.conflict,
            "defaulted": self.defaulted,
            "cli": self.to_cli(),
        }


class Vernacular:
    def __init__(self, path: Path = VERNACULAR_PATH):
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.w = self.data["weights"]
        self.neg = self.data["negation"]
        self.poles = self.data["poles"]
        self.defaults = self.data["defaults"]
        self.out = self.data["out"]
        self.banned = self.data["banned_terms"]
        # 展开成 (轴, 值, 线索词, 权重)，长词优先以免「青」抢掉「青花」
        self.cues: list[tuple[str, str, str, float]] = []
        for axis, values in self.data["in"].items():
            for value, tiers in values.items():
                if isinstance(tiers, list):  # dark / light 是扁的
                    continue
                for tier, words in tiers.items():
                    weight = self.w.get(tier, 1.0)
                    for word in words:
                        self.cues.append((axis, value, word, weight))
        # dark / light 是 {tier: [...]} 而非 {value: {tier: [...]}}
        for axis in ("dark", "light"):
            spec = self.data["in"].get(axis)
            if isinstance(spec, dict):
                for tier, words in spec.items():
                    if not isinstance(words, list):
                        continue
                    weight = self.w.get(tier, 1.0)
                    for word in words:
                        self.cues.append((axis, axis, word, weight))
        self.cues.sort(key=lambda x: -len(x[2]))

    # ---------------------------------------------------------------- 匹配

    def _negated(self, text: str, pos: int) -> bool:
        """线索词前 window 个字符内出现否定标记，就算被否定。"""
        window = int(self.neg.get("window", 5))
        left = text[max(0, pos - window):pos]
        return any(m in left for m in self.neg["markers"])

    def _opposite_pole(self, mood: str) -> str | None:
        """响的对极是静，静的对极是响。用于否定时的权重转移。"""
        if mood in self.poles["loud"]:
            return "quiet"
        if mood in self.poles["quiet"]:
            return "loud"
        return None

    def score(self, text: str) -> tuple[dict, list]:
        """按轴累加线索词权重。

        长词吃掉自己的字符span：「素雅」命中后，「素」和「雅」不能在同一片
        字符上再各算一次，否则 3.0 会滚成 5.4，所有含长词的句子分数虚高，
        歧义门限也就永远踩不准。cues 已按长度倒序，所以先到先占。
        """
        scores: dict[str, dict[str, float]] = {}
        hits: list[dict] = []
        transfer = float(self.neg.get("opposite_pole_transfer", 0.0))
        taken: dict[str, set] = {}
        for axis, value, word, weight in self.cues:
            span = taken.setdefault(axis, set())
            start = 0
            while True:
                pos = text.find(word, start)
                if pos < 0:
                    break
                start = pos + 1
                cells = set(range(pos, pos + len(word)))
                if cells & span:
                    continue  # 这片字符已被同轴更长的线索词占了
                span |= cells
                negated = self._negated(text, pos)
                bucket = scores.setdefault(axis, {})
                bucket[value] = bucket.get(value, 0.0) + (-weight if negated else weight)
                hits.append({"axis": axis, "value": value, "cue": word,
                             "w": -weight if negated else weight, "negated": negated})
                # 「别太艳」不只是把艳减掉，它还是一个朝素净去的指令。
                # 只减分的话 婚礼(2.0)-艳(1.2)=0.8 仍会让艳胜出，用户的「别」白说了。
                if negated and axis == "mood" and transfer > 0:
                    pole = self._opposite_pole(value)
                    if pole:
                        for m in self.poles[pole]:
                            bucket[m] = bucket.get(m, 0.0) + weight * transfer
                        hits.append({"axis": "mood", "value": "->" + pole, "cue": word,
                                     "w": round(weight * transfer, 2), "negated": False,
                                     "reason": "否定转对极"})
        return scores, hits

    # ---------------------------------------------------------------- 解析

    def resolve(self, text: str, catalog=None) -> Intent:
        text = (text or "").strip()
        it = Intent(text=text)
        scores, hits = self.score(text)
        it.scores, it.hits = scores, hits

        def top(axis: str) -> tuple[str | None, float]:
            bucket = {k: v for k, v in scores.get(axis, {}).items() if v > 0}
            if not bucket:
                return None, 0.0
            k = max(bucket, key=lambda x: bucket[x])
            return k, bucket[k]

        media, media_s = top("media")
        mood, mood_s = top("mood")
        scene, scene_s = top("scene")
        dark_s = max(scores.get("dark", {}).get("dark", 0.0), 0.0)
        light_s = max(scores.get("light", {}).get("light", 0.0), 0.0)

        it.signal_axes = sum(1 for s in (media_s, mood_s, scene_s, max(dark_s, light_s)) if s > 0)

        # 场景优先于氛围（场景自带 mood）。并列的其他场景留着做多方向。
        if scene:
            bucket = {k: v for k, v in scores.get("scene", {}).items() if v > 0}
            it.alt_scenes = [k for k in sorted(bucket, key=lambda x: -bucket[x])
                             if k != scene and bucket[k] >= scene_s * 0.6][:2]
        it.scene = scene
        it.mood = mood
        it.media = media
        it.dark = dark_s > light_s and dark_s > 0
        it.explicit_light = light_s > 0 and light_s >= dark_s

        # 种子色：库内色名 / 别名 / hex。必须真解析得到，不许静默漂走。
        if catalog is not None:
            m = _HEX_RE.search(text)
            if m:
                it.seed = m.group(0)
            else:
                found = None
                for name in sorted(list(catalog.by_name) + list(catalog.aliases), key=len, reverse=True):
                    if len(name) >= 2 and name in text and not self._negated(text, text.find(name)):
                        found = name
                        break
                it.seed = found

        # 缺省
        if not it.media:
            it.media = self.defaults["media"]
            it.defaulted.append("media")
        if not it.mood and not it.scene:
            if it.dark:
                it.scene = self.defaults["dark_scene"]
                it.mood = self.defaults["dark_mood"]
                it.defaulted += ["scene", "mood"]
            else:
                it.mood = self.defaults["mood"]
                it.defaulted.append("mood")
        it.n = int(self.defaults.get("n", 2))

        it.ambiguity = self._ambiguity(scores)
        it.echo = self._echo(it)
        it.unheard = self._unheard(text, hits, it)
        return it

    def _unheard(self, text: str, hits: list, it: Intent) -> list[str]:
        """挑出用户说了、但一个轴都没命中的实词。

        没有这一项就会静默失败：用户说「要有仙气」，我们照缺省给出一套合理但
        与他意图无关的方案，他看不出是自己没说清还是技能没听懂。宁可说一句
        「仙气我没接住」，也不要假装听懂了。
        """
        matched: set = set()
        # 记下每个位置是被多长的线索词命中的。单字线索往往是吃掉了复合词的头
        # （「茶」命中于「茶叶小店」），多字线索则是一个独立的词。
        cue_len: dict = {}

        def mark(s: str) -> None:
            start = 0
            while True:
                pos = text.find(s, start)
                if pos < 0:
                    break
                for i in range(pos, pos + len(s)):
                    matched.add(i)
                    cue_len[i] = max(cue_len.get(i, 0), len(s))
                start = pos + 1

        for h in hits:
            mark(h.get("cue", ""))
        if it.seed:
            mark(it.seed)
        # 连续的未命中中文片段，长度 ≥2 才算"实词"，并滤掉纯功能词
        # 中性词是在确认「该用这个技能」，不选轴，也不算没听懂
        for term in self.data.get("neutral_terms", []):
            if term in text:
                mark(term)
        FILLER = set("的了是要做个想给我你他她它们这那有和跟与就也很再一点些吧啊呢吗把被让对从在上下里外前后能会可以帮设计颜色出来看用种样比较觉得需要希望忙")
        chunks: list[tuple[int, str]] = []
        cur, cur_start = [], 0
        for i, ch in enumerate(text):
            if i in matched or not ('一' <= ch <= '鿿'):
                if cur:
                    chunks.append((cur_start, "".join(cur)))
                    cur = []
            else:
                if not cur:
                    cur_start = i
                cur.append(ch)
        if cur:
            chunks.append((cur_start, "".join(cur)))
        out = []
        for start, c in chunks:
            # 先把两端的功能词剥掉，再判邻接。对原始片段判会误杀：
            # 「要有仙气的网站」里整段「要有仙气的」的结尾紧贴 网站，
            # 但真正的实词 仙气 与命中处之间隔着一个「的」，不是残渣。
            lo, hi = 0, len(c)
            while lo < hi and c[lo] in FILLER:
                lo += 1
            while hi > lo and c[hi - 1] in FILLER:
                hi -= 1
            core = c[lo:hi]
            if len(core) < 2:
                continue
            abs_lo, abs_hi = start + lo, start + hi
            # 只有紧贴「单字线索」的才算复合词残渣：「茶叶小店」里 茶 命中后
            # 剩下的「叶小店」是残渣；而「赛博朋克感觉」里 感觉 是独立的二字词，
            # 紧贴它的 赛博朋克 是真没听懂的词，不能一起吞掉。
            if cue_len.get(abs_lo - 1) == 1 or cue_len.get(abs_hi) == 1:
                continue
            out.append("".join(ch for ch in core if ch not in FILLER))
        return [x for x in out if len(x) >= 2][:3]

    def _ambiguity(self, scores: dict) -> str | None:
        """响 vs 静同时被强烈要求 —— 这是真歧义，并列展示解决不了。"""
        mood_scores = {k: v for k, v in scores.get("mood", {}).items() if v > 0}
        if not mood_scores:
            return None
        loud = max((mood_scores.get(m, 0.0) for m in self.poles["loud"]), default=0.0)
        quiet = max((mood_scores.get(m, 0.0) for m in self.poles["quiet"]), default=0.0)
        if loud >= 2.0 and quiet >= 2.0:
            hi, lo = max(loud, quiet), min(loud, quiet)
            if hi > 0 and (hi - lo) / hi < 0.15:
                return "响/静"
        return None

    # ---------------------------------------------------------------- 微调

    def tweak(self, text: str, current_mood: str | None = None,
              current_dark: bool = False) -> dict:
        """微调语境的解析。词义与首轮相反，所以走独立词表。

        首轮「素净一点」是要素净；改稿时「太素了」是抱怨，意思是往艳走。
        复用 in.mood 会把抱怨读成需求，用户说了半天颜色一点没变。
        """
        cfg = self.data.get("tweak", {})
        hit = lambda key: any(w in text for w in cfg.get(key, []))  # noqa: E731

        out: dict = {"mood": current_mood, "dark": current_dark, "actions": [],
                     "pin": {}, "pin_hint": [], "note": []}
        louder, quieter = hit("louder"), hit("quieter")
        if louder != quieter:  # 同时说了两个方向就当没说，让用户再讲一句
            table = cfg.get("louder_map" if louder else "quieter_map", {})
            cur = current_mood or ("雅" if louder else "艳")
            nxt = table.get(cur)
            if nxt and nxt != cur:
                out["mood"] = nxt
                out["actions"].append(("素艳", f"{cur} -> {nxt}"))
            elif nxt == cur:
                out["note"].append(f"已经在{'最艳' if louder else '最素'}那一档了，再走就出中国色的语汇了")
        elif louder and quieter:
            out["note"].append("同一句里既要更艳又要更素，我没法两边都走——说一句到底哪个方向")

        if hit("cooler"):
            out["mood"] = "清冷"
            out["actions"].append(("冷暖", "-> 清冷"))
        elif hit("warmer"):
            out["actions"].append(("冷暖", "底换暖白（汉白玉/乳白/粉白），避开月白"))

        if hit("darker"):
            out["dark"] = True
            # 不带场景直接转暗，深底会落到库内任意深色上，配出灰配紫这种东西。
            # 漆器是库内唯一真正以深底为场的场景，转暗时默认落在它上面。
            out["scene_hint"] = self.defaults.get("dark_scene")
            out["actions"].append(("明暗", f"深底做场（走{out['scene_hint']}那套深底语汇），不是把浅色方案反相"))
        elif hit("lighter"):
            out["dark"] = False
            out["actions"].append(("明暗", "回到浅底"))

        if hit("less_accent"):
            out["actions"].append(("面积", "点缀压到下限，只在按钮和印章上"))
        if hit("more_gold"):
            golds = cfg.get("gold_accents", [])
            if golds:
                out["pin"]["accent"] = golds[0]
            out["actions"].append(("点缀", f"钉成金（{golds[0] if golds else '甘草黄'}），只走线不填面"))
            if (out["mood"] or current_mood) in ("雅", "空灵", "清冷"):
                out["mood"] = "艳"
                out["actions"].append(("素艳轴", "为了给金升到艳"))
                out["note"].append("素净档位里几乎没有真金，为了给你金整套调艳了一档——这点必须告诉用户，不能暗中换")
        if hit("keep_others"):
            out["pin_hint"].append("把没被点到的角色钉住")
            out["actions"].append(("钉住", "只改被点到的那一维，其余用 --keep 钉死"))
        if hit("restart"):
            out["actions"].append(("重来", "换整个方向，不做微调；问一句偏素还是偏热闹"))
        return out

    def _echo(self, it: Intent) -> list[str]:
        """回读给用户听的一行白话。不含任何内部术语。"""
        parts = []
        media_words = {"ui": "网页界面", "poster": "海报印刷", "fashion": "服装", "interior": "空间"}
        if it.media:
            parts.append(media_words.get(it.media, it.media))
        if it.scene:
            parts.append(self.out["scene"].get(it.scene, it.scene))
        elif it.mood:
            parts.append(self.out["mood"].get(it.mood, it.mood))
        if it.mood and it.scene:
            parts.append(self.out["mood"].get(it.mood, it.mood))
        # 只在用户真的表态过明暗时才回读这一项。有些场景本身就是深底的
        # （补服的石青地、漆器的黑漆地），dark 旗标没开也会产出深色方案——
        # 这时候咬定「浅色底」就是在向用户描述一个与交付物不符的东西。
        if it.dark:
            parts.append("深色底")
        elif it.explicit_light:
            parts.append("浅色底")
        return parts

    # ---------------------------------------------------------------- 输出净化

    def check_plain(self, text: str, allow: tuple[str, ...] = ()) -> list[str]:
        """返回 text 里命中的禁用术语。用户先说过的词可以回声，传进 allow。"""
        return [t for t in self.banned if t in text and t not in allow]


def resolve(text: str, catalog=None, path: Path = VERNACULAR_PATH) -> Intent:
    return Vernacular(path).resolve(text, catalog=catalog)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python vernacular.py \"用户的原话\"")
        return 2
    try:
        from engine import Catalog
        cat = Catalog()
    except Exception:
        cat = None
    it = resolve(" ".join(sys.argv[1:]), catalog=cat)
    print(json.dumps(it.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
