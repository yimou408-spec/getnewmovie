"""Bounded extractive opinions. Source text never supplies instructions or URLs.

Only allowlisted, verbatim aspect phrases reach default summaries. Independence
and spoiler clearance must be supplied upstream, never inferred by a model.
"""
import re
import unicodedata
from itertools import islice
import httpx

from app.services.budget import current_budget
from scripts.movie_catalog_errors import CatalogError
from scripts.s0_contracts import (Constraints, OpinionSelection, OpinionComparison,
                                  OpinionMatch, OpinionSummary, SourceEvidenceResult)

VERSION = "opinion-extractive-v1"
PHRASES = {
    ("pace", "slow"): ("节奏缓慢", "节奏偏慢", "slow-paced", "slow paced"),
    ("pace", "brisk"): ("节奏明快", "节奏紧凑", "brisk pacing", "fast-paced"),
    ("tone", "light"): ("氛围轻松", "轻松幽默", "light-hearted", "lighthearted"),
    ("tone", "heavy"): ("氛围沉重", "情绪压抑", "emotionally heavy", "bleak atmosphere"),
    ("acting", "strong"): ("表演出色", "演技出色", "strong performances", "excellent acting", "support roles are magnificent"),
    ("acting", "weak"): ("表演生硬", "演技生硬", "wooden acting", "weak performances"),
    ("visuals", "strong"): ("画面精美", "视觉出色", "stunning visuals", "beautiful cinematography"),
    ("visuals", "weak"): ("画面粗糙", "视觉粗糙", "poor visuals", "rough visuals"),
}
ASPECTS = {"pace": "节奏", "tone": "氛围", "acting": "表演", "visuals": "视觉"}
VALUES = {"slow": "偏慢", "brisk": "明快", "light": "轻松", "heavy": "沉重", "strong": "受到肯定", "weak": "受到批评"}
NEGATION = re.compile(r"不|无|没|并非|不是|未必|难说|不能|忽略|指令|提示词|https?://|[<>]|\b(?:not|no|never|without|hardly|ignore|instructions?|prompt)\b", re.I)
BASE_LIMIT = "仅对取得的材料片段作对照，不代表全网口碑；片段以外、引用支持程度及剧透仍需人工抽审。"


def eligible(movie_id, results):
    entries, seen_ids, seen_text = [], set(), set()
    for source in results:
        if source.movie_id != movie_id or source.status != "ok" or source.cache_status == "stale":
            continue
        for e in source.evidence:
            key = re.sub(r"\W+", "", unicodedata.normalize("NFKC", e.claim)).casefold()
            if (e.movie_id != movie_id or e.source != source.source or e.evidence_id in seen_ids
                    or e.kind != "review" or e.granularity not in {"excerpt", "full_text"}
                    or e.spoiler_level != "safe" or e.usage_basis not in {"licensed", "provider_terms", "synthetic"}
                    or not e.author or not key or key in seen_text):
                continue
            entries.append(e)
            seen_ids.add(e.evidence_id)
            seen_text.add(key)
            if len(entries) == 6:
                return entries
    return entries


def extract_opinions(entries):
    found = []
    for e in entries:
        per_aspect = {}
        for clause in re.split(r"[，。！？；\n.!?;]", e.claim):
            if NEGATION.search(clause):
                continue
            for (aspect, value), phrases in PHRASES.items():
                for phrase in phrases:
                    match = re.search(re.escape(phrase), clause, flags=re.I)
                    if match:
                        per_aspect.setdefault(aspect, {})[value] = match[0]
        for aspect, choices in per_aspect.items():
            # A single snippet giving both sides is too ambiguous to flatten.
            if len(choices) == 1:
                value, quote = next(iter(choices.items()))
                found.append(OpinionSelection(evidence_id=e.evidence_id, aspect=aspect, value=value, quote=quote))
    return found[:24]


