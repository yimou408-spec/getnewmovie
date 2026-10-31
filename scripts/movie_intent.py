"""Bounded intent sessions with local/cloud extraction and deterministic fallback.

Only accepted constraints reach the real catalog. Unsupported prose requires
consent; no synthetic movie fallback. Cloud prose transfer is opt-in via config.
Sessions are anonymous capability tokens, process-local, capped and expiring.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from threading import RLock
import time
from uuid import uuid4

from scripts.movie_catalog import CatalogError
from scripts.s0_contracts import Constraints, Interpretation, Question


GENRES = {
    "喜剧": "喜剧|comedy", "科幻与奇幻": "科幻与奇幻|科幻|奇幻|sci-fi|science fiction|fantasy",
    "惊悚": "惊悚|悬疑|悬念|thriller|mystery", "动作": "动作|action",
    "爱情": "爱情|romance", "动画": "动画|animation", "剧情": "剧情|drama",
    "家庭": "家庭|family", "纪录片": "纪录片|documentary", "恐怖": "恐怖|horror",
}
MOODS = {
    "轻松解压": "轻松解压|轻松|解压|放松(?:一下)?|幽默|搞笑|relax(?:ing)?|funny",
    "温暖治愈": "温暖治愈|温暖|治愈|warm|heartwarming",
    "烧脑过瘾": "烧脑过瘾|烧脑|过瘾|mind.bending",
    "浪漫心动": "浪漫心动|浪漫|心动|romantic",
    "惊奇冒险": "惊奇冒险|惊奇|冒险|adventure",
    "感动一下": "感动一下|感动|感人|moving",
}
NUMBER = r"[0-9零〇一二两三四五六七八九十百半个.]+"
GENRE_PATTERN = "|".join(f"(?:{p})" for p in GENRES.values())
NEGATION = r"(?:不要(?:看)?|不想(?:看)?|不喜欢(?:看)?|别看|不看|排除|不|\b(?:without|not|no)\b)"
NEGATIVE = rf"{NEGATION}\s*(?:任何)?(?:{GENRE_PATTERN})(?:片|电影)?(?:\s*[、和或与及]\s*(?:{GENRE_PATTERN})(?:片|电影)?)*"


def number(text):
    text = text.replace("个", "").replace("两", "二")
    if text == "半":
        return .5
    if text.endswith("半"):
        return number(text[:-1]) + .5
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    digits = {c: i for i, c in enumerate("零一二三四五六七八九")}
    total, current = 0, 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in "十百":
            total += (current or 1) * (10 if char == "十" else 100)
            current = 0
        else:
            raise ValueError("unsupported number")
    return total + current


def parse_text(query):
    text = query.lower().strip()
    parsed, unhandled = {}, []

    def remove(pattern, action):
        nonlocal text
        def replace(match):
            action(match)
            return " "
        text = re.sub(pattern, replace, text, flags=re.I)

    def add(field, value):
        if value not in parsed.setdefault(field, []):
            parsed[field].append(value)

    def exclusions(match):
        for label, pattern in GENRES.items():
            if re.search(pattern, match[0], re.I):
                add("exclude_genres", label)

    remove(NEGATIVE, exclusions)
    # Strip upper-bound prefixes before recognizing lower-bound expressions.
    text = re.sub(r"(?:不要超过|不超过|不能超过|最多|至多|上限为?)\s*", "", text)
    # Do not turn a range, a lower bound or approximate time into an upper bound.
    remove(rf"{NUMBER}\s*(?:到|至|[-~—])\s*{NUMBER}\s*分钟|(?:至少|不少于|超过)\s*{NUMBER}\s*(?:小时|分钟)|{NUMBER}\s*(?:小时|分钟)\s*(?:左右|以上)",
           lambda m: unhandled.append(m[0]))
    times = []
    def duration(m):
        try:
            value = number(m[1]) * 60 + (number(m[2]) if m[2] else 0) if m[1] else number(m[3])
            if value != int(value) or not 1 <= value <= 600:
                raise ValueError("duration outside supported range")
            times.append(int(value))
        except ValueError:
            unhandled.append(m[0])
    remove(rf"(?:({NUMBER})\s*(?:小时|钟头)(?:\s*({NUMBER})\s*分钟)?|({NUMBER})\s*分钟)(?:以内|以下|之内)?", duration)
    if len(set(times)) == 1:
        parsed["max_runtime_minutes"] = times[0]
    elif times:
        unhandled.append("出现多个不同时长，请保留一个明确的上限")
    # Parse company before genre: "with family" is a context, not a genre.
    for field, patterns in {
        "company": {
            "和家人": "和家人|全家|带孩子|陪孩子|with family",
            "两个人": "两个人|约会|和对象|和伴侣|date night",
            "和朋友": "和朋友|朋友一起|with friends", "一个人": "一个人|独自|alone",
        },
        "era": {
            "recent": "2020年(?:以后|以来|至今)|新片",
            "2000s": "2000(?:年)?(?:到|至|[-—])2019年?",
            "classic": "2000年(?:以前|之前)",
        },
    }.items():
        values = []
        for label, pattern in patterns.items():
            remove(rf"{NEGATION}\s*(?:{pattern})", lambda m: unhandled.append(m[0]))
            remove(pattern, lambda m, label=label: values.append(label))
        values = list(dict.fromkeys(values))
        if len(values) == 1:
            parsed[field] = values[0]
        elif values:
            context = "同行" if field == "company" else "年代"
            names = {"recent": "2020 年至今", "2000s": "2000—2019 年", "classic": "2000 年以前"}
            choices = " / ".join(names.get(value, value) for value in values)
            unhandled.append(f"出现多个不同{context}：{choices}；请保留一个明确条件")
    for label, pattern in GENRES.items():
        remove(pattern, lambda m, label=label: add("genres", label))
    for label, pattern in MOODS.items():
        # Negated moods are not converted into the same positive preference.
        remove(rf"{NEGATION}\s*(?:{pattern})", lambda m: unhandled.append(m[0]))
        remove(pattern, lambda m, label=label: add("moods", label))
    if set(parsed.get("genres", [])) & set(parsed.get("exclude_genres", [])):
        unhandled.append("文字同时要求并排除同一类型，请重新描述")
    residue = re.sub(r"(?:什么都行|没有特别偏好|随便|都可以|下班后|下班|今晚|今天|现在|周末|我们|我|想要|希望|想|推荐|给我|帮我|找|一起|看看|看|一部|几部|电影|片子|片|一点|一下|有点|一些|的|和|或|但是|但|直接|候选|please|a movie|movies?|want|some)", "", text)
    residue = re.sub(r"[\s，。；、！？,.!?;:：]", "", residue)
    if residue:
        unhandled.insert(0, residue[:200])
    return parsed, list(dict.fromkeys(unhandled))


def explain(c, **extra):
    hard = []
    if c.genres:
        hard.append("类型：" + " / ".join(c.genres))
    if c.max_runtime_minutes:
        hard.append(f"时长不超过 {c.max_runtime_minutes} 分钟（未知时长不入选）")
    if c.exclude_genres:
        hard.append("排除类型：" + " / ".join(c.exclude_genres))
    if c.exclude_movie_ids:
        hard.append(f"排除 {len(c.exclude_movie_ids)} 部已指定影片")
    if c.era != "any":
        hard.append("年代：" + {"recent": "2020 年至今", "2000s": "2000—2019 年", "classic": "2000 年以前"}[c.era])
    if c.company == "和家人":
        hard.append("和家人：限定家庭 / 动画，适龄需自行核对")
    soft = ["心情：" + " / ".join(c.moods) + "（类型与简介词法线索推断）"] if c.moods else []
    if c.company and c.company != "和家人":
        soft.append("同行情境：" + c.company + "（仅记录，不改变排序）")
    return Interpretation(effective_constraints=c, hard_conditions=hard, soft_preferences=soft, **extra)


@dataclass
class Pending:
    fingerprint: str
    token: str
    text: Constraints
    picks: Constraints
    conflicts: list[str]
    unhandled: list[str]
    questions: list[Question]
    method: str


class IntentSessions:
    def __init__(self, ttl=1800, capacity=256, clock=time.monotonic, parser=None):
        self.ttl, self.capacity, self.clock = ttl, capacity, clock
        self.sessions = {}
        self.lock = RLock()
        self.parser = parser or parse_text
        self.method = getattr(parser, "method", "rules-v1")

    def create(self):
        with self.lock:
            now = self.clock()
            self.sessions = {k: v for k, v in self.sessions.items() if v[0] > now}
            if len(self.sessions) >= self.capacity:
                del self.sessions[next(iter(self.sessions))]
            sid = uuid4().hex
            self.sessions[sid] = (now + self.ttl, None)
            return sid

    def resolve(self, body):
        with self.lock:
            entry = self.sessions.get(body.session_id)
            if not entry or entry[0] <= self.clock():
                self.sessions.pop(body.session_id, None)
                raise CatalogError("SESSION_EXPIRED", "临时会话已过期，请重新提交观影想法。", 409)
            values = body.model_dump(exclude={"clarification", "clarification_count"})
            # Rerolls may extend the exclusion list without changing a confirmed intent.
            values["constraints"].pop("exclude_movie_ids", None)
            fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            pending = entry[1]
            if body.clarification:
                if not pending or pending.token != body.clarification.clarification_id or pending.fingerprint != fingerprint:
                    raise CatalogError("STALE_CLARIFICATION", "条件已变更或澄清已过期，请重新提交。", 409)
                answers = {a.question_id: a.option for a in body.clarification.answers}
                if len(answers) != len(body.clarification.answers) or set(answers) != {q.question_id for q in pending.questions} or any(answers[q.question_id] not in q.options for q in pending.questions):
                    raise CatalogError("INVALID_CLARIFICATION", "请完整选择当前问题提供的选项。", 422)
                c = pending.picks if answers.get("conflict") == "按点选条件" else pending.text
                c = c.model_copy(update={"exclude_movie_ids": body.constraints.exclude_movie_ids})
                return explain(c, method=pending.method, conflicts=[], unhandled=pending.unhandled), None, []
            method = self.method
            try:
                parsed, unhandled = self.parser(body.query)
            except CatalogError:
                parsed, unhandled = parse_text(body.query)
                method = "rules-v1"
            original = body.constraints
            merged = original.model_dump()
            conflicts = []
            for field, value in parsed.items():
                current = merged[field]
                if field == "exclude_genres":
                    merged[field] = list(dict.fromkeys([*current, *value]))
                else:
                    if current not in (None, [], "", "any") and current != value:
                        label = {"genres": "类型", "moods": "心情", "max_runtime_minutes": "时长上限", "company": "同行", "era": "年代"}[field]
                        def display(item):
                            if isinstance(item, list):
                                return " / ".join(item)
                            if field == "era":
                                return {"recent": "2020 年至今", "2000s": "2000—2019 年", "classic": "2000 年以前"}[item]
                            return f"{item} 分钟" if field == "max_runtime_minutes" else str(item)
                        conflicts.append(f"{label}：点选 {display(current)}；文字 {display(value)}")
                    merged[field] = value
            if set(merged["genres"]) & set(merged["exclude_genres"]):
                conflicts.append("要求类型与排除类型有交集，不能直接推荐")
            c = Constraints.model_validate(merged)
            questions = []
            if conflicts:
                questions.append(Question(question_id="conflict", text="文字和点选条件有冲突，这次以哪组为准？", options=["按文字条件", "按点选条件"]))
            if unhandled:
                questions.append(Question(question_id="unhandled", text="这些要求暂时无法可靠执行：" + "；".join(unhandled) + "。要仅按已识别条件继续吗？", options=["仅按已识别条件继续"] if not any("同时要求并排除" in x for x in unhandled) else []))
            if not questions:
                self.sessions[body.session_id] = (entry[0], None)
                return explain(c, method=method), None, []
            if not pending or pending.fingerprint != fingerprint:
                picks = original.model_copy(deep=True)
                text_values = c.model_dump()
                # A text exclusion explicitly conflicts with an included pick.
                text_values["genres"] = [g for g in c.genres if g not in c.exclude_genres]
                c = Constraints.model_validate(text_values)
                pending = Pending(fingerprint, uuid4().hex, c, picks, conflicts, unhandled, questions, method)
                self.sessions[body.session_id] = (entry[0], pending)
            return explain(pending.text, method=pending.method, conflicts=conflicts, unhandled=unhandled), pending.token, pending.questions
