# SnowFoxClaw 个人 Agent 第一阶段开发架构文档 v0.2

## 1. 文档信息

| 项 | 内容 |
| --- | --- |
| 项目 | SnowFoxClaw 个人 Agent |
| 阶段 | 第一阶段：人格 + 记忆 + 对话连续性 |
| 目标 | 验证「个人 Agent 懂我、记得我、语气连续」，不是缩水企业系统 |
| 状态 | 架构基线 |
| 关联 | Hestia 仅通过 adapter 复用 vecRecall/HKC 能力，不共享企业语义 |
| 变更 | v0.2：目录改单包布局，补 vecRecall adapter 与 embedding 选型。修订版：补 ConversationTurn schema、EmbeddingProvider、依赖清单，修第 3 周依赖 |

### 1.1 术语

| 术语 | 含义 |
| --- | --- |
| Hestia | 企业线 Agent 系统，完整契约引擎、多租户、审计链 |
| vecRecall | Hestia 侧向量记忆检索组件，提供 embedding 存储与召回能力 |
| HKC | Hestia Knowledge Core，企业与个人的知识存储/检索底座 |
| L0–L3 | 人格、偏好、情景记忆、工作上下文四层记忆分层 |
| used_context | 每次回复附带的上下文使用清单，用于可解释与调试 |

## 2. 阶段目标与非目标

### 2.1 目标

1. 建立结构化人格层 Persona Profile，人格不是提示词里几句人设。
2. 建立偏好存储 Preference Store，支持记住用户习惯、时段、渠道、禁忌。
3. 建立情景记忆 Episodic Memory，支持跨会话检索。
4. 建立工作上下文 Working Context，保证单会话任务连续。
5. 实现 Context Assembler：每次对话按预算组装人格、偏好、记忆、工作上下文。
6. 实现最小评估集与可观测面板：能证明「记得住、不乱记、可删除、语气一致」。

### 2.2 非目标

第一阶段不做：工具执行、轻量契约、主动触发、多模态、多设备同步、云端增强、企业审计链。只预留接口桩：ActionProposal、ConfirmationGate、TriggerEvent、AuditEvent。

## 3. 设计原则

1. 对话是主界面：只做 chat 入口，不做审批卡片；调试面板仅为 CLI 只读子命令（`foxclaw context show`），不做 Web UI。
2. 人格连续性优先：Persona Profile 结构化、版本化，每次对话固定加载。
3. 记忆分层：L0 Persona、L1 Preference、L2 Episodic、L3 Working，vecRecall 只是检索后端之一。
4. 本地优先：第一阶段默认 LOCAL_ONLY，数据不出设备。
5. 可评估：人格、记忆、删除、连续性都有最小指标。
6. 接口隔离：共享组件通过 adapter 接入，不直接依赖 Hestia 实现。
7. 单包优先：沿用已发布的 snowfoxclaw 单包，内部按子模块组织，不做多包拆分。

## 4. 逻辑架构

```
User
  │
  ▼
CLI: foxclaw chat / API: /v1/chat
  │
  ▼
Conversation Orchestrator
  ├── PersonaService          L0 人格
  ├── PreferenceService       L1 偏好
  ├── MemoryService           L2 情景记忆
  │     └── MemoryRetriever Adapter → LocalIndex / VecRecallAdapter
  ├── WorkingContextService   L3 工作上下文
  ├── ContextAssembler        预算裁剪 + PromptBuilder
  ├── EmbeddingProvider       向量化（mock / 本地 / Ollama）
  ├── LLMProvider             本地模型 / 云模型可切换
  ├── TurnStore               对话记录
  └── MemoryExtractor         候选记忆提取（第一阶段：纯规则；第 3 周加 LLM 摘要）
        └── CandidateStore → 用户确认 / 低风险自动入 MemoryStore
```

### 4.1 模块职责

