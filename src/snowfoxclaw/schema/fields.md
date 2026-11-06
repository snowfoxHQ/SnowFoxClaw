# M0-1a 字段清单（已评审）

状态：2026-11-07 评审通过，M0-1b 依此落地 `schema/*.json`，由 `tests/test_schema.py` 校验两者一致。

与 `docs/architecture.md` 第 5 章一一对应，编号沿用 5.1–5.5。

每个参与校验的表格前有 `<!-- table: 名称 -->` 锚点，pytest 依赖锚点解析，请勿删除或改名。

## 0. 通用约定

| 项 | 约定 |
| --- | --- |
| 命名 | 字段一律 `snake_case`，不出现连字符与大写 |
| 时间 | ISO8601 带时区，统一 UTC，形如 `2026-11-07T10:00:00Z` |
| 时间存储 | SQLite 存 TEXT；必须带时区，否则 `expires_at` 比较会错 |
| ID | `前缀_` + 6 位小写字母数字；前缀固定为 `persona_` `pref_` `mem_` `turn_` `sess_` `vec_` |
| 枚举 | 小写下划线，不接受大小写变体；写入前做规范化校验 |
| 数值区间 | `confidence`、`importance` 均为 float，闭区间 `[0.0, 1.0]` |
| confidence 默认 | `user_explicit` 取 `1.0`，`inferred` 取 `0.5`；冲突比较与召回排序都用这个值 |
| 缺省 | `null` 与「字段不存在」语义等同，落库统一存 NULL |
| 版本 | 库级 `schema_version` 存于 `meta` 表，与 `docs/roadmap.md` 的迁移一一对应 |
| 人格回滚 | 回滚 = 创建新版本（内容复制自旧版本，`version + 1`），`active_version` 永远指向最新；不允许指针回指旧版本 |
| used_context 存储 | 单个 JSON TEXT 列（`used_context_json`），不拆关联表；只支持按 turn 回读，不支持反查「哪些 turn 用了 mem_001」 |
| key 规范化 | trim → 全角转半角 → 英文小写；规范化结果相同视为同一 key |

敏感级沿用 architecture.md 5.6：`low` / `medium` / `high`。`high` 表示**默认不落库**，必须用户显式确认才写入。

## 1. PersonaProfile（5.1）

第一阶段为**单人格**：`id` 恒为 `persona_default`，`version` 单调递增，历史版本全部保留以支持回滚。

<!-- table: persona_profile -->

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

<!-- table: response_style -->

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `format` | string | 否 | ≤200 字符 | 如「先结论后细节」 |
| `emoji` | enum | 否 | `none` / `few` / `normal`，默认 `few` | 表情使用程度 |

**激活规则**：激活版本记录在 `meta` 表的 `persona.active_version`，不放进 profile 行。理由：历史版本需并存，加 `is_active` 会在回滚时同时改多行且易出现双激活。激活前必须 `source = user_confirmed`。

**回滚规则**：回滚到旧版本时读取旧版本内容，写入一行 `version = 当前最大值 + 1` 的新记录，再更新 `active_version`，旧记录一律不改。若允许指针回指旧版本，同一个 `version` 号会对应两段激活历史，`used_context` 回读将无法判断当时用的是哪一份。

## 2. PreferenceItem（5.2）

<!-- table: preference_item -->

| 字段 | 类型 | 必填 | 约束 / 默认 | 敏感级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | string | 是 | `pref_` 前缀 | low | 主键 |
| `domain` | enum | 是 | `schedule` / `communication` / `writing` / `general` | low | 偏好领域，召回时用于筛选 |
| `key` | string | 是 | 1–64 字符，规范化后无首尾空白 | low | 偏好名，如「提醒时间」 |
| `value` | string | 是 | 1–500 字符 | 随内容 | 偏好值，如「晚上11点」 |
| `value_type` | enum | 是 | `text` / `number` / `time` / `bool`，默认 `text` | low | 值类型，冲突比较与召回排序要用 |
| `confidence` | float | 是 | `[0,1]`，显式 `1.0` / 推断 `0.5` | low | 置信度 |
| `sensitivity` | enum | 是 | `low` / `medium` / `high` | low | 分级决定写入策略 |
| `source` | enum | 是 | `user_explicit` / `inferred` | low | 显式说出还是推断 |
| `created_at` | ISO8601 | 是 | 写入时生成 | low | — |
| `last_used_at` | ISO8601 | 否 | 默认 `null` | low | 被组装进上下文时更新，用于排序 |
| `superseded_values` | object[] | 否 | ≤5 项，FIFO，默认 `[]` | medium | 被覆盖的旧值，行内留痕 |

