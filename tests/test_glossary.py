from glossary import Glossary


def test_add_remove_update_len():
    g = Glossary()
    g.add("Kubernetes")
    g.add("Kafka", "Kafka")
    g.add("  ", "x")          # blank ignored
    assert len(g) == 2
    g.update({"Redis": "Redis"})
    assert g.terms["Kubernetes"] == "Kubernetes"
    g.remove("Kafka")
    assert "Kafka" not in g.terms


def test_prompt_lines_empty_and_filled():
    assert Glossary().prompt_lines() == ""
    lines = Glossary({"Redis": "Redis"}).prompt_lines()
    assert "Redis -> Redis" in lines


def test_find_terms_word_boundary_and_cjk():
    g = Glossary({"Redis": "Redis", "AI": "AI", "鸿蒙": "HarmonyOS"})
    found = g.find_terms("We use Redis and some AImazing tool")
    assert "Redis" in found and "AI" not in found   # 'AImazing' must not match 'AI'
    assert g.find_terms("这是鸿蒙系统") == ["鸿蒙"]


def test_enforce_counts_present_and_preserved():
    g = Glossary({"Kubernetes": "Kubernetes"})
    r = g.enforce("它运行在 Kubernetes 上", "It runs on Kubernetes")
    assert r.hits == 1 and r.preserved == 1
    r2 = g.enforce("它运行在库伯内特斯上", "It runs on Kubernetes")
    assert r2.hits == 1 and r2.preserved == 0
