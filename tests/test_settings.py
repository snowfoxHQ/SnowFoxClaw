"""M0-6：配置合并与 embedding 维度契约。"""

from __future__ import annotations

from pathlib import Path

import pytest

from snowfoxclaw.embedding.mock import MockEmbedding
from snowfoxclaw.embedding.provider import EmbeddingDimensionError, assert_dim
from snowfoxclaw.settings import ConfigError, load_settings


def test_defaults_match_architecture():
    settings = load_settings(env={})
    assert settings.embedding.provider == "mock"
    assert settings.embedding.model == "bge-small-zh-v1.5"
    assert settings.embedding.dim == 512
    assert settings.retrieval.top_k == 5
    assert settings.retrieval.high_sensitivity_quota == 1
    assert settings.storage_path.name == "snowfoxclaw.db"


def test_user_config_overrides_only_given_keys(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text("embedding:\n  dim: 768\n", encoding="utf-8")

    settings = load_settings(user_config=config, env={})
    assert settings.embedding.dim == 768
    assert settings.embedding.model == "bge-small-zh-v1.5"
    assert settings.retrieval.top_k == 5


def test_env_overrides_user_config(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text("embedding:\n  dim: 768\n", encoding="utf-8")

    settings = load_settings(user_config=config, env={"SNOWFOXCLAW_EMBEDDING_DIM": "256"})
    assert settings.embedding.dim == 256


def test_missing_user_config_is_error():
    with pytest.raises(ConfigError):
        load_settings(user_config=Path("no-such-config.yaml"), env={})


def test_unknown_provider_rejected():
    with pytest.raises(ConfigError):
        load_settings(env={"SNOWFOXCLAW_EMBEDDING_PROVIDER": "openai"})


def test_non_positive_dim_rejected():
    with pytest.raises(ConfigError):
        load_settings(env={"SNOWFOXCLAW_EMBEDDING_DIM": "0"})


def test_non_integer_env_rejected():
    with pytest.raises(ConfigError):
        load_settings(env={"SNOWFOXCLAW_EMBEDDING_DIM": "big"})


def test_quota_larger_than_top_k_rejected(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text("retrieval:\n  top_k: 1\n  high_sensitivity_quota: 3\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(user_config=config, env={})


def test_mock_embedding_is_deterministic():
    provider = MockEmbedding(dim=16)
    first = provider.embed(["今天天气不错"])
    second = provider.embed(["今天天气不错"])
    assert first == second
    assert first[0] != provider.embed(["今天天气很差"])[0]


def test_mock_embedding_is_normalized():
    vector = MockEmbedding(dim=32).embed(["归一化"])[0]
    norm = sum(value * value for value in vector) ** 0.5
    assert norm == pytest.approx(1.0)


def test_assert_dim_passes_for_matching_provider():
    assert_dim(MockEmbedding(dim=512), 512)


def test_assert_dim_rejects_declared_mismatch():
    with pytest.raises(EmbeddingDimensionError):
        assert_dim(MockEmbedding(dim=512), 768)


class _LyingProvider:
    """声明 512 维但只吐 8 维，模拟接错模型的情况。"""

    dim = 512

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def test_assert_dim_rejects_output_mismatch():
    with pytest.raises(EmbeddingDimensionError):
        assert_dim(_LyingProvider(), 512)