<!-- table: preference_superseded -->

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `value` | string | 是 | 1–500 字符 | 被覆盖的旧值 |
| `confidence` | float | 是 | `[0,1]` | 被覆盖时的置信度 |
| `superseded_at` | ISO8601 | 是 | 写入时生成 | 覆盖发生时间 |

**唯一约束**：`(domain, key)` 唯一，以扩展关键字 `x-unique` 声明在 `preference.json`，W1-3 建表时落成 UNIQUE 约束。

**key 规范化**：写入前 trim、全角转半角、英文小写。`「提醒时间 」` 与 `「提醒时间」` 是同一个 key，规范化在 W1-2 PreferenceService 里实现，schema 层只禁止首尾空白。

**冲突策略**（同 key 再次出现时）：

| 情形 | 处理 |
| --- | --- |
| 新值来自 `user_explicit` | 覆盖 `value`，`confidence` 置 1.0，`source` 升级为显式 |
| 新值来自 `inferred` 且旧为显式 | 不覆盖，仅记录候选，等用户确认 |
| 双方均为 `inferred` | 后推断覆盖前推断，`confidence` 取两者较高值，旧值压入 `superseded_values` |
| 任意情形 `sensitivity = high` | 不自动写入，进待确认列表 |

`superseded_by` 在唯一键下无处安放：同 key 只有一行，旧记录已不存在。因此改为行内 `superseded_values` 数组，效果等同留痕，只是方向从「旧值指向新值」变成「新值持有旧值」。

`value` 的敏感级由内容决定而非 `sensitivity` 字段：`sensitivity` 是分级结论，`value` 是承载文本，写入前都要过第 9 章检测。

## 3. EpisodicMemory（5.3）

<!-- table: episodic_memory -->

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
| `sensitivity` | enum | 是 | `low` / `medium` / `high` | low | `high` 需用户确认且带 `consent` |
| `consent` | object | 否 | `sensitivity = high` 时必填 | low | 用户确认留痕，见下表 |
| `expires_at` | ISO8601 | 否 | 默认 `null` 表示不过期 | low | 到期后检索跳过，不物理删除 |

<!-- table: consent -->

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `confirmed_by` | enum | 是 | `user` | 第一阶段确认者只有用户本人 |
| `confirmed_at` | ISO8601 | 是 | 写入时生成 | 确认时间 |
| `channel` | enum | 是 | `cli` / `api` | 确认渠道，第一阶段实际只会是 `cli` |

**确认形态**：第一阶段没有 UI，确认走 CLI 的 y/n 交互，结果写成 `consent` 子对象，不单开表。日志只记 `mem_id` 与「已确认」这一事实，不记原文。

**high 召回约束**（必读，W2-6 跨会话恢复容易踩）：

- `sensitivity = high` 的记忆默认不进入检索结果，即使用户没说要删。
- 仅在用户当次显式要求时才返回，且 `topK` 配额最多 1 条。
- 进入上下文时在 `used_context.memories_used` 中标注 `sensitivity`，让回读页能显示「本次使用了一条高敏感记忆」。

不加这条约束的后果：用户确认「记住我的身份证号」之后，每一轮对话都召回它，模型每轮都看到，体验上非常吓人。

**删除传播**：删除 memory 只删自身与对应 `vec_*`，不动 `turn_*`。删除 turn 时把引用它的 `raw_ref` 置 `null`，**不级联删除 memory**，因为 `summary` 已脱敏且信息已独立成立。

**索引**：`session_id + ts`、`importance` 倒序、`expires_at`（清理扫描）、`embedding_ref`。

## 4. WorkingContext（5.4）

<!-- table: working_context -->

| 字段 | 类型 | 必填 | 约束 / 默认 | 敏感级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `session_id` | string | 是 | 主键 | low | 一个会话一条 |
| `task_goal` | string | 否 | ≤300 字符，默认 `null` | medium | 当前任务目标 |
| `active_entities` | string[] | 否 | ≤20 项，默认 `[]` | low | 活跃实体 |
| `open_questions` | string[] | 否 | ≤10 项，默认 `[]` | medium | 未决问题 |
| `recent_turns` | string[] | 否 | ≤20 项，FIFO，默认 `[]` | low | 最近 turn id，只存引用 |
| `ttl` | duration | 是 | 默认 `2h`，形如 `30m` / `2h` / `1d` | low | 生存时长**意图**，用户可改 |
| `updated_at` | ISO8601 | 是 | 每次变更刷新 | low | **TTL 计算基准** |
| `expires_at` | ISO8601 | 是 | `updated_at + ttl` | low | 派生值，落库便于批量清理 |

