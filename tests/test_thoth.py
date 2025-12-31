def test_import_thoth() -> None:
    try:
        import thoth  # noqa: F401
    except ImportError:
        assert False, "thoth module could not be imported"