| 模块 | 职责 |
| --- | --- |
| Conversation Orchestrator | 接收消息、加载上下文、调用 LLM、回写 turn、触发候选提取 |
| PersonaService | 人格配置读写、版本管理、激活版本 |
| PreferenceService | 偏好 CRUD、相关偏好召回、置信度与敏感级 |
| MemoryService | 情景记忆写入、检索、删除、导出 |
| MemoryRetriever | 检索抽象；第一阶段实现 LocalIndex，预留 VecRecallAdapter |
| WorkingContextService | 当前任务目标、活跃实体、未决问题、TTL |
| ContextAssembler | 按 token 预算组装 L0–L3，输出可解释 ContextBundle |
| EmbeddingProvider | 文本向量化抽象，支持 mock/本地/外部，业务代码不得直连模型 |
| LLMProvider | 模型抽象，支持 mock/本地/云，业务代码不得直连模型 |
| TurnStore | 对话 turn 持久化，供 raw_ref 回查与 used_context 回读 |
| MemoryExtractor | 从 turn 中提取候选记忆，敏感过滤、去重、置信度 |
| EvalHarness | 跑评估集，输出人格一致性、记忆召回、删除生效等报告 |

## 5. 数据模型

### 5.1 PersonaProfile

```json
{
  "id": "persona_default",
  "version": 1,
  "display_name": "用户称呼",
  "tone": "简洁/温和/直接",
  "verbosity": "short|medium|long",
  "language": "zh-CN",
  "values": ["尊重", "不替我做不可逆决定"],
  "boundaries": ["不主动联系第三方", "不读取未授权文件"],
  "taboos": ["不说教", "不频繁追问"],
  "response_style": {"format": "先结论后细节", "emoji": "少"},
  "updated_at": "ISO8601",
  "source": "user_confirmed"
}
```

人格更新必须用户确认；每次对话记录使用的 persona_version。

### 5.2 PreferenceItem

```json
{
  "id": "pref_001",
  "domain": "schedule|communication|writing|general",
  "key": "提醒时间",
  "value": "晚上11点",
  "confidence": 0.9,
  "sensitivity": "low|medium|high",
  "source": "user_explicit|inferred",
  "created_at": "ISO8601",
  "last_used_at": "ISO8601"
}
```

敏感偏好不自动写入；推断偏好需低风险且可查看、可删除。

### 5.3 EpisodicMemory

```json
{
  "id": "mem_001",
  "session_id": "s1",
  "ts": "ISO8601",
  "type": "event|fact|preference_evidence|task",
  "summary": "用户说周四下午通常开会",
  "entities": ["周四", "会议"],
  "raw_ref": "turn_123",
  "embedding_ref": "vec_001",
  "importance": 0.7,
  "confidence": 0.8,
  "sensitivity": "low",
  "expires_at": null
}
```

### 5.4 WorkingContext

```json
{
  "session_id": "s1",
  "task_goal": "整理下周日程",
  "active_entities": ["项目A", "周四"],
  "open_questions": ["是否包含周五"],
  "recent_turns": ["turn_122", "turn_123"],
  "ttl": "2h"
}
```

### 5.5 ConversationTurn（本版新增）

流程第 9 步、TurnStore、raw_ref、used_context 回读都依赖此结构，第 1 周 W1-3 建表前须冻结。

```json
{
  "id": "turn_123",
  "session_id": "s1",
  "ts": "ISO8601",
  "role": "user|assistant",
  "content": "原文或按脱敏规则处理后的文本",
  "persona_version": 1,
  "used_context": {
    "persona_version": 1,
    "preferences_used": ["pref_001"],
    "memories_used": ["mem_001"]
  },
  "tokens": {"prompt": 1200, "completion": 300}
}
```

约定：

- `content` 落库前按第 9 章规则脱敏，日志不落原文。
- `used_context` 仅 assistant turn 有值，user turn 为 null。
- `tokens` 用于预算校准，缺失不阻断。

### 5.6 数据分级

| 级别 | 范围 | 第一阶段处理 |
| --- | --- | --- |
| LOCAL_ONLY | 人格、偏好、情景记忆、敏感文件索引 | 默认，全部数据 |
| ENCRYPTED_SYNC | 多设备同步的密文 | 预留，不实现 |
| CLOUD_ENHANCED | 用户显式授权的无状态推理 | 预留；如接云模型，只发本次组装的最小上下文 |

## 6. 关键接口

### 6.1 内部服务接口

