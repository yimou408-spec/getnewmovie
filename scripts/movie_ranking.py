"""Transparent lexical baseline. Signals are inferences, never audience ratings.

Only source descriptions are inspected; full synopses are never exposed on cards.
Weights are product heuristics, not a fitted or user-validated relevance model.
"""
import re

CLUES = {
    "幽默": r"\b(comedy|comedic|hilarious|laugh\w*|humou?r\w*)\b",
    "友谊": r"\b(friendship|friends|friend|companions?)\b",
    "成长": r"\b(coming.of.age|grow\w*|self.discovery)\b",
    "爱情": r"\b(romance|romantic|fall\w* in love|love story)\b",
    "谜团": r"\b(mystery|mysteries|detective|investigat\w*|puzzle)\b",
    "冒险": r"\b(adventure|quest|journey|explor\w*)\b",
    "太空": r"\b(space|galaxy|galactic|astronaut|planet\w*)\b",
    "奇幻": r"\b(magic\w*|fantasy|enchanted)\b",
    "恐怖线索": r"\b(horror|terrifying|haunted|nightmare|slasher|gory|blood\w*)\b",
    "沉重线索": r"\b(grief|tragic|tragedy|brutal|murder\w*|revenge|violent)\b",
}
MOOD_CLUES = {
    "轻松解压": {"幽默", "友谊"}, "温暖治愈": {"友谊", "成长"},
    "烧脑过瘾": {"谜团"}, "浪漫心动": {"爱情"},
    "惊奇冒险": {"冒险", "太空", "奇幻"}, "感动一下": {"成长", "友谊", "爱情"},
}


def content_clues(description):
    if not isinstance(description, str):
        return []
    return [label for label, pattern in CLUES.items() if re.search(pattern, description[:12000], re.I)]


def rank_movies(rows, constraints):
    if constraints.sort_by == "popular":
        return list(rows)
    target = set().union(*(MOOD_CLUES[m] for m in constraints.moods)) if constraints.moods else set()
    calm = bool(set(constraints.moods) & {"轻松解压", "温暖治愈"})
    remaining = []
    for index, row in enumerate(rows):
        movie = row[0]
        tags = set(movie.tags)
        score = 5 / (index + 1) + 6 * len(tags & target)
        score += len(set(movie.genres) & set(constraints.genres))
        if not constraints.moods and "恐怖" not in constraints.genres and "恐怖" in movie.genres:
            score -= 9
        if calm:
            score -= 18 * len(tags & {"恐怖线索", "沉重线索"})
        remaining.append((score, index, row))
    selected = []
    used_genres, used_directors = set(), set()
    while remaining:
        def score(item):
            movie = item[2][0]
            # The first three are a varied shortlist. Never relax hard filters.
            repeat = 6 * bool(used_genres & set(movie.genres)) + 8 * bool(movie.director and movie.director in used_directors)
            return (item[0] - repeat, -item[1])
        best = max(remaining, key=score)
        remaining.remove(best)
        selected.append(best[2])
        used_genres.update(best[2][0].genres)
        if best[2][0].director:
            used_directors.add(best[2][0].director)
    return selected
