"""Shared deterministic rules for existing selections and future Agent turns."""
from dataclasses import dataclass
from datetime import datetime, timezone

from scripts.movie_ranking import rank_movies
from scripts.s0_contracts import Constraints


@dataclass
class ConditionResolution:
    constraints: Constraints
    conflicts: list[str]
    unhandled: list[str]

    @property
    def needs_confirmation(self):
        return bool(self.conflicts or self.unhandled)


def merge_conditions(intent, *, previous=None, selected=None, displayed=()):
    """Preserve omitted fields; same-turn picks and text conflicts are explicit."""
    if intent.action == "reset":
        return ConditionResolution(Constraints(), [], [])
    previous, selected = previous or Constraints(), selected or Constraints()
    base = previous if intent.action in ("refine", "reroll") else Constraints()
    values = base.model_dump()
    picks = selected.model_dump(exclude_unset=True)
    updates = intent.updates.model_dump(exclude_unset=True)
    values.update(picks)
    values.update(updates)
    conflicts = list(intent.conflicts)
    for name, value in updates.items():
        pick = picks.get(name)
        if name != "exclude_movie_ids" and pick not in (None, [], "", "any", "balanced") and pick != value:
            conflicts.append(f"{name}：本次点选条件与文字要求不同，请确认。")
    if set(values["genres"]) & set(values["exclude_genres"]):
        if not conflicts:
            conflicts.append("要求类型与排除类型有交集，请确认。")
    if intent.action == "reroll":
        values["exclude_movie_ids"] = list(dict.fromkeys([*values["exclude_movie_ids"], *displayed]))
    return ConditionResolution(Constraints.model_validate(values), list(dict.fromkeys(conflicts)), list(intent.unhandled))


@dataclass
class MovieSelection:
    eligible: list
    candidates: list


def select_movies(rows, constraints, *, current_year=None):
    """Hard filters first; lexical ranking only orders eligible real catalog rows."""
    year = current_year if current_year is not None else datetime.now(timezone.utc).year
    eligible, seen = [], set()
    for movie, retrieved_at in rows:
        genres = set(movie.genres)
        if movie.movie_id in seen or movie.movie_id in constraints.exclude_movie_ids or genres.intersection(constraints.exclude_genres):
            continue
        if constraints.genres and not genres.intersection(constraints.genres):
            continue
        if constraints.company == "和家人" and not genres.intersection({"家庭", "动画"}):
            continue
        if constraints.max_runtime_minutes is not None and (movie.runtime_minutes is None or movie.runtime_minutes > constraints.max_runtime_minutes):
            continue
        if constraints.era != "any":
            low, high = {"recent": (2020, year), "2000s": (2000, 2019), "classic": (1888, 1999)}[constraints.era]
            if movie.year is None or not low <= movie.year <= high:
                continue
        seen.add(movie.movie_id)
        eligible.append((movie, retrieved_at))
    ranked = rank_movies(eligible, constraints)
    return MovieSelection(ranked, ranked[:3])