```
PersonaService.getActive() -> PersonaProfile
PreferenceService.relevant(session, message) -> PreferenceItem[]
MemoryService.search(query, session, topK) -> EpisodicMemory[]
WorkingContextService.get(session) -> WorkingContext
ContextAssembler.assemble(session, message) -> ContextBundle
LLMProvider.chat(messages, options) -> Reply
MemoryExtractor.extract(turn) -> MemoryCandidate[]
```

### 6.2 外部最小 API

```
POST /v1/chat
  {session_id, message}
  -> {reply, used_context: {persona_version, preferences_used, memories_used}}

GET/PUT /v1/persona
GET/POST/PATCH/DELETE /v1/preferences
GET /v1/memories?query=&type=&limit=
DELETE /v1/memories/{id}
GET /v1/sessions/{id}/context
POST /v1/eval/run
```

used_context 是「可解释」的最小要求，调试面板可展示。

服务只监听 127.0.0.1，默认无鉴权；如需对外暴露必须同时启用鉴权，第一阶段不支持。

### 6.3 vecRecall adapter 约定（M0 冻结）

第一阶段不依赖 Hestia 运行环境，只定义适配接口。M0 冻结签名，第 2 周按接口实现 LocalIndex，VecRecallAdapter 作为可选后端。

```python
class MemoryRetriever(Protocol):
    def upsert(self, item: MemoryItem) -> str: ...
    def delete(self, ids: list[str]) -> None: ...
    def search(self, query: str, top_k: int,
               filters: dict | None = None) -> list[RetrievedItem]: ...

@dataclass
class MemoryItem:
    id: str
    text: str
    metadata: dict          # session_id, type, sensitivity, importance
    embedding: list[float] | None

@dataclass
class RetrievedItem:
    id: str
    text: str
    score: float
    metadata: dict
```

约定：

- adapter 只做「存、删、查」，不承担人格、偏好、工作上下文语义。
- 第一阶段默认实现 LocalIndex（SQLite + 本地向量）。
- VecRecallAdapter 只保证接口兼容，不引入 Hestia 的服务发现、鉴权、审计依赖。
- 后续接入 vecRecall 时替换实现，不改上层调用。

### 6.4 HKC 约定

第一阶段不接入 HKC。个人知识以「笔记/文件」形式由后续阶段处理。边界：HKC 对企业是知识库，对个人是混合体，不继承企业分类体系；接入时通过独立 adapter，不共享企业 schema。

## 7. 关键流程：一次对话

1. 接收消息，加载 PersonaProfile 激活版本。
2. 召回相关偏好：按 domain、关键词、最近使用、置信度排序。
3. 检索情景记忆：query + recency + importance，topK 可配置。
4. 加载 Working Context，按 TTL 清理过期项。
5. ContextAssembler 按 token 预算裁剪：人格固定 > 工作上下文 > 偏好 > 情景记忆。
6. PromptBuilder 从结构化字段生成 system prompt，不把人格写死在代码。
7. 调用 LLMProvider 生成回复。
8. 写入 ConversationTurn，记录 persona_version 和 used_context。
9. 异步 MemoryExtractor 提取候选：规则先过滤敏感信息，再生成摘要（第 3 周前仅规则）。
10. 候选去重、置信度评估；低风险偏好可自动入待确认列表，敏感项不写入。
11. 更新 Working Context 摘要。
12. 返回回复；用户可查看「这次用了哪些记忆/偏好」。

## 8. 存储、模型与部署

### 8.1 包布局

沿用已发布单包 snowfoxclaw，第一阶段不拆分多包。

```
src/snowfoxclaw/
  cli.py              # 现有入口，新增 serve / chat / context 子命令
  persona/
    schema.py
    service.py
  preference/
    schema.py
    service.py
  memory/
    schema.py
    service.py
    retriever.py      # MemoryRetriever + LocalIndex
    extractor.py      # 规则提取；第 3 周加 LLM 摘要
    store.py
  context/
    assembler.py
    prompt_builder.py
    working.py
  llm/
    provider.py
    mock.py
    local.py
  embedding/
    provider.py       # EmbeddingProvider 协议（本版新增）
    mock.py
    local.py
  storage/
    db.py
    migrations/
  eval/
    harness.py
  adapters/
    vecrecall.py      # 仅接口兼容
  api/
    server.py
    chat.py
    persona.py
    preferences.py
    memories.py
  schema/             # M0-1 产出的 JSON Schema
  privacy/            # M0-2 产出的分级与敏感规则
config.yaml           # M0-6 产出，随包分发默认值
```

