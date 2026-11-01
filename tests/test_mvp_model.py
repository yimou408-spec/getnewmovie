"""M03 model adapter tests: synthetic HTTP responses, no credentials or network."""
import json

import httpx
import pytest

from scripts.mvp_intent_contracts import load_cases
from scripts.mvp_model import ModelAdapter, ModelSettings
from scripts.mvp_probe_model import main, run_probe


@pytest.fixture(autouse=True)
def isolate_project_env(monkeypatch, tmp_path):
    # Tests must never read a developer's real project credentials.
    monkeypatch.setattr("scripts.mvp_model.ENV_FILE", tmp_path / "absent.env", raising=False)


def settings(**changes):
    return ModelSettings(base_url="https://model.example/v1", api_key="SECRET", model="test-model", **changes)


def response(content, finish="stop"):
    return {"model": "actual-model", "choices": [{"finish_reason": finish, "message": {"content": content}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}}


@pytest.mark.parametrize("case_id", ["E02", "E03", "E04", "E05", "E07"])
def test_adapter_accepts_approved_intents_and_preserves_partial_updates(case_id):
    from scripts.mvp_intent_contracts import ROOT
    case = next(c for c in load_cases(ROOT / "contracts/mvp/intent-cases.json") if c.case_id == case_id)

    def handle(request):
        payload = json.loads(request.content)
        assert str(request.url) == "https://model.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer SECRET"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["max_tokens"] == 1024
        assert "json" in payload["messages"][0]["content"].lower()
        assert "expected_intent" not in payload["messages"][1]["content"]
        intent = case.expected_intent.model_dump(exclude_unset=True)
        return httpx.Response(200, json=response(json.dumps(intent, ensure_ascii=False)))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = ModelAdapter(settings(), client=client).interpret(case.request.query, context=case.context, picks=case.request.constraints)
    assert result.status == "ok"
    assert result.intent.model_dump(exclude_unset=True) == case.expected_intent.model_dump(exclude_unset=True)
    assert result.metadata["response_model"] == "actual-model"
    assert result.metadata["usage"]["total_tokens"] == 20
    assert result.metadata["finish_reason"] == "stop"


@pytest.mark.parametrize("content,finish,status", [
    ("", "stop", "empty_content"),
    ("not json SECRET", "stop", "invalid_output"),
    ('{"action":"recommend","movies":["made up"]}', "stop", "invalid_output"),
    ('{"action":"recommend"}', "length", "truncated"),
])
def test_incomplete_or_invalid_output_is_not_success_and_never_logged(content, finish, status):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response(content, finish)))) as client:
        result = ModelAdapter(settings(), client=client).interpret("想看喜剧")
    assert result.status == status
    assert result.intent is None
    assert "SECRET" not in json.dumps(result.metadata)


def test_timeout_is_bounded_and_budget_stops_second_call():
    calls = []

    def handle(request):
        calls.append(request)
        assert request.extensions["timeout"]["read"] == 20
        raise httpx.ReadTimeout("SECRET", request=request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        adapter = ModelAdapter(settings(), client=client, max_requests=1)
        first = adapter.interpret("喜剧")
        second = adapter.interpret("科幻")
    assert first.status == "timeout"
    assert second.status == "budget_exhausted"
    assert len(calls) == 1
    assert "SECRET" not in json.dumps(first.metadata)


def test_missing_settings_do_not_send_requests_or_disclose_key(monkeypatch):
    for key in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert ModelSettings.from_env() is None
    assert "SECRET" not in repr(settings())


def test_http_error_does_not_expose_response_body():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="SECRET"))) as client:
        result = ModelAdapter(settings(), client=client).interpret("喜剧")
    assert result.status == "http_401"
    assert "SECRET" not in json.dumps(result.metadata)


