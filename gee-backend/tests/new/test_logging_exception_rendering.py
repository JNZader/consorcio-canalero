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

import logging
import time

import structlog

from app.core.logging import configure_structlog


def _console_renderer() -> object:
    """The renderer the dev (non-JSON) configuration installs on the root handler."""
    configure_structlog(json_format=False, log_level="INFO")
    handler = logging.getLogger().handlers[0]
    processors = handler.formatter.processors
    return processors[-1]


def test_the_dev_console_renderer_does_not_dump_frame_locals() -> None:
    """The exception formatter is the plain one, not rich-with-locals.

    Asserted on the CONFIGURED renderer rather than on the module source, so a
    future refactor that moves the option somewhere else still has to keep the
    behavior.
    """
    try:
        renderer = _console_renderer()
        formatter = renderer._exception_formatter

        assert formatter is structlog.dev.plain_traceback, (
            "the dev ConsoleRenderer fell back to rich's traceback formatter; "
            "its default show_locals=True renders SQLAlchemy locals for every "
            "frame of every logged 500 (BL-RICH-RENDER-500-HANG)"
        )
        assert not isinstance(formatter, structlog.dev.RichTracebackFormatter)
    finally:
        # Leave the process as the suite found it.
        configure_structlog(json_format=False, log_level="INFO")


def test_logging_an_exception_with_fat_locals_is_not_pathologically_slow() -> None:
    """A behavioral floor under the pin above: rendering must stay sub-second.

    Deliberately generous (1 s against a measured 0.01 s) — this asserts the
    absence of a 100x-class regression, not a benchmark, so it will not turn
    into a flaky red on a loaded CI runner.
    """
    configure_structlog(json_format=False, log_level="INFO")
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

    assert elapsed < 1.0, f"rendering one logged exception took {elapsed:.2f}s"
