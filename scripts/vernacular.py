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
MOTIFS_PATH = ROOT / "references" / "motifs.json"

# 季节线索。用错季节是纹样上最容易被识破的错（冬天的页面画荷花），
# 而现有词表里几乎没有季节——「秋天」「夏天」原本都报「没接住」。
SEASON_CUES = {
    "春": ["春天", "春季", "初春", "早春", "开春", "阳春", "春日"],
    "夏": ["夏天", "夏季", "初夏", "盛夏", "仲夏", "夏日", "消暑"],
    "秋": ["秋天", "秋季", "初秋", "深秋", "金秋", "秋日", "重阳"],
    "冬": ["冬天", "冬季", "初冬", "深冬", "隆冬", "冬日", "岁末", "年末"],
}

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
    # 纹样是独立的一轴。它与 scene 不互斥也不冲突：「梅花点缀的网站」应该同时
    # 得到 scene=江南（一套合理配色）和 motif=折枝梅（一个点缀），两者互补。
    # 把纹样词当成场景选择器是这条路最容易犯的错——纹样就变成了配比色。
    season: str | None = None
    motifs: list = field(default_factory=list)
    motif_notes: list = field(default_factory=list)

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
            "motifs": [{"id": m["id"], "name": m["name"],
                        "borrows": m["borrows_token"], "ink_pct": m.get("ink_pct"),
                        "placement": m["placement"]} for m in self.motifs],
            "motif_notes": self.motif_notes,
            "season": self.season,
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
        self._motifs = None
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
        it.season = self.season_of(text)
        it.motifs, it.motif_notes, heard_motif = self.match_motifs(
            text, scene=it.scene, season=it.season, catalog=catalog)
        it.echo = self._echo(it)
        for name, spec in self.match_sets(text):
            members = [m["name"] for m in self._load_motifs()["motifs"]
                       if m["id"] in (spec.get("members") or [])]
            it.motif_notes.append(f"「{name}」是成套语汇（{'、'.join(members)}）。{spec.get('rule','')}")
        for item in self.taboo_check(text):
            it.motif_notes.append(f"{item['what']}不作普通标记：{item['why']}。改法：{item['instead']}")
        it.unheard = self._unheard(text, hits, it, heard_motif)
        return it

    def _unheard(self, text: str, hits: list, it: Intent,
                 heard_motif: list | None = None) -> list[str]:
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
        # 纹样与季节也是听懂了的——它们走独立轴，不在 hits 里，
        # 不标记的话「荷花」会既命中纹样又被报成没接住，自相矛盾。
        # 用命中过的别名（过滤前），不是留用的纹样：被场景挡掉的那个词
        # 已经在 motif_notes 里解释过了，再报一次没接住是同一个矛盾换了方向。
        for al in (heard_motif or []):
            mark(al)
        # 季节只在真起了作用时才算听懂。它现在只驱动纹样的季节提醒，
        # 没纹样就什么都不改——那种情况下报「没接住秋天」是对的，
        # 因为用户确实说了秋天而我们确实没拿它做任何事。
        if it.season and (it.motifs or it.motif_notes):
            for cue in SEASON_CUES.get(it.season, []):
                if cue in text:
                    mark(cue)
        for item in ((self._load_motifs().get("taboo") or {}).get("items") or []):
            for key in (item.get("match") or [item["what"]]):
                if key in text:
                    mark(key)
        for spec in ((self._load_motifs().get("sets") or {}).values()):
            for al in (spec.get("aliases") or []):
                if al in text:
                    mark(al)
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

    # ---------------------------------------------------------------- 纹样

    def _load_motifs(self) -> dict:
        """读纹样表。读不出来要响亮地失败，不许回落成空表。

        回落的症状是「我没听懂你说的荷花」——把一个数据文件的语法错报成
        用户的话没说清。与 handoff._load_motifs 同一处理，两边必须一致：
        一边响一边闷，坏的那次就看运气走到哪条路。
        """
        if self._motifs is None:
            try:
                self._motifs = json.loads(MOTIFS_PATH.read_text(encoding="utf-8"))
            except FileNotFoundError as e:
                raise SystemExit(f"读不到纹样表 {MOTIFS_PATH}：{e}") from e
            except json.JSONDecodeError as e:
                raise SystemExit(
                    f"纹样表 {MOTIFS_PATH} 不是合法 JSON：第 {e.lineno} 行 {e.msg}") from e
        return self._motifs

    def season_of(self, text: str) -> str | None:
        """从话里读出季节。纹样季节错是最容易被识破的一种错。"""
        best, best_len = None, 0
        for season, cues in SEASON_CUES.items():
            for cue in cues:
                if cue in text and len(cue) > best_len:
                    best, best_len = season, len(cue)
        return best

    def _shadowed(self, text: str, catalog) -> set:
        """被色名占住的字位。纹样别名落在这里面就不算纹样请求。

        库内有荷花白、金莲花橙、荷叶绿、远山紫，而纹样别名有荷花、莲花、荷叶、远山。
        不遮蔽的话「用荷花白做底色的网站」会既解析出 seed 荷花白、又凭空多一枝荷；
        岁末场景下还要倒过来训话说「水面浮叶是夏的东西」——用户根本没提荷花，
        他说的是一个色名。这类错最难查：症状是「多给了个纹样」，
        看起来像纹样匹配太松，真正的原因是两张词表撞了名。
        """
        if catalog is None:
            return set()
        out: set = set()
        for name in list(catalog.by_name) + list(catalog.aliases):
            if len(name) < 2:
                continue
            start = 0
            while True:
                pos = text.find(name, start)
                if pos < 0:
                    break
                out.update(range(pos, pos + len(name)))
                start = pos + 1
        return out

    def match_motifs(self, text: str, scene: str | None = None,
                     season: str | None = None,
                     catalog=None) -> tuple[list, list, list]:
        """按白话挑纹样。返回 (留用的纹样, 要向用户说明的话, 命中过的别名)。

        纹样与场景是两条独立的轴。命中纹样不改配色，只追加一个点缀。

        第三个返回值是**过滤前**命中过的别名。_unheard 要用它：只按留用的纹样
        标记，被场景挡掉的那个词就会既出现在「气质不合」的说明里、又被报成没接住。
        """
        data = self._load_motifs()
        motifs = data.get("motifs", [])
        season = season or self.season_of(text)
        shadow = self._shadowed(text, catalog)
        hits, notes, heard = [], [], []
        for m in motifs:
            # 命中过的别名要全收，不能命中一个就 break。折枝梅的别名里
            # 梅花 排在 一枝梅 之前，「加一枝梅花点缀」会先中 梅花 就停下，
            # 于是 一枝 没被标记，残渣「加枝」被报成没接住——纹样明明认出来了。
            matched_here = []
            for al in m.get("aliases", []):
                pos = text.find(al)
                # 别名整段被更长的色名盖住 -> 用户说的是色名，不是纹样
                while pos >= 0 and all(i in shadow for i in range(pos, pos + len(al))):
                    pos = text.find(al, pos + 1)
                if pos >= 0:
                    matched_here.append(al)
            if matched_here:
                heard.extend(matched_here)
                hits.append(m)
        # 场景不合的挡掉，并说明原因（不静默丢弃）
        kept = []
        for m in hits:
            if scene and scene in (m.get("avoid_scenes") or []):
                notes.append(f"{m['name']}与这套配色的气质不合（{scene}），换一个或换配色")
                continue
            kept.append(m)
        # 季节冲突提醒。high 硬说，mid 软说，none 不提。
        # mid 原先与 none 同路，等于那个档位白填：折枝梅标着「冬末早春·mid」，
        # 「盛夏的活动页加一枝梅花」却一声不响——而梅开在盛夏正是最好认的那种错。
        if season:
            for m in kept:
                rig = m.get("season_rigidity")
                ms = m.get("season", "")
                if rig not in ("high", "mid") or ms in ("无季", "四季") or season in ms:
                    continue
                if rig == "high":
                    notes.append(f"{m['name']}是{ms}的东西，你说的是{season}——这个错最容易被看出来")
                else:
                    notes.append(f"{m['name']}本是{ms}的花，你说的是{season}——"
                                 f"不算硬错，但懂的人会觉得季节没对上")
        # 成套关系
        ids = {m["id"] for m in kept}
        for name, spec in (data.get("sets") or {}).items():
            members = set(spec.get("members") or [])
            inter = ids & members
            if len(inter) >= 2 and inter != members:
                missing = [x for x in members - inter]
                names = [mm["name"] for mm in motifs if mm["id"] in missing]
                notes.append(f"「{name}」是成套的，你选的这几件缺 {'、'.join(names)}"
                             f"——要么补齐，要么分置到不同区块。{spec.get('rule','')}")
        return kept, notes, heard

    def taboo_check(self, text: str) -> list:
        """礼制等级纹样的拦截。拒绝要给替代路径，不要只说不行。

        用显式 match 词表，不从 what 截字符串——「补子的禽兽等第作用户等级」
        整条当键永远匹配不上，而用户就是会那样说。
        """
        out = []
        for item in (self._load_motifs().get("taboo") or {}).get("items", []):
            for key in (item.get("match") or [item["what"]]):
                if key in text:
                    out.append(item)
                    break
        return out

    def match_sets(self, text: str) -> list:
        """用户直接点名成套（「梅兰竹菊」「岁寒三友」）时，提醒它是成套语汇。"""
        out = []
        for name, spec in (self._load_motifs().get("sets") or {}).items():
            for al in (spec.get("aliases") or []):
                if al in text:
                    out.append((name, spec))
                    break
        return out

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
        # 季节读出来了就回读。它只驱动纹样的季节提醒，不改配色——
        # 不回读的话用户无从知道我们把「岁末」听成了冬，而那句提醒正是据此发的。
        if it.season and (it.motifs or it.motif_notes):
            parts.append(f"{it.season}天")
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
