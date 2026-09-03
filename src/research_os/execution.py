"""Explicit executor abstraction for local and future production backends."""

from __future__ import annotations

from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol


class ExecutorUnavailableError(RuntimeError):
    pass


class Executor(Protocol):
    def submit(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    value: Any = None
    error: str | None = None
    executor: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalExecutor:
    name = "LocalExecutor"

    def submit(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> ExecutionResult:
        try:
            return ExecutionResult("COMPLETED", function(*args, **kwargs), executor=self.name)
        except Exception as exc:
            return ExecutionResult("FAILED", error=f"{type(exc).__name__}: {exc}", executor=self.name)


class ProcessExecutor:
    name = "ProcessExecutor"

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers

    def submit(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[ExecutionResult]:
        # ProcessPoolExecutor does not execute shell text; callers supply a
        # picklable Python callable and explicit typed arguments.
        pool = ProcessPoolExecutor(max_workers=self.max_workers)
        future = pool.submit(_process_call, function, args, kwargs, self.name)
        future.add_done_callback(lambda _: pool.shutdown(wait=False, cancel_futures=False))
        return future


def _process_call(function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], executor: str) -> ExecutionResult:
    try:
        return ExecutionResult("COMPLETED", function(*args, **kwargs), executor=executor)
    except Exception as exc:
        return ExecutionResult("FAILED", error=f"{type(exc).__name__}: {exc}", executor=executor)


class SlurmExecutor:
    name = "SlurmExecutor"

    def submit(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> ExecutionResult:
        raise ExecutorUnavailableError("SlurmExecutor is an interface only; no scheduler adapter is configured")

