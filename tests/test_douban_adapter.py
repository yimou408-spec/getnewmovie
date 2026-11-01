"""Offline Douban contracts; every returned film and review below is invented."""
import httpx
import pytest

from scripts.douban_adapter import DoubanAdapter, select_identity


def candidate(mid="101", title="Test Film", year="2019"):
    return {"id": mid, "title": title, "sub_title": "Test Original", "year": year,
            "type": "movie", "url": f"https://movie.douban.com/subject/{mid}/"}


def adapter(handler, budget=9):
    return DoubanAdapter(httpx.Client(base_url="https://movie.douban.com", trust_env=False,
                                     transport=httpx.MockTransport(handler)), max_requests=budget)


def test_same_title_remakes_are_not_selected_without_exact_year_and_alias():
    rows = [candidate("101", year="1994"), candidate("102")]
    assert select_identity(rows, ["Test Film"], 2019).subject_id == "102"
    assert select_identity(rows, ["Test Film"], None).status == "ambiguous"
    assert select_identity(rows, ["Different film"], 2019).status == "no_results"
    assert select_identity([candidate("101"), candidate("102")], ["Test Film"], 2019).status == "ambiguous"


@pytest.mark.parametrize("payload", [None, {}, [None], [{"id": "../../evil"}], [candidate(year="unknown")]])
def test_malformed_search_never_becomes_a_confirmed_identity(payload):
    result = adapter(lambda r: httpx.Response(200, json=payload)).search(["Test Film"], 2019)
    assert result.subject_id is None


def test_canonical_paths_and_challenge_redirects_are_observed_without_following():
    paths = []
    def handle(request):
        paths.append(request.url.path)
        return httpx.Response(302, headers={"location": "https://sec.douban.com/a?token=secret"})
    probe = adapter(handle)
    result = probe.fetch("itunes:999", "101")
    assert paths == ["/subject/101/", "/subject/101/comments/"]
    assert result.status == "access_limited"
    assert result.evidence == []
    assert all(item.redirect_host == "sec.douban.com" for item in probe.observations)
    assert "secret" not in result.model_dump_json()
    assert "secret" not in str(probe.observations)


@pytest.mark.parametrize("status,expected", [(403, "access_limited"), (418, "access_limited"),
                                             (429, "access_limited"), (500, "upstream_error")])
def test_http_failures_are_distinct_from_no_reviews(status, expected):
    probe = adapter(lambda r: httpx.Response(status))
    assert probe.fetch("itunes:999", "101").status == expected
    assert probe.calls == 2


def test_timeouts_and_budget_include_failures_and_stop_further_calls():
    def timeout(request):
        raise httpx.ReadTimeout("sensitive upstream details")
    probe = adapter(timeout, budget=1)
    result = probe.fetch("itunes:999", "101")
    assert result.status == "budget_exhausted"
    assert probe.calls == 1
    assert probe.observations[0].status == "timeout"
    assert "sensitive" not in result.model_dump_json()


def test_200_captcha_html_is_access_limited_and_empty_html_is_parse_error():
    for body, status in [("<title>安全验证</title>", "access_limited"), ("<html></html>", "parse_error")]:
        result = adapter(lambda r: httpx.Response(200, text=body)).fetch("itunes:999", "101")
        assert result.status == status
        assert not result.evidence


def test_explicit_no_comments_is_distinct_from_a_failed_page_parse():
    body = '<div id="comments"><p>还没有人写过短评</p></div>'
    result = adapter(lambda r: httpx.Response(404) if r.url.path == "/subject/101/"
                     else httpx.Response(200, text=body)).fetch("itunes:999", "101")
    assert result.status == "no_results"
    assert result.evidence == []


def test_rating_synopsis_and_review_excerpt_remain_separate_and_bound_to_film():
    subject = '''<script type="application/ld+json">{"@type":"Movie","name":"Test Film",
      "url":"https://movie.douban.com/subject/101/","aggregateRating":
      {"ratingValue":"8.2","bestRating":"10","ratingCount":"12"}}</script>
      <span property="v:summary">Invented plot synopsis, not an audience opinion.</span>'''
    comments = '''<div class="comment-item" data-cid="901"><div class="comment">
      <span class="comment-info"><a href="https://www.douban.com/people/test/">Test Author</a></span>
      <span class="short">Invented short review excerpt.</span></div></div>'''
    result = adapter(lambda r: httpx.Response(200, text=subject if r.url.path == "/subject/101/" else comments)).fetch("itunes:999", "101")
    assert result.status == "ok"
    assert result.ratings[0].value == 8.2
    assert result.ratings[0].scale == 10
    assert {e.granularity for e in result.evidence} == {"rating", "excerpt"}
    assert all(e.movie_id == "itunes:999" for e in result.evidence)
    review = next(e for e in result.evidence if e.kind == "review")
    assert review.spoiler_level == "unknown"
    assert review.author == "Test Author"
    assert review.source_content_id == "901"
    assert "synopsis" not in review.claim
    assert review.usage_basis == "unverified"


