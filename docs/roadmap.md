# SnowFoxClaw 个人 Agent 第一阶段开发路线文档 v0.2

## 1. 总周期与里程碑

总周期约 3 周，含阶段零 3–5 天。

| 里程碑 | 时间 | 交付 |
| --- | --- | --- |
| M0 阶段零 | 第 0 周，3–5 天 | Schema 冻结、评估集、数据分级、接口桩、vecRecall adapter 定义、embedding 选型、目录骨架、依赖清单 |
| M1 人格与偏好 | 第 1 周末 | Persona/Preference 存储与召回、Chat 基础链路 |
| M2 记忆与连续性 | 第 2 周末 | Episodic 写入/检索/删除、跨会话连续性、纯规则提取 |
| M3 评估与验收 | 第 3 周末 | LLM 摘要接入、评估报告、演示、文档、验收 |

## 2. 任务拆解

### 2.1 M0 阶段零（3–5 天）

| ID | 任务 | 产出 | 验收 |
| --- | --- | --- | --- |
| M0-1a | 五个 schema 的字段清单评审（markdown 表格即可） | `schema/fields.md` | 字段名、类型、敏感级评审通过 |
| M0-1b | JSON Schema 落地 | `schema/*.json` | 与 M0-1a 一致，可被 pytest 校验 |
| M0-2 | 定义数据分级与敏感检测规则 | `privacy/data_class.md` | 三类分级、敏感正则清单 |
| M0-3 | 建 20 条人格评估对话 + 10 条记忆评估用例 | `eval/cases.yaml` | 覆盖语气、称呼、边界、禁忌、跨会话 |
| M0-4 | 定义接口桩 | `api/openapi.yaml` | chat/persona/preferences/memories/eval |
| M0-5 | 冻结 vecRecall adapter 接口 | `memory/retriever.py` 协议 | 签名与返回格式评审通过 |
| M0-6 | embedding 模型与维度选型 | `config.default.yaml` + 迁移草案 | 模型、维度、索引方式确定 |
| M0-7 | 建仓库骨架与 CI | 子模块目录、lint、test | 空测试可跑 |
| M0-8 | 依赖清单与本地服务骨架 | `pyproject.toml` 依赖 + `foxclaw serve` 空壳 | uvicorn 能起，`/healthz` 返回 200，CI 通过 |

**为何 M0-1 拆两步**：3–5 天内同时冻结五个 JSON Schema 并写评估集偏紧。M0-1a 只出字段清单，M0-3 与 M0-1a 并行开写（用例里的字段引用先留占位），M0-1b 在 M0 内完成、不阻塞 M0-3；M0-1b 落地后回填 M0-3 的占位字段。这样 M0-3 不会因为 schema 文件没写完而空转。

**并行关系**：M0-1a、M0-2、M0-3、M0-7、M0-8 互不阻塞，可同时推进；M0-1b 依赖 M0-1a；M0-4 依赖 M0-1a；M0-5、M0-6 独立。

M0-8 与 M0-7 可并行，两者都在第 0 周内完成。M0-8 存在的理由：`foxclaw serve` 需要 FastAPI 栈，而当前 `pyproject.toml` 零依赖，不先落地会导致 W1-5 返工。

### 2.2 Week 1：人格 + 偏好 + 基础对话

| ID | 任务 | 产出 | 依赖 |
| --- | --- | --- | --- |
| W1-1 | PersonaService：读写、版本、激活 | 服务 + 单测 | M0-1b |
| W1-2 | PreferenceService：CRUD、相关召回、置信度 | 服务 + 单测 | M0-1b |
| W1-3 | SQLite 存储层 Repository + 迁移（含 ConversationTurn 表） | 存储层 | M0-1b、M0-8 |
| W1-4 | ContextAssembler + PromptBuilder，仅组装 L0+L1 | 组装层 | W1-1、W1-2 |
| W1-5 | Conversation Orchestrator + LLMProvider mock + `foxclaw serve` | `/v1/chat` 可跑 | W1-4 |
| W1-6 | used_context 回读 | 响应字段 + 调试输出 | W1-5 |

周验收：连续 5 轮对话，称呼、语气、边界一致；修改人格后下一轮生效；偏好可召回。

### 2.3 Week 2：情景记忆 + 跨会话连续性

本周明确只做纯规则提取，LLM 摘要放第 3 周（W3-1）。理由：本周验收看的是召回与删除，不是摘要质量。

