import copy

from config_merge import deep_merge


def test_does_not_mutate_base_or_override():
    base = {"a": {"b": 1}}
    override = {"a": {"c": 2}}
    base_copy = copy.deepcopy(base)
    override_copy = copy.deepcopy(override)
    deep_merge(base, override)
    assert base == base_copy
    assert override == override_copy


def test_result_does_not_alias_nested_dicts():
    base = {"a": {"b": 1}}
    result = deep_merge(base, {})
    result["a"]["b"] = 999
    assert base["a"]["b"] == 1


def test_none_override_wins():
    base = {"a": {"b": 1}}
    override = {"a": None}
    assert deep_merge(base, override) == {"a": None}


def test_list_replaced_not_merged():
    base = {"a": [1, 2, 3]}
    override = {"a": [4]}
    assert deep_merge(base, override) == {"a": [4]}


def test_dict_replaces_non_dict_base_value():
    base = {"a": 5}
    override = {"a": {"b": 1}}
    assert deep_merge(base, override) == {"a": {"b": 1}}


def test_non_dict_override_replaces_dict_base_value():
    base = {"a": {"b": 1}}
    override = {"a": 5}
    assert deep_merge(base, override) == {"a": 5}


def test_deep_nesting():
    base = {"a": {"b": {"c": 1, "d": 2}}}
    override = {"a": {"b": {"c": 99}}}
    assert deep_merge(base, override) == {"a": {"b": {"c": 99, "d": 2}}}


def test_multiple_keys_independent():
    base = {"x": 1, "y": {"z": 2}}
    override = {"y": {"w": 3}, "q": 4}
    assert deep_merge(base, override) == {"x": 1, "y": {"z": 2, "w": 3}, "q": 4}
