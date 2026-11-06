# M0-1a 字段清单（待评审）

本文件是 M0-1a 的产出，用于**冻结字段名、类型、敏感级**。M0-1b 依据本文件生成 `schema/*.json` 并由 pytest 校验两者一致。

与 `docs/architecture.md` 第 5 章一一对应，编号沿用 5.1–5.5。

评审通过前的任何字段改动都在本文件进行，不直接改 architecture.md。

## 0. 通用约定

| 项 | 约定 |
| --- | --- |
| 命名 | 字段一律 `snake_case`，不出现连字符与大写 |
| 时间 | ISO8601 带时区，统一 UTC，形如 `2026-11-07T10:00:00Z` |
| ID | `前缀_` + 6 位 base32 随机串；前缀固定为 `persona_` `pref_` `mem_` `turn_` `sess_` `vec_` |
| 枚举 | 小写下划线，不接受大小写变体；写入前做规范化校验 |
| 数值区间 | `confidence`、`importance` 均为 float，闭区间 `[0.0, 1.0]` |
| 缺省 | `null` 与「字段不存在」语义等同，落库统一存 NULL |
| 版本 | 库级 `schema_version` 存于 `meta` 表，与 `docs/roadmap.md` 的迁移一一对应 |

敏感级沿用 architecture.md 5.6：`low` / `medium` / `high`。`high` 表示**默认不落库**，必须用户显式确认才写入。

## 1. PersonaProfile（5.1）

第一阶段为**单人格**：`id` 恒为 `persona_default`，`version` 单调递增，历史版本全部保留以支持回滚。

| 字段 | 类型 | 必填 | 约束 / 默认 | 敏感级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | string | 是 | 固定 `persona_default` | low | 主键之一 |
| `version` | int | 是 | ≥1，同 id 内唯一 | low | 主键之一，用户确认后 +1 |
| `display_name` | string | 是 | 1–32 字符 | medium | 用户称呼，可能含真名 |
| `tone` | string | 是 | 1–200 字符 | low | 语气描述，**自由文本不枚举** |
| `verbosity` | enum | 是 | `short` / `medium` / `long`，默认 `medium` | low | 回复长度倾向 |
| `language` | string | 是 | BCP-47，默认 `zh-CN` | low | 回复语言 |
| `values` | string[] | 否 | ≤20 项，每项 ≤100 字符，默认 `[]` | medium | 价值观约束 |
| `boundaries` | string[] | 否 | ≤20 项，每项 ≤100 字符，默认 `[]` | medium | 行为边界 |
| `taboos` | string[] | 否 | ≤20 项，每项 ≤100 字符，默认 `[]` | low | 禁忌表达 |
| `response_style` | object | 否 | 见下表，默认 `{}` | low | 输出格式偏好 |
| `created_at` | ISO8601 | 是 | 写入时生成 | low | 版本创建时间 |
| `updated_at` | ISO8601 | 是 | 写入时生成 | low | 最后一次修改 |
| `source` | enum | 是 | `user_confirmed` / `imported` / `default` | low | 来源，非 `user_confirmed` 不激活 |

`response_style` 子字段：

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `format` | string | 否 | ≤200 字符 | 如「先结论后细节」 |
| `emoji` | enum | 否 | `none` / `few` / `normal`，默认 `few` | 表情使用程度 |

**激活规则**：激活版本记录在 `meta` 表的 `persona.active_version`，不放进 profile 行。理由：历史版本需并存，加 `is_active` 会在回滚时同时改多行且易出现双激活。激活前必须 `source = user_confirmed`。

## 2. PreferenceItem（5.2）

| 字段 | 类型 | 必填 | 约束 / 默认 | 敏感级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | string | 是 | `pref_` 前缀 | low | 主键 |
| `domain` | enum | 是 | `schedule` / `communication` / `writing` / `general` | low | 偏好领域，召回时用于筛选 |
| `key` | string | 是 | 1–64 字符 | low | 偏好名，如「提醒时间」 |
| `value` | string | 是 | 1–500 字符 | 随内容 | 偏好值，如「晚上11点」 |
| `confidence` | float | 是 | `[0,1]`，默认由 source 决定 | low | 置信度 |
| `sensitivity` | enum | 是 | `low` / `medium` / `high` | low | 分级决定写入策略 |
| `source` | enum | 是 | `user_explicit` / `inferred` | low | 显式说出还是推断 |
| `created_at` | ISO8601 | 是 | 写入时生成 | low | — |
| `last_used_at` | ISO8601 | 否 | 默认 `null` | low | 被组装进上下文时更新，用于排序 |

**唯一约束**：`(domain, key)` 唯一。

**冲突策略**（同 key 再次出现时）：

| 情形 | 处理 |
| --- | --- |
| 新值来自 `user_explicit` | 覆盖 `value`，`confidence` 置 0.95，`source` 升级为显式 |
| 新值来自 `inferred` 且旧为显式 | 不覆盖，仅记录候选，等用户确认 |
| 双方均为 `inferred` | `value` 取新值，`confidence` 取两者较高值 |
| 任意情形 `sensitivity = high` | 不自动写入，进待确认列表 |

`value` 的敏感级由内容决定而非 `sensitivity` 字段：`sensitivity` 是分级结论，`value` 是承载文本，写入前都要过第 9 章检测。

## 3. EpisodicMemory（5.3）