def test_cross_film_json_ld_and_invalid_subject_ids_are_rejected():
    body = '''<script type="application/ld+json">{"@type":"Movie","url":"https://movie.douban.com/subject/202/",
      "aggregateRating":{"ratingValue":"8.2","bestRating":"10"}}</script>'''
    probe = adapter(lambda r: httpx.Response(200, text=body))
    assert not probe.fetch("itunes:999", "101").ratings
    with pytest.raises(ValueError):
        probe.fetch("itunes:999", "101/../../private")


def test_no_live_switch_makes_zero_requests(monkeypatch):
    from scripts.douban_probe import main
    monkeypatch.setattr("sys.argv", ["douban_probe"])
    def fail(*args, **kwargs):
        raise AssertionError("Network must be opt-in")
    monkeypatch.setattr(httpx.Client, "send", fail)
    assert main() == 2


def test_live_requires_explicit_network_config(monkeypatch):
    from scripts.douban_probe import main
    monkeypatch.delenv("DOUBAN_PROBE_NETWORK", raising=False)
    monkeypatch.setattr("sys.argv", ["douban_probe", "--live"])
    assert main() == 2


def test_report_counts_actual_calls_and_budget_stops_searches():
    from scripts.douban_probe import run_probe
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(429)
    report = run_probe(httpx.Client(transport=httpx.MockTransport(handle)), max_requests=2)
    assert report["requests_made"] == len(requests) == 2
    assert report["summary"]["rate_limit_count"] == 2
    assert report["results"][2]["identity_status"] == "budget_exhausted"


def test_timeout_on_subject_and_comments_is_included_in_report():
    from scripts.douban_probe import run_probe
    def handle(request):
        if request.url.path == "/j/subject_suggest":
            return httpx.Response(200, json=[candidate(title="Before Sunrise", year="1995")])
        raise httpx.ConnectTimeout("not reportable raw error")
    report = run_probe(httpx.Client(transport=httpx.MockTransport(handle)))
    assert report["summary"]["timeout_count"] == 2
    assert report["requests_made"] == 5


def test_targeted_subject_probe_stops_after_blocked_first_pair_and_preserves_identity_uncertainty():
    from scripts.douban_probe import run_subject_probe
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': 'https://sec.douban.com/c?token=SECRET'})
    report = run_subject_probe(httpx.Client(transport=httpx.MockTransport(handle)), '1296339')
    assert len(calls) == report['requests_made'] == 2
    assert len(report['results']) == 1 and report['sample_count'] == 1
    assert report['results'][0]['evaluation_status'] == 'access_limited'
    assert report['identity_status'] == 'pending_review'
    assert not report['two_round_acquisition_passed'] and not report['multi_source_acceptance_passed']
    assert 'SECRET' not in str(report)


def test_targeted_subject_probe_success_requires_both_endpoints_and_two_rounds():
    from scripts.douban_probe import run_subject_probe
    subject = '''<script type="application/ld+json">{"@type":"Movie",
      "url":"https://movie.douban.com/subject/101/","aggregateRating":
      {"ratingValue":"8.2","bestRating":"10","ratingCount":"12"}}</script>'''
    comments = '''<div class="comment-item" data-cid="901"><div class="comment">
      <span class="comment-info"><a href="https://www.douban.com/people/test/">Test Author</a></span>
      <span class="short">Invented comment; never print or store this text.</span></div></div>'''
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,
        text=subject if r.url.path == '/subject/101/' else comments)))
    report = run_subject_probe(client, '101')
    assert report['two_round_acquisition_passed'] and report['requests_made'] == 4
    assert len(report['results']) == 2 and report['identity_status'] == 'pending_review'
    assert all(r['score_count'] == r['review_excerpt_count'] == 1 for r in report['results'])
    assert 'Invented comment' not in str(report)
    limited = run_subject_probe(client, '101', max_requests=2)
    assert not limited['two_round_acquisition_passed'] and len(limited['results']) == 1
    partial = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,
        text=subject if r.url.path == '/subject/101/' else '<html></html>')))
    failed = run_subject_probe(partial, '101')
    assert not failed['two_round_acquisition_passed'] and failed['requests_made'] == 2


def test_targeted_subject_probe_cli_rejects_invalid_id_before_network(monkeypatch):
    from scripts.douban_probe import main
    monkeypatch.setenv('DOUBAN_PROBE_NETWORK', 'direct')
    monkeypatch.setattr('sys.argv', ['douban_probe', '--live', '--subject-id', '101/invalid'])
    with pytest.raises(SystemExit):
        main()
