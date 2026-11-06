"""配置加载：内置默认 -> 用户覆盖 -> 环境变量，三级合并后校验。

embedding.dim 是硬契约：写库后不允许运行时变更，所以这里在启动期就把它校验成确定的整数，
而不是等到建表时才发现配置里写的是字符串。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.default.yaml")
PROVIDERS = frozenset({"mock", "local", "ollama"})


class ConfigError(ValueError):
    """配置缺失或取值非法。"""


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str = "mock"
    model: str = "bge-small-zh-v1.5"
    dim: int = 512
    normalize: bool = True
    batch_size: int = 16


@dataclass(frozen=True)
class RetrievalSettings:
    top_k: int = 5
    high_sensitivity_quota: int = 1


@dataclass(frozen=True)
class Settings:
    embedding: EmbeddingSettings
    retrieval: RetrievalSettings
    storage_path: Path


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在：{path}") from exc
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是映射：{path}")
    return data


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """按小节浅合并，让用户配置只写要改的键。"""
    merged: dict[str, Any] = {
        key: dict(value) if isinstance(value, dict) else value for key, value in base.items()
    }
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


_ENV_KEYS = (
    ("SNOWFOXCLAW_EMBEDDING_PROVIDER", "embedding", "provider", str),
    ("SNOWFOXCLAW_EMBEDDING_MODEL", "embedding", "model", str),
    ("SNOWFOXCLAW_EMBEDDING_DIM", "embedding", "dim", int),
    ("SNOWFOXCLAW_RETRIEVAL_TOP_K", "retrieval", "top_k", int),
    ("SNOWFOXCLAW_STORAGE_PATH", "storage", "path", str),
)


def _apply_env(data: dict[str, Any], env: Mapping[str, str]) -> None:
    for env_key, section, field, caster in _ENV_KEYS:
        raw = env.get(env_key)
        if raw is None or raw == "":
            continue
        try:
            value = caster(raw)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"环境变量 {env_key} 取值非法：{raw!r}") from exc
        data.setdefault(section, {})[field] = value


def _build(data: dict[str, Any]) -> Settings:
    embedding = data.get("embedding") or {}
    retrieval = data.get("retrieval") or {}
    storage = data.get("storage") or {}

    provider = str(embedding.get("provider", "mock"))
    if provider not in PROVIDERS:
        raise ConfigError(f"embedding.provider 不支持 {provider!r}，可选：{sorted(PROVIDERS)}")

    dim = int(embedding.get("dim", 512))
    if dim < 1:
        raise ConfigError("embedding.dim 必须是正整数")

    batch_size = int(embedding.get("batch_size", 16))
    if batch_size < 1:
        raise ConfigError("embedding.batch_size 必须是正整数")

    top_k = int(retrieval.get("top_k", 5))
    if top_k < 1:
        raise ConfigError("retrieval.top_k 必须 ≥ 1")

    quota = int(retrieval.get("high_sensitivity_quota", 1))
    if quota < 0:
        raise ConfigError("retrieval.high_sensitivity_quota 不能为负")
    if quota > top_k:
        # 配额比 top_k 还大的话，等于没有约束，属于配置笔误
        raise ConfigError(f"retrieval.high_sensitivity_quota={quota} 不能大于 top_k={top_k}")

    raw_path = storage.get("path")
    if not raw_path:
        raise ConfigError("storage.path 不能为空")

    return Settings(
        embedding=EmbeddingSettings(
            provider=provider,
            model=str(embedding.get("model", "bge-small-zh-v1.5")),
            dim=dim,
            normalize=bool(embedding.get("normalize", True)),
            batch_size=batch_size,
        ),
        retrieval=RetrievalSettings(top_k=top_k, high_sensitivity_quota=quota),
        storage_path=Path(str(raw_path)).expanduser(),
    )


def load_settings(
    user_config: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Settings:
    """加载并校验配置。任一步失败都抛 ConfigError，不做静默降级。"""
    data = _read_yaml(DEFAULT_CONFIG_PATH)
    if user_config is not None:
        data = _merge(data, _read_yaml(Path(user_config)))
    _apply_env(data, os.environ if env is None else env)
    return _build(data)