def test_probe_applies_global_request_cap_and_checks_semantics():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response('{"action":"recommend"}')))) as client:
        report = run_probe(settings(), case_ids=["E02", "E03"], max_requests=1, client=client)
    assert report["requests_made"] == 1
    assert [row["status"] for row in report["cases"]] == ["semantic_mismatch", "not_run_budget"]
    assert report["passed"] is False


def test_config_rejects_unsafe_or_double_endpoint():
    for url in ("http://model.example", "https://user:pass@model.example", "https://model.example?token=secret", "https://model.example/chat/completions"):
        with pytest.raises(ValueError):
            ModelSettings(base_url=url, api_key="SECRET", model="test-model")


def test_cli_requires_live_flag_and_configuration_before_creating_client(monkeypatch, capsys):
    def unexpected_client(*args, **kwargs):
        pytest.fail("Unconfigured CLI must not create an HTTP client")

    monkeypatch.setattr(httpx, "Client", unexpected_client)
    for key in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert main([]) == 2
    assert main(["--live"]) == 2
    assert "NOT_CONFIGURED" in capsys.readouterr().out


def test_single_case_probe_can_pass_with_valid_semantics():
    intent = {"action": "recommend", "updates": {"genres": ["喜剧"], "moods": ["轻松解压"],
              "max_runtime_minutes": 120, "exclude_genres": ["恐怖"]}, "conflicts": [], "unhandled": []}
    data = response(json.dumps(intent))
    data.pop("usage")
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))) as client:
        report = run_probe(settings(), case_ids=["E02"], client=client)
    assert report["passed"] is True
    assert report["requests_made"] == 1
    assert report["cases"][0]["usage"] is None
    assert report["agent_acceptance"] == "not_tested"


def test_settings_load_env_file_from_explicit_path_without_changing_process(monkeypatch, tmp_path):
    for key in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('# 本机配置\nLLM_BASE_URL=https://model.example\nLLM_MODEL=test-model\nLLM_API_KEY="file-secret"\n', encoding="utf-8-sig")
    config = ModelSettings.from_env(env_file=env_file)
    assert config.api_key == "file-secret"
    assert config.base_url == "https://model.example"
    assert ModelSettings.from_env(env_file=tmp_path / "missing.env") is None


def test_process_settings_take_precedence_over_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('LLM_BASE_URL=https://model.example\nLLM_MODEL=file-model\nLLM_API_KEY=file-secret\n', encoding="utf-8")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "process-secret")
    config = ModelSettings.from_env(env_file=env_file)
    assert config.api_key == "process-secret"
    assert config.model == "file-model"


def test_default_env_path_is_independent_of_current_directory(monkeypatch, tmp_path):
    for key in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / "project.env"
    env_file.write_text('LLM_BASE_URL=https://model.example\nLLM_MODEL=test-model\nLLM_API_KEY=file-secret\n', encoding="utf-8")
    monkeypatch.setattr("scripts.mvp_model.ENV_FILE", env_file)
    another_dir = tmp_path / "elsewhere"
    another_dir.mkdir()
    monkeypatch.chdir(another_dir)
    assert ModelSettings.from_env().api_key == "file-secret"


def test_text_interpreter_does_not_receive_conflicting_structured_picks():
    from scripts.s0_contracts import Constraints
    def handle(request):
        payload = json.loads(request.content)
        user = json.loads(payload['messages'][1]['content'])
        # Picks are merged and compared by deterministic code after text parsing.
        assert user['query'] == '喜剧，120分钟以内'
        assert 'selected_constraints' not in user
        assert '恐怖' not in payload['messages'][1]['content']
        return httpx.Response(200, json=response(json.dumps({'action': 'recommend',
            'updates': {'genres': ['喜剧'], 'max_runtime_minutes': 120}})))
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = ModelAdapter(settings(), client=client).interpret('喜剧，120分钟以内',
            picks=Constraints(genres=['恐怖']))
    assert result.status == 'ok' and result.intent.updates.genres == ['喜剧']
