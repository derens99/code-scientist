from semver import compare_versions


def test_equal_versions():
    assert compare_versions("1.2.3", "1.2.3") == 0


def test_major_differs():
    assert compare_versions("2.0.0", "1.9.9") == 1


def test_minor_differs():
    assert compare_versions("1.1.0", "1.2.0") == -1


def test_patch_differs():
    assert compare_versions("1.2.3", "1.2.4") == -1
