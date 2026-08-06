import pytest

from scripts import report_archive_capacity


def test_archive_warning_limit_uses_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAW_ARCHIVE_WARNING_BYTES", raising=False)
    assert report_archive_capacity._warning_limit() == 400_000_000


def test_archive_warning_limit_accepts_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAW_ARCHIVE_WARNING_BYTES", "750000000")
    assert report_archive_capacity._warning_limit() == 750_000_000


@pytest.mark.parametrize("value", ["texto", "0", "9999999"])
def test_archive_warning_limit_rejects_unsafe_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("RAW_ARCHIVE_WARNING_BYTES", value)
    with pytest.raises(RuntimeError):
        report_archive_capacity._warning_limit()
