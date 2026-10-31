"""Current constraints win. Memory is read only when both switches allow it."""
from scripts.s0_contracts import Constraints
from scripts.movie_catalog_errors import CatalogError


def bounded_exclusions(*groups):
    values = list(dict.fromkeys(item for group in groups for item in group))
    if len(values) > Constraints.model_fields["exclude_movie_ids"].metadata[0].max_length:
        raise CatalogError("EVENT_CONFLICT", "本次排除与已看记录合计超过500部，请清理后重试。", 409)
    return values


def apply_memory(current, saved, seen, *, explicit=()):
    values = dict(saved)
    # Non-default current values and explicitly selected empty values override.
    defaults = Constraints().model_dump()
    for key, value in current.model_dump().items():
        if value != defaults[key] or key in explicit:
            values[key] = value
    values["exclude_movie_ids"] = bounded_exclusions(current.exclude_movie_ids, seen)
    # A current include/exclude supersedes the opposite historical preference.
    if current.genres or "genres" in explicit:
        values["exclude_genres"] = [g for g in values.get("exclude_genres", []) if g not in current.genres]
    if current.exclude_genres:
        values["genres"] = [g for g in values.get("genres", []) if g not in current.exclude_genres]
    return Constraints.model_validate(values)