`ttl` 与 `expires_at` 都存，语义不同：`ttl` 是用户意图（「这个上下文活 2 小时」），`expires_at` 是写入时按 `updated_at + ttl` 算出的派生结果。只存 `ttl` 时清理任务要逐行解析 duration 再和当前时间比，只存 `expires_at` 则丢失用户意图、无法回答「为什么是 2 小时」。

## 5. ConversationTurn（5.5）

<!-- table: conversation_turn -->

| 字段 | 类型 | 必填 | 约束 / 默认 | 敏感级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | string | 是 | `turn_` 前缀 | low | 主键 |
| `session_id` | string | 是 | 引用 `sess_*` | low | 所属会话 |
| `ts` | ISO8601 | 是 | 写入时生成 | low | 发生时间 |
| `role` | enum | 是 | `user` / `assistant` | low | 消息角色 |
| `content` | string | 是 | ≤32k 字符，已脱敏 | 随内容 | 正文，落库前过脱敏规则 |
| `persona_version` | int | 是 | 引用 PersonaProfile.version | low | 会话当前激活版本 |
| `used_context` | object | 否 | 仅 assistant 有值，user 必须为 `null` | low | 见下表 |
| `tokens` | object | 否 | 默认 `null`，缺失不阻断 | low | 见下表 |

<!-- table: used_context -->

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `persona_version` | int | 是 | 引用 profile version | 本次组装**实际使用**的版本 |
| `preferences_used` | string[] | 是 | `pref_*`，默认 `[]` | 本次带入的偏好 |
| `memories_used` | object[] | 是 | 默认 `[]` | 本次带入的记忆，见下表 |

<!-- table: memory_ref -->

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | `mem_*` | 记忆 id |
| `sensitivity` | enum | 是 | `low` / `medium` / `high` | 使用时的敏感级，供回读提示 |

<!-- table: tokens -->

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| `prompt` | int | 否 | ≥0 | 提示 token 数 |
| `completion` | int | 否 | ≥0 | 生成 token 数 |

**存储形态**：`used_context` 整体序列化为 JSON 存在 `used_context_json` 列，不拆 `turn_preferences` / `turn_memories` 关联表。第一阶段查询需求只到「按 turn 回读」，没有反查场景，拆表是过度设计。

**回读语义**：删除 memory 后，历史 turn 的 `used_context.memories_used` 不回改。回读时若 `id` 已不存在，显示「已删除的记忆 mem_xxx」——当时确实用了，这是历史事实，抹掉反而让回读失真。

`persona_version` 两处并存是有意为之：顶层跟随会话状态，`used_context` 内记录事实，人格在组装后被更新时两者不同，排障以 `used_context` 为准。

**索引**：`session_id + ts`。

## 6. 评审结论（2026-11-07）

| # | 决策 | 结论 | 落地补充 |
| --- | --- | --- | --- |
| 1 | 第一阶段只支持单人格 | 通过 | `getActive()` 不传 id，内部固定；未来扩展加 `list` / `select`，不预埋 |
| 2 | `tone` 自由文本，限 200 字符 | 通过 | `verbosity` 承担结构化枚举，`tone` 只描述语气，分工不同 |
| 3 | 偏好唯一键 `(domain, key)` | 通过 | 补 key 规范化与 `value_type`，否则「提醒时间」和「提醒的时间」绕过冲突检测 |
| 4 | `sensitivity = high` 允许用户确认后写入 | 通过 | 补 `consent` 子对象、日志只记 id、召回配额 ≤1 且 `used_context` 标注敏感级 |
| 5 | WorkingContext 增加 `updated_at` / `expires_at` | 通过 | `ttl` 保留为意图字段，`expires_at` 为派生存库值，两者都存 |
| 6 | 删除 turn 不级联删 memory | 通过 | 补回读语义：`used_context.memories_used` 不回改，已删记忆显示「已删除的记忆 id」 |

## 7. M0-1b 校验清单

`tests/test_schema.py` 覆盖以下六项，全部可执行：

| 校验 | 方法 |
| --- | --- |
| 字段名与本文一致 | 解析 `<!-- table: -->` 锚点下的表格，与 JSON Schema `properties` 键集合比对 |
| 必填 / 可选一致 | md 表格第 3 列（是/否）与 schema `required` 比对 |
| 唯一约束可执行 | 断言 `preference.json` 的 `x-unique == [["domain", "key"]]`，且两字段都在 `required` |
| 时间格式校验 | `FormatChecker` 校验：无时区串被拒，`Z` 结尾通过 |
| high 记忆留痕 | `if sensitivity = high then required consent`，缺 `consent` 应被拒 |
| used_context 往返 | 构造 turn 实例，`json.dumps` → `json.loads` → 再校验仍通过 |