| 字段 | 类型 | 必填 | 约束 / 默认 | 敏感级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | string | 是 | `mem_` 前缀 | low | 主键 |
| `session_id` | string | 是 | 引用 `sess_*` | low | 产生该记忆的会话 |
| `ts` | ISO8601 | 是 | 写入时生成 | low | 事件时间，也是创建时间 |
| `type` | enum | 是 | `event` / `fact` / `preference_evidence` / `task` | low | 记忆类型 |
| `summary` | string | 是 | 1–500 字符，**已脱敏** | medium | 摘要正文，不存原文 |
| `entities` | string[] | 否 | ≤20 项，每项 ≤50 字符，默认 `[]` | low | 用于召回加权 |
| `raw_ref` | string | 否 | 引用 `turn_*`，默认 `null` | medium | 原文指针，非原文本身 |
| `embedding_ref` | string | 否 | 引用 `vec_*`，默认 `null` | low | 向量索引键；无向量时为 null |
| `importance` | float | 是 | `[0,1]`，默认 0.5 | low | 召回排序权重 |
| `confidence` | float | 是 | `[0,1]` | low | 提取置信度 |
| `sensitivity` | enum | 是 | `low` / `medium` / `high` | low | `high` 不落库 |
| `expires_at` | ISO8601 | 否 | 默认 `null` 表示不过期 | low | 到期后检索跳过，不物理删除 |

**删除传播**：删除 memory 只删自身与对应 `vec_*`，不动 `turn_*`。删除 turn 时把引用它的 `raw_ref` 置 `null`，**不级联删除 memory**，因为 `summary` 已脱敏且信息已独立成立。

**索引**：`session_id + ts`、`importance` 倒序、`expires_at`（清理扫描）、`embedding_ref`。

## 4. WorkingContext（5.4）

| 字段 | 类型 | 必填 | 约束 / 默认 | 敏感级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `session_id` | string | 是 | 主键 | low | 一个会话一条 |
| `task_goal` | string | 否 | ≤300 字符，默认 `null` | medium | 当前任务目标 |
| `active_entities` | string[] | 否 | ≤20 项，默认 `[]` | low | 活跃实体 |
| `open_questions` | string[] | 否 | ≤10 项，默认 `[]` | medium | 未决问题 |
| `recent_turns` | string[] | 否 | ≤20 项，FIFO，默认 `[]` | low | 最近 turn id，只存引用 |
| `ttl` | duration | 是 | 默认 `2h`，形如 `30m` / `2h` / `1d` | low | 生存时长配置 |
| `updated_at` | ISO8601 | 是 | 每次变更刷新 | low | **TTL 计算基准** |
| `expires_at` | ISO8601 | 是 | `updated_at + ttl` | low | 落库便于批量清理 |

`updated_at` 与 `expires_at` 为本次评审新增：原 5.4 只有 `ttl`，无基准时间则无法判断过期，清理任务无处下手。

## 5. ConversationTurn（5.5）

| 字段 | 类型 | 必填 | 约束 / 默认 | 敏感级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | string | 是 | `turn_` 前缀 | low | 主键 |
| `session_id` | string | 是 | 引用 `sess_*` | low | 所属会话 |
| `ts` | ISO8601 | 是 | 写入时生成 | low | 发生时间 |
| `role` | enum | 是 | `user` / `assistant` | low | 消息角色 |
| `content` | string | 是 | ≤32k 字符，已脱敏 | 随内容 | 正文，落库前过脱敏规则 |
| `persona_version` | int | 是 | 引用 PersonaProfile.version | low | 会话当前激活版本 |
| `used_context` | object | 否 | 仅 assistant 有值，user 为 `null` | low | 见下表 |
| `tokens` | object | 否 | 默认 `null`，缺失不阻断 | low | 见下表 |

`used_context` 子字段：

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `persona_version` | int | 是 | 引用 profile version | 本次组装**实际使用**的版本 |
| `preferences_used` | string[] | 是 | `pref_*`，默认 `[]` | 本次带入的偏好 |
| `memories_used` | string[] | 是 | `mem_*`，默认 `[]` | 本次带入的记忆 |

`tokens` 子字段：`prompt`（int，≥0）、`completion`（int，≥0），均可缺省。

`persona_version` 两处并存是有意为之：顶层跟随会话状态，`used_context` 内记录事实，人格在组装后被更新时两者不同，排障以 `used_context` 为准。

**索引**：`session_id + ts`。

## 6. 待你拍板的 6 个点

| # | 决策 | 我的建议 | 影响 |
| --- | --- | --- | --- |
| 1 | 第一阶段是否只支持单人格 | 是，`id` 固定 `persona_default` | 多人格要加 `owner` 维度，表结构与 API 全变 |
| 2 | `tone` 用自由文本还是枚举 | 自由文本，长度限 200 | 枚举会限制表达；自由文本依赖 prompt 质量 |
| 3 | 偏好唯一键 `(domain, key)` 是否成立 | 成立，按上表冲突策略 upsert | 若允许同 key 多条，召回时需额外排序规则 |
| 4 | `sensitivity = high` 是否允许用户确认后写入 | 允许，但必须显式确认并留记录 | 一律不写会让「记住我的身份证号」这类合理需求无法满足 |
| 5 | WorkingContext 增加 `updated_at` / `expires_at` | 加 | 不加则 TTL 无法落地，W2-5 会卡 |
| 6 | 删除 turn 是否级联删 memory | 不级联，仅把 `raw_ref` 置 null | 级联会误删已独立成立的脱敏摘要 |

确认这 6 点后我出 M0-1b 的 JSON Schema 与 pytest 一致性校验。