`apps/agentd/` 不单独存在，改为 `foxclaw serve` 子命令，挂在现有 `foxclaw` 入口下。

### 8.2 存储

- SQLite 存结构化数据与 turn；本地向量索引存 embedding。
- 通过 MemoryRetriever 接口隔离，后续可换 vecRecall。
- 第一阶段支持数据库文件加密可选；日志脱敏。

### 8.3 Embedding 选型（M0-6 决策）

| 项 | 选择 |
| --- | --- |
| 默认模型 | bge-small-zh-v1.5，512 维，本地 CPU 可跑 |
| 备选 | nomic-embed-text（Ollama），768 维 |
| 索引 | SQLite 存向量 BLOB + 内存余弦；数据量 <10 万条不引专用向量库 |
| 维度 | 写入配置 embedding.dim，迁移时固定，不允许运行时变更 |

M0 确定模型与维度并写入 config.yaml，第 2 周按此实现，避免表结构返工。

### 8.4 LLM

默认 mock 用于测试；本地 Ollama/llama.cpp 可选；云模型仅传最小上下文。

### 8.5 EmbeddingProvider（本版新增）

8.3 定了模型与维度，但测试链路不能依赖真实模型，否则 CI 要装 torch。与 LLMProvider 平级抽象：

```python
class EmbeddingProvider(Protocol):
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

实现与用途：

| 实现 | 用途 | 依赖 |
| --- | --- | --- |
| MockEmbedding | 单测与 CI 默认，固定种子生成确定性向量，可测召回排序 | 无 |
| LocalBgeEmbedding | 本地推理，默认生产路径 | onnxruntime 或 sentence-transformers |
| OllamaEmbedding | 走 Ollama /api/embeddings | 本地 Ollama |

规则：`dim` 由实现声明，与 config.yaml 的 `embedding.dim` 必须一致，启动时校验，不一致直接失败而不是降级。

### 8.6 依赖清单（本版新增，随 M0-8 落地）

| 类别 | 依赖 |
| --- | --- |
| 运行时 | pydantic>=2, fastapi, uvicorn, httpx, pyyaml |
| extras: embed | onnxruntime 或 sentence-transformers |
| extras: ollama | 无额外依赖（httpx 直连） |
| 开发 | pytest, ruff, mypy |

可选重依赖一律放 extras，保证 `pip install snowfoxclaw` 不拖入模型运行时。

## 9. 安全与隐私

1. 默认 LOCAL_ONLY，不默认上传记忆库。
2. 敏感信息检测：密码、证件号、财务信息、私密联系人等不写入 Episodic，除非用户显式要求。
3. 记忆可查看、可删除、可导出；删除后检索不再返回。
4. 日志只记录 ID、耗时、token 数，不记录原文；调试模式需显式开启并脱敏。
5. 人格和偏好更新需用户确认；推断偏好标注来源和置信度。

## 10. 可观测与评估

### 10.1 指标

| 指标 | 目标 |
| --- | --- |
| 人格一致性 | 20 条评估对话人工评分 ≥4/5 |
| 10 轮连续对话 | 语气、称呼、边界一致 |
| 跨会话偏好召回 | 3 个显式偏好全部可召回 |
| 情景记忆召回 | 评估集 ≥80% |
| 敏感信息误写 | 0 条 |
| 删除生效 | 删除后检索 100% 不出现 |
| 回读可解释 | 每次回复可列出 used_context |
| 上下文组装延迟 | 本地 <300ms，不含模型推理 |

## 11. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 人格层变成提示词 | Persona Schema + 版本 + 评估集 |
| 记忆乱写 | 候选机制、敏感过滤、用户确认、删除 |
| 云模型泄露 | 默认本地；云增强只发最小上下文 |
| 评估主观 | 固定 20 条对话 + 规则检查 + 人工评分 |
| 过早接工具 | 第一阶段只留接口桩，不实现执行 |
| vecRecall 接口漂移 | M0 冻结 MemoryRetriever，上层只依赖接口 |
| embedding 变更导致返工 | M0 固定模型与维度，写入配置与迁移，启动强校验 |