| ID | 任务 | 产出 | 依赖 |
| --- | --- | --- | --- |
| W2-1 | MemoryService：写入/检索/删除 | 服务 + 单测 | M0-1b |
| W2-2 | LocalIndex + MemoryRetriever 实现 | 检索后端 | M0-5、M0-6 |
| W2-3 | MemoryExtractor 规则版：敏感过滤 + 关键词/模板提取 | 候选生成 | W1-5、W2-1 |
| W2-4 | CandidateStore：待确认 / 低风险自动入 | 候选流程 | W2-3 |
| W2-5 | WorkingContextService：TTL、活跃实体、未决问题 | 服务 | W1-5 |
| W2-6 | 跨会话恢复：新 session 加载偏好 + 相关记忆；ContextAssembler 由 L0+L1 扩到 L2+L3 | 连续性 | W2-1、W2-2、W2-5、W1-4 |
| W2-7 | 记忆查看/删除 API | `/v1/memories` | W2-1 |

周验收：10 轮连续对话记得前面内容；新会话能召回 3 个显式偏好；删除记忆后不再召回；敏感信息不写入。

### 2.4 Week 3：评估、摘要、验收

| ID | 任务 | 产出 | 依赖 |
| --- | --- | --- | --- |
| W3-1 | MemoryExtractor 接入 LLM 摘要 | 摘要链路 | W2-3 |
| W3-2 | EvalHarness 跑 20+10 用例 | 评估报告 | M0-3、W2-7 |
| W3-3 | 人格一致性调优 | prompt / 字段调整 | W3-2 |
| W3-4 | 记忆召回与精确率调优 | topK / importance / 去重策略 | W3-2 |
| W3-5 | 隐私检查：日志脱敏、删除导出 | 检查清单 | W2-7 |
| W3-6 | 演示脚本与文档 | demo + README | W3-3、W3-4、W3-5 |
| W3-7 | 验收评审 | 验收记录 | W3-1–W3-6 |

W3-6 与 W3-7 的依赖方向在此修正：上一稿写成 W3-6 依赖 W3-7、W3-7 依赖 W3-2–6，构成循环，无法排期。正确方向是文档先成型（W3-6），再进验收评审（W3-7）。

## 3. 验收标准

必须全部满足：

1. 连续 10 轮对话，Agent 记得前面说过的事实，语气一致。
2. 跨会话新开对话，能召回至少 3 个显式偏好。
3. 20 条人格评估对话人工评分平均 ≥4/5。
4. 10 条记忆评估用例召回率 ≥80%。
5. 敏感信息误写 0 条。
6. 删除记忆后检索 100% 不再出现。
7. 每次回复能列出 used_context：persona_version、preferences_used、memories_used。
8. 本地上下文组装延迟 <300ms（不含模型推理）。
9. 默认 LOCAL_ONLY，日志不落原文。

## 4. 交付物

- `docs/architecture.md`、`docs/roadmap.md`
- Schema：Persona / Preference / Episodic / WorkingContext / ConversationTurn（`schema/*.json`）
- `MemoryRetriever` 协议 + `LocalIndex` 实现
- `EmbeddingProvider` 协议 + Mock 实现
- OpenAPI：chat / persona / preferences / memories / eval
- 可运行 `foxclaw serve` + `foxclaw chat` + `foxclaw context show`
- 评估集（`eval/cases.yaml`）与评估报告
- 演示脚本：人格连续、跨会话记忆、删除生效、敏感拦截
- 第二阶段接口桩：ActionProposal、ConfirmationGate、TriggerEvent、AuditEvent，仅定义不实现

## 5. 风险与应对

| 风险 | 应对 |
| --- | --- |
| 人格做成提示词 | Schema 先行，M0-1a / M0-1b 不通过不开工 |
| 记忆过度写入 | 候选机制 + 敏感过滤 + 用户可删 |
| 评估主观 | 固定用例 + 规则检查 + 人工评分 |
| 模型不稳定 | LLMProvider mock 用于测试，分离模型能力与架构能力 |
| 范围膨胀 | 第一阶段不接工具、不做主动触发，只留桩 |
| 第 2 周排期超载 | LLM 摘要推迟到第 3 周，第 2 周只跑规则链路 |
| vecRecall 接口返工 | M0-5 冻结协议，上层只依赖接口 |
| embedding 返工 | M0-6 固定模型与维度 |
| serve 依赖未落地导致 W1-5 返工 | M0-8 提前把 FastAPI 栈与空壳服务跑通 |

## 6. 第二阶段衔接点

第一阶段结束时必须留下：

- `ToolRegistry` 空接口
- `ActionProposal` 数据结构
- `ConfirmationGate` 桩：确认 + 回读 + 幂等键字段
- `TriggerEvent` 桩：定时 / 事件 / 条件三类枚举
- `AuditEvent` 最小字段：who、what、when、result、reversible

第二阶段再从「轻量契约 + 工具接入」开始，不回头改第一阶段人格与记忆 Schema。

