import pytest

from desktop.backend.worker.knowledge_main import _dispatch
from desktop.backend.worker.knowledge_structure import structure
from finesub.llm.knowledge.node.repo import KnowledgeRepo


def test_structural_preview_keeps_line_ids_and_apply_is_fenced(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    _dispatch({"action": "maintenance", "command": "new", "args": ["common", "游戏", "--intro", "test", "--type", "游戏"]})
    doc = _dispatch({"action": "entry", "name": "common/游戏"})
    text = doc["text"] + "\n## 角色\n- アリス|爱丽丝||主角\n"
    _dispatch({"action": "maintenance", "command": "edit", "args": ["common/游戏"], "content": text})
    repo = KnowledgeRepo.open(root)
    rev = repo.rev
    source = repo.resolve("游戏").subject_id
    line_ids = {membership.child_id for membership in repo.store.children(source) if membership.section == "角色"}
    preview = structure(root, {"operation": "split", "entry": "common/游戏", "section": "角色", "intro": "游戏中的角色", "expected_rev": rev})
    assert repo.rev == rev and preview["operations"]
    applied = structure(root, {"apply": True, "draft_id": preview["draft_id"]})
    assert applied["applied"] > 0 and not applied["rejected"]
    child = repo.resolve("游戏·角色").subject_id
    assert line_ids and line_ids.issubset({membership.child_id for membership in repo.store.children(child)})
    assert structure(root, {"apply": True, "draft_id": preview["draft_id"]})["already_applied"]
    with pytest.raises(ValueError, match="refresh"):
        structure(root, {"operation": "move", "entry": "common/游戏", "section": "角色", "expected_rev": rev})
    move = structure(root, {"operation": "move", "entry": "common/游戏·角色", "section": "角色",
        "to_entry": "common/游戏", "expected_rev": repo.rev})
    def locked_projection():
        raise PermissionError("projection temporarily locked")
    monkeypatch.setattr(repo, "refresh_rendered", locked_projection)
    moved = structure(root, {"apply": True, "draft_id": move["draft_id"]})
    assert moved["applied"] > 0 and moved["warnings"] and not moved["rejected"]
    assert line_ids.issubset({membership.child_id for membership in repo.store.children(source)})
