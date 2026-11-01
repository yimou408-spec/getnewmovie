"""Local, revocable decisions about exact acquired review excerpts.

This registry records an auditor's assertions; it cannot establish originality
or permissions itself. Never persist its overlays in the acquisition cache.
"""
import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from scripts.s0_contracts import StrictModel


class IndependenceBasis(StrictModel):
    publisher: str = Field(min_length=3, max_length=160)
    original_url: HttpUrl
    rationale: str = Field(min_length=30, max_length=1000)

    @model_validator(mode='after')
    def public_reference(self):
        url = self.original_url
        if url.scheme != 'https' or url.username or url.password or url.port not in {None, 443}:
            raise ValueError('original publication requires an HTTPS reference')
        return self


class ReviewDecision(StrictModel):
    movie_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=160)
    evidence_id: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    author: str = Field(min_length=1, max_length=160)
    claim_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    excerpt: str = Field(min_length=1, max_length=600)
    spoiler_level: Literal['safe', 'contains_spoilers']
    independent_source_group: str | None = Field(default=None, min_length=1, max_length=160)
    independence_basis: IndependenceBasis | None = None
    reviewer: str = Field(min_length=1, max_length=160)
    reviewer_kind: Literal['human', 'agent']
    reviewed_at: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
    reason: str = Field(min_length=20, max_length=1000)

    @model_validator(mode='after')
    def independent_basis_required(self):
        if bool(self.independent_source_group) != bool(self.independence_basis):
            raise ValueError('independence requires an original-publisher reference and rationale')
        return self


class ReviewRegistry(StrictModel):
    version: Literal[1]
    decisions: list[ReviewDecision] = Field(max_length=500)

    @model_validator(mode='after')
    def unique_decisions(self):
        keys = [(d.movie_id, d.source, d.evidence_id) for d in self.decisions]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate audit decisions')
        return self


class ReviewAudit:
    def __init__(self, path):
        self.path = Path(path)

    def apply(self, result):
        output = result.model_copy(deep=True)
        if result.status != 'ok' or result.cache_status == 'stale':
            return output
        try:
            if self.path.stat().st_size > 2_000_000:
                raise ValueError('oversized registry')
            registry = ReviewRegistry.model_validate_json(self.path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            output.warnings.append('评价审核登记不可用；保留来源原始标记，不提升安全或独立性。')
            return output
        decisions = {(d.movie_id, d.source, d.evidence_id): d for d in registry.decisions}
        for e in output.evidence:
            d = decisions.get((e.movie_id, e.source, e.evidence_id))
            if (d is None or e.movie_id != result.movie_id or e.source != result.source
                    or e.kind != 'review' or e.granularity not in {'excerpt', 'full_text'}
                    or e.usage_basis not in {'licensed', 'provider_terms'}
                    or e.spoiler_level == 'contains_spoilers'):
                continue
            if (str(e.url) != str(d.url) or e.author != d.author
                    or hashlib.sha256(e.claim.encode('utf-8')).hexdigest() != d.claim_sha256
                    or d.excerpt not in e.claim):
                output.warnings.append('评价审核与当前材料不一致；未套用旧审核结论。')
                continue
            e.claim, e.granularity = d.excerpt, 'excerpt'
            e.spoiler_level = d.spoiler_level
            e.independent_source_group = d.independent_source_group
            output.warnings.append(f'片段审核：{d.reviewer_kind}:{d.reviewer}，{d.reviewed_at}；'
                                   '仅覆盖当前引用片段，不代表整篇无剧透或人工签收。')
        return output
