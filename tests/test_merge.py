from storycodex.merge import merge


def test_merge_scalars_objects_arrays():
    base = {
        "title": "Base",
        "meta": {"a": 1, "b": 2},
        "tags": ["one", "two"],
        "items": [{"id": 1}],
    }
    override = {
        "title": "Override",
        "meta": {"b": 3, "c": 4},
        "tags": ["two", "three"],
        "items": [{"id": 1}, {"id": 2}],
    }

    merged = merge(base, override)

    assert merged["title"] == "Override"
    assert merged["meta"] == {"a": 1, "b": 3, "c": 4}
    assert merged["tags"] == ["one", "two", "three"]
    assert merged["items"] == [{"id": 1}, {"id": 2}]
