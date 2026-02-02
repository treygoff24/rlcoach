# tests/test_env_example.py


def test_env_example_includes_anthropic_key():
    content = open(".env.example", encoding="utf-8").read()
    assert "ANTHROPIC_API_KEY" in content
    assert "COACH_MODEL_ID" in content
    assert "COACH_MAX_STEPS" in content
