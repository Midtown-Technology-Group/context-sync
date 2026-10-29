"""Runtime requirements needed by both installed sync entrypoints."""

from importlib.metadata import requires

from work_context_sync import app, async_pipeline


def test_distribution_declares_httpx_as_runtime_dependency():
    """Ordinary installs must include the HTTP client, without selecting an extra."""
    requirements = requires("mtg-work-context-sync") or []
    assert any(
        requirement.lower().startswith("httpx") and ";" not in requirement
        for requirement in requirements
    )


def test_async_pipeline_is_available_in_installed_package():
    """The CLI must not silently disable its advertised async option."""
    assert app.ASYNC_AVAILABLE is True
    assert app.run_async_sync is async_pipeline.run_async_sync
