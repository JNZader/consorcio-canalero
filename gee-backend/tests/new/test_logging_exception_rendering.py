"""BL-RICH-RENDER-500-HANG — the dev console must not pretty-print frame locals.

A 500 is logged through ``app.main``'s catch-all with ``logger.exception``. Under
``ConsoleRenderer``'s DEFAULT exception formatter that means rich renders the
locals of up to 100 frames — SQLAlchemy sessions, engines and result rows in the
geo stacks — turning a 2 ms failure into a multi-second (originally: never
returning) one.

The regression is invisible in ordinary assertions: the response is still a
correct 500, just pathologically slow, so it only ever showed up as "the test
suite got mysteriously slower". Pinned here instead.
"""

import contextlib
import io
import logging
import sys
import time

import pytest
import structlog

from app.core.logging import configure_structlog


# ``configure_structlog`` is process-global: it rebinds ``structlog``'s
# configuration AND replaces the handlers on the root logger plus the three
# uvicorn loggers. Every test here calls it, so every test has to put the
# process back exactly as it found it -- not "call configure again with the
# arguments we guessed the suite was using", which is what an unconditional
# ``configure_structlog(json_format=False, ...)`` in a ``finally`` amounts to.
_TOUCHED_LOGGERS = ("", "uvicorn", "uvicorn.access", "uvicorn.error")


@contextlib.contextmanager
def _logging_state_restored():
    """Snapshot the real logging state, then put it back verbatim."""
    structlog_config = structlog.get_config()
    stdlib_loggers = [logging.getLogger(name) for name in _TOUCHED_LOGGERS]
    stdlib_state = [(logger, list(logger.handlers), logger.level) for logger in stdlib_loggers]
    try:
        yield
    finally:
        structlog.configure(**structlog_config)
        for logger, handlers, level in stdlib_state:
            logger.handlers.clear()
            logger.handlers.extend(handlers)
            logger.setLevel(level)


@pytest.fixture
def dev_console_stdout(monkeypatch):
    """Configure the dev (non-JSON) logging and hand back what it writes.

    ``configure_structlog`` builds its handler as ``StreamHandler(sys.stdout)``,
    binding the stream at configuration time, so replacing ``sys.stdout``
    BEFORE the call is what routes the rendered records into the buffer.
    """
    stream = io.StringIO()
    with _logging_state_restored():
        monkeypatch.setattr(sys, "stdout", stream)
        configure_structlog(json_format=False, log_level="INFO")
        yield stream


def test_the_dev_console_renderer_does_not_dump_frame_locals(dev_console_stdout) -> None:
    """The exception formatter is the plain one, not rich-with-locals.

    Asserted on the CONFIGURED renderer rather than on the module source, so a
    future refactor that moves the option somewhere else still has to keep the
    behavior.
    """
    handler = logging.getLogger().handlers[0]
    renderer = handler.formatter.processors[-1]

    assert renderer._exception_formatter is structlog.dev.plain_traceback, (
        "the dev ConsoleRenderer fell back to rich's traceback formatter; "
        "its default show_locals=True renders SQLAlchemy locals for every "
        "frame of every logged 500 (BL-RICH-RENDER-500-HANG)"
    )


def test_logging_an_exception_with_fat_locals_is_not_pathologically_slow(
    dev_console_stdout,
) -> None:
    """A behavioral floor under the pin above: rendering must stay sub-second.

    Deliberately generous (1 s against a measured 0.01 s) — this asserts the
    absence of a 100x-class regression, not a benchmark, so it will not turn
    into a flaky red on a loaded CI runner.

    The elapsed-time assertion ALONE is not a floor: a logger that renders
    NOTHING is the fastest logger there is, so a silenced handler, a level
    raised above ERROR or a swallowed formatter would all make this test
    greener. The rendered stream is therefore asserted too — the traceback has
    to actually be in the output for the timing to mean anything.
    """
    logger = structlog.get_logger("test.exception.rendering")

    def deep(level: int, payload: list[tuple[int, str]]):
        heavy = {"level": level, "payload": payload, "copy": list(payload)}
        if level == 0:
            raise RuntimeError(f"boom {len(heavy)}")
        return deep(level - 1, payload)

    payload = [(index, "x" * 200) for index in range(50)]

    started = time.monotonic()
    try:
        deep(25, payload)
    except RuntimeError:
        logger.exception("probe")
    elapsed = time.monotonic() - started

    rendered = dev_console_stdout.getvalue()
    assert "probe" in rendered, f"the event itself never reached the stream: {rendered!r}"
    assert "Traceback (most recent call last)" in rendered, (
        f"no traceback was rendered at all, so the timing below proves nothing: {rendered!r}"
    )
    assert "RuntimeError: boom 3" in rendered, (
        f"the exception type/message is missing from the rendered traceback: {rendered!r}"
    )
    # The locals dump is what the pin above forbids; assert its absence in the
    # OUTPUT too, not only in the renderer's configuration.
    assert "xxxxxxxxxxxxxxxxxxxx" not in rendered, (
        "frame locals leaked into the rendered traceback (BL-RICH-RENDER-500-HANG)"
    )

    assert elapsed < 1.0, f"rendering one logged exception took {elapsed:.2f}s"
