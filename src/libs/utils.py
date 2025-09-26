"""Utility helpers for logging, timeouts, and Lean 4 scheduler orchestration.

- trace: decorator adding exception capture and structured logging.
- timeout_handler: run a callable in a separate process with a hard timeout.
- call_scheduler: batch submit requests to Lean4ServerScheduler and collect outputs.
- call_scheduler_with_timeout: wrap call_scheduler with a wall-clock timeout.
"""

from loguru import logger
import uuid
from prover.lean.verifier import Lean4ServerScheduler
import multiprocessing as mp


def trace(func):
    """Decorator that wraps a function to capture exceptions and log calls/results.

    - Uses loguru's @logger.catch to log uncaught exceptions with tracebacks.
    - On success, logs the function name, args/kwargs, and the returned value.
    Returns a wrapped callable with identical signature.
    """

    @logger.catch()
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        logger.info(
            f"Called function {func.__name__} with args {args} and kwargs {kwargs}."
        )
        logger.info(f"Returned {result}.")
        return result

    return wrapper


def timeout_handler(func, args=(), kwargs={}, timeout_duration=1, default=None):
    """Execute `func(*args, **kwargs)` in a separate process with timeout.

    - If execution exceeds `timeout_duration` seconds, kill the process and
      return `default`.
    - If it finishes in time, return the function's result communicated via a Pipe.
    Note: `kwargs` has a mutable default; provide an explicit dict when calling to avoid
    accidental cross-call mutation.
    """

    def target(pipe):
        result = func(*args, **kwargs)
        pipe.send(result)

    parent_pipe, child_pipe = mp.Pipe()
    process = mp.Process(target=target, args=(child_pipe,))
    process.start()
    process.join(timeout_duration)
    if process.is_alive():
        print("Terminating due to timeout.")
        process.kill()
        # process.join()
        return default
    else:
        if parent_pipe.poll():
            return parent_pipe.recv()
        else:
            return default


def call_scheduler(scheduler_input):
    """Submit a batch of Lean requests to Lean4ServerScheduler and return outputs.

    - max_concurrent_requests is set to the batch size (len(scheduler_input)).
    - timeout is per-request (seconds); memory_limit per scheduler settings.
    Returns a list of outputs aligned with the submission order.
    """

    scheduler = Lean4ServerScheduler(
        max_concurrent_requests=len(scheduler_input),
        timeout=60,  # per-request timeout in seconds
        memory_limit=10,  # scheduler-specific units (e.g., GB)
        name=str(uuid.uuid4()),
    )
    request_id_list = scheduler.submit_all_request(scheduler_input)
    outputs_list = scheduler.get_all_request_outputs(request_id_list)

    scheduler.close()
    return outputs_list


def call_scheduler_with_timeout(scheduler_input):
    """Run call_scheduler with a hard 600s wall-clock timeout.

    Returns an empty list on timeout; otherwise the scheduler outputs.
    """
    return timeout_handler(
        call_scheduler, args=(scheduler_input,), timeout_duration=600, default=[]
    )
    