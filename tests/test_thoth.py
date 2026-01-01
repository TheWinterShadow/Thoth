import pytest

try:
    import thoth
except ImportError:
    thoth = None


def test_import_thoth() -> None:
    """Test that the thoth module can be imported."""
    if thoth is None:
        pytest.fail("thoth module could not be imported")