def compose(opinions, entries, constraints):
    by_id = {e.evidence_id: e for e in entries}
    opinions = sorted(opinions, key=lambda p: (p.evidence_id, p.aspect, p.value, p.quote))
    groups = {by_id[p.evidence_id].independent_source_group for p in opinions
              if by_id[p.evidence_id].independent_source_group}
    comparisons = []
    for aspect in ASPECTS:
        selected = [p for p in opinions if p.aspect == aspect and by_id[p.evidence_id].independent_source_group]
        group_values = {}
        for p in selected:
            group_values.setdefault(by_id[p.evidence_id].independent_source_group, set()).add(p.value)
        selected = [p for p in selected if len(group_values[by_id[p.evidence_id].independent_source_group]) == 1]
        if len({by_id[p.evidence_id].independent_source_group for p in selected}) < 2:
            continue
        values = sorted({p.value for p in selected})
        refs = sorted({p.evidence_id for p in selected})
        if len(values) == 1:
            text = f"本次独立材料在{ASPECTS[aspect]}上的描述一致：{VALUES[values[0]]}。"
            kind = "agreement"
        else:
            text = f"本次独立材料对{ASPECTS[aspect]}的描述不同：{' / '.join(VALUES[v] for v in values)}。"
            kind = "disagreement"
        comparisons.append(OpinionComparison(aspect=aspect, kind=kind, text=text, evidence_ids=refs))
    matches, cautions = [], []
    if "轻松解压" in constraints.moods:
        for value, target, text in [
            ("light", matches, "材料含轻松氛围线索，与你本次想轻松解压的需求相符；这是匹配推断，不保证观感。"),
            ("heavy", cautions, "材料含沉重氛围线索，你本次想轻松解压，可能需要谨慎选择；这是匹配推断。"),
        ]:
            refs = sorted({p.evidence_id for p in opinions if p.aspect == "tone" and p.value == value})
            if refs:
                target.append(OpinionMatch(text=text, evidence_ids=refs))
    status = ("insufficient" if not opinions else "compared" if comparisons else
              "independence_unknown" if not groups or any(not by_id[p.evidence_id].independent_source_group for p in opinions) else
              "single_group" if len(groups) == 1 else "no_overlap")
    limitations = [BASE_LIMIT]
    if status != "compared":
        limitations.append({"insufficient": "缺少可安全引用并识别的评价观点。", "independence_unknown": "来源独立性尚未全部核验，不能认定跨源共识。",
                            "single_group": "仅一个已核验独立来源组，转载和相同正文不增加来源数。",
                            "no_overlap": "独立材料没有可对照的相同主题，未强行生成共识或分歧。"}[status])
    synthetic = any(by_id[p.evidence_id].usage_basis == "synthetic" for p in opinions)
    if synthetic:
        limitations.append("含离线合成材料，仅用于开发验收，不代表真实多源评价通过。")
    return OpinionSummary(status=status, synthetic=synthetic, independent_group_count=len(groups),
                          opinions=opinions, comparisons=comparisons, matches=matches, cautions=cautions, limitations=limitations)


def validate_synthesis(summary, movie_id, evidence, constraints=None, source_results=None):
    # Only fresh, available results may support an attached summary.
    if source_results is None:
        results = [SourceEvidenceResult(movie_id=e.movie_id, source=e.source, status="ok", evidence=[e]) for e in evidence]
    else:
        results = source_results
    entries = eligible(movie_id, results)
    allowed = {p.model_dump_json() for p in extract_opinions(entries)}
    keys = [p.model_dump_json() for p in summary.opinions]
    if len(keys) != len(set(keys)) or any(key not in allowed for key in keys):
        raise ValueError("opinion requires same-movie safe licensed verbatim support")
    expected = compose(summary.opinions, entries, constraints or Constraints())
    for field in ("status", "synthetic", "independent_group_count", "opinions", "comparisons", "matches", "cautions", "limitations"):
        if getattr(summary, field) != getattr(expected, field):
            raise ValueError("opinion synthesis must match supported deterministic output: " + field)


class OpinionPipeline:
    def __init__(self, *, model=None, supplement=None):
        self.model, self.supplement = model, supplement
        self.followup_used = False

    def run(self, movie_id, constraints, results):
        results = list(results)
        entries = eligible(movie_id, results)
        initial = compose(extract_opinions(entries), entries, constraints)
        followup, extras = "not_needed", []
        if initial.status != "compared":
            if not initial.opinions:
                followup = "safety_review_needed" if any(e.kind == "review" for r in results for e in r.evidence) else "source_unavailable"
            elif self.supplement is None:
                followup = "not_configured"
            elif self.followup_used:
                followup = "budget_exhausted"
            else:
                self.followup_used = True
                try:
                    if current_budget.get():
                        current_budget.get().check()
                    # An injected source operation shares the request ledger; one call only.
                    extras = [SourceEvidenceResult.model_validate(r) for r in islice(self.supplement(movie_id), 5)]
                    if len(extras) > 4 or any(r.movie_id != movie_id for r in extras):
                        raise ValueError("invalid followup binding")
                    existing = {e.evidence_id for r in results for e in r.evidence}
                    new_ids = [e.evidence_id for r in extras for e in r.evidence]
                    if len(new_ids) != len(set(new_ids)) or existing.intersection(new_ids):
                        raise ValueError("followup duplicate evidence")
                    if current_budget.get():
                        current_budget.get().check()
                    followup = "completed"
                except CatalogError:
                    followup, extras = "budget_exhausted", []
                except (ValueError, TypeError, OSError, httpx.HTTPError):
                    followup, extras = "failed", []
        entries = eligible(movie_id, [*results, *extras])
        opinions, method, model_status = extract_opinions(entries), "controlled_phrases", "not_enabled"
        if opinions and self.model is not None:
            selected, model_status = self.model.select(entries)
            if model_status == "ok":
                allowed = {p.model_dump_json() for p in opinions}
                keys = [p.model_dump_json() for p in selected]
                if selected and len(keys) == len(set(keys)) and set(keys) == allowed:
                    opinions, method = selected, "model_selected"
                else:
                    model_status = "invalid_output"
        summary = compose(opinions, entries, constraints)
        summary.extraction_method, summary.model_status = method, model_status
        summary.followup_status = followup
        validate_synthesis(summary, movie_id, [e for r in [*results, *extras] for e in r.evidence], constraints, [*results, *extras])
        return summary, extras
