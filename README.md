# SnowFoxClaw

个人 Agent 智能体，住在你设备里的狐狸。

> **0.1.0 是占位版本。** 当前仅用于在 PyPI 上保留 `snowfoxclaw` 包名，功能尚未实现。

## 安装

```bash
pip install snowfoxclaw
```

## 验证

```bash
python -c "import snowfoxclaw; print(snowfoxclaw.__version__)"
foxclaw --version
```

## 本地服务

```bash
foxclaw serve                      # 默认 http://127.0.0.1:8765
curl http://127.0.0.1:8765/healthz # {"status":"ok","version":"0.1.0"}
```

服务只监听回环地址，不对外暴露。当前只有 `/healthz`，业务接口按里程碑逐步开放。

## 开发

```bash
git clone https://github.com/snowfoxHQ/SnowFoxClaw
cd SnowFoxClaw
pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

向量模型等重依赖在 `embed` 额外组中，按需安装：`pip install -e ".[dev,embed]"`。

## License

MIT
