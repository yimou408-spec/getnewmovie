"""Explicit cross-source links; a title match never rewrites the canonical ID."""
from scripts.s0_contracts import ExternalMovieIdentity, Movie


def confirm_external_identity(movie: Movie, identity: ExternalMovieIdentity) -> Movie:
    identity = ExternalMovieIdentity.model_validate(identity.model_dump())
    if identity.status != "confirmed":
        raise ValueError("an external candidate requires independent confirmation")
    existing = [link for link in movie.external_ids or [] if link.provider == identity.provider]
    if any(link.external_id != identity.external_id for link in existing):
        raise ValueError("conflicting external identity; resolve before merging")
    result = movie.model_copy(deep=True)
    result.external_ids = [link for link in result.external_ids or [] if link.provider != identity.provider] + [identity]
    return result
