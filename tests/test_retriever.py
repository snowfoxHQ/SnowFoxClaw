"""M0-5：MemoryRetriever 契约行为。W2 的 LocalIndex 应直接复用这些用例。"""

from __future__ import annotations

import pytest

from snowfoxclaw.embedding.mock import MockEmbedding
from snowfoxclaw.embedding.provider import EmbeddingDimensionError
from snowfoxclaw.memory.retriever import InMemoryIndex, MemoryItem, MemoryRetriever


def make_index() -> InMemoryIndex:
    return InMemoryIndex(MockEmbedding(dim=32))


def item(
    item_id: str,
    text: str,
    *,
    sensitivity: str = "low",
    session_id: str = "sess_abc123",
    importance: float = 0.5,
) -> MemoryItem:
    return MemoryItem(
        id=item_id,
        text=text,
        metadata={
            "session_id": session_id,
            "type": "fact",
            "sensitivity": sensitivity,
            "importance": importance,
        },
    )


def test_reference_implementation_satisfies_protocol():
    assert isinstance(make_index(), MemoryRetriever)


def test_upsert_returns_id_and_fills_embedding():
    index = make_index()
    assert index.upsert(item("mem_000001", "用户喜欢在晚上工作")) == "mem_000001"
    assert len(index) == 1

    hit = index.search("用户喜欢在晚上工作", top_k=1)
    assert hit[0].id == "mem_000001"


def test_upsert_rejects_embedding_with_wrong_dimension():
    index = make_index()
    broken = MemoryItem(id="mem_000002", text="维度不对", embedding=[0.1, 0.2])
    with pytest.raises(EmbeddingDimensionError):
        index.upsert(broken)


def test_upsert_copies_metadata():
    index = make_index()
    source = item("mem_000003", "元数据隔离")
    index.upsert(source)
    source.metadata["sensitivity"] = "high"
    assert index.search("元数据隔离", top_k=1)[0].metadata["sensitivity"] == "low"


def test_search_ranks_identical_text_first():
    index = make_index()
    index.upsert(item("mem_000010", "每天早上喝咖啡"))
    index.upsert(item("mem_000011", "周末去爬山"))

    hit = index.search("周末去爬山", top_k=1)
    assert hit[0].id == "mem_000011"
    assert hit[0].score == pytest.approx(1.0)


def test_search_respects_top_k():
    index = make_index()
    for offset in range(5):
        index.upsert(item(f"mem_00002{offset}", f"第 {offset} 条记忆"))
    assert len(index.search("记忆", top_k=3)) == 3


def test_search_with_zero_top_k_returns_empty():
    index = make_index()
    index.upsert(item("mem_000030", "任意内容"))
    assert index.search("任意内容", top_k=0) == []


def test_search_on_empty_index_returns_empty():
    assert make_index().search("什么都没有", top_k=5) == []


def test_filters_narrow_by_metadata():
    index = make_index()
    index.upsert(item("mem_000040", "会话一的偏好", session_id="sess_aaa111"))
    index.upsert(item("mem_000041", "会话二的偏好", session_id="sess_bbb222"))

    hit = index.search("偏好", top_k=5, filters={"session_id": "sess_aaa111"})
    assert [entry.id for entry in hit] == ["mem_000040"]


def test_high_sensitivity_excluded_by_default():
    index = make_index()
    index.upsert(item("mem_000050", "身份证号 110101199003071234", sensitivity="high"))
    index.upsert(item("mem_000051", "普通记忆", sensitivity="low"))

    ids = [entry.id for entry in index.search("记忆", top_k=5)]
    assert ids == ["mem_000051"]


def test_high_sensitivity_returned_only_when_explicitly_requested():
    index = make_index()
    index.upsert(item("mem_000060", "高敏感一", sensitivity="high"))
    index.upsert(item("mem_000061", "高敏感二", sensitivity="high"))

    hit = index.search("高敏感", top_k=5, filters={"sensitivity": "high"})
    assert len(hit) == 1
    assert hit[0].metadata["sensitivity"] == "high"


def test_quota_follows_configuration():
    index = InMemoryIndex(MockEmbedding(dim=32), high_sensitivity_quota=2)
    for offset in range(3):
        index.upsert(item(f"mem_00006{offset}", f"高敏感 {offset}", sensitivity="high"))

    hit = index.search("高敏感", top_k=5, filters={"sensitivity": "high"})
    assert len(hit) == 2


def test_negative_quota_rejected():
    with pytest.raises(ValueError):
        InMemoryIndex(MockEmbedding(dim=32), high_sensitivity_quota=-1)


def test_delete_is_idempotent_and_removes_items():
    index = make_index()
    index.upsert(item("mem_000070", "待删除"))
    index.delete(["mem_000070", "mem_不存在"])
    assert len(index) == 0
    assert index.search("待删除", top_k=5) == []


def test_retrieved_item_carries_metadata_for_used_context():
    """used_context.memories_used 需要 id + sensitivity，metadata 必须原样带出。"""
    index = make_index()
    index.upsert(item("mem_000080", "用于回读标注"))

    hit = index.search("回读标注", top_k=1)[0]
    assert hit.metadata["sensitivity"] == "low"
    assert hit.text == "用于回读标注"
