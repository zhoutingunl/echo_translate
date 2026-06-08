from replay import REPLAY_SCRIPTS


def test_scripts_well_formed():
    assert REPLAY_SCRIPTS, "expected at least one replay script"
    for key, script in REPLAY_SCRIPTS.items():
        assert script["title"] and script["lang_code"]
        assert script["steps"], f"{key} has no steps"
        seen_ids = 0
        for step in script["steps"]:
            assert step["action"] in {"final", "interim", "revise"}
            assert "text" in step and isinstance(step["t"], int)
            if step["action"] == "final":
                seen_ids += 1
            if step["action"] == "revise":
                # a revise must target an already-emitted final segment id
                assert 1 <= step["seg"] <= seen_ids
