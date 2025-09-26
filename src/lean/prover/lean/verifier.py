import os
import time
import json
import ctypes
import resource
import traceback
import subprocess
import multiprocessing as mp
from pprint import pprint

from .ast_parser import lean4_parser
from ..workers import ProcessScheduler
from ..utils import AttrDict

# Paths and defaults
HOME_DIR = os.path.expanduser("~")
DEFAULT_LAKE_PATH = os.environ.get("LAKE_BIN", f"{HOME_DIR}/.elan/bin/lake")
_THIS_DIR = os.path.dirname(__file__)
_SRC_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
DEFAULT_LEAN_WORKSPACE = os.environ.get("LEAN_WORKSPACE", os.path.join(_SRC_ROOT, "lean"))

assert os.path.exists(DEFAULT_LEAN_WORKSPACE), f"LEAN_WORKSPACE path {DEFAULT_LEAN_WORKSPACE} does not exist"

def verify_lean4_file(
    code: str,
    lake_path: str = DEFAULT_LAKE_PATH,
    lean_workspace: str = DEFAULT_LEAN_WORKSPACE,
    last_env=None,
    timeout: int = 300,
    allTactics: bool = False,
    ast: bool = False,
    premises: bool = False,
    tactics: bool = False,
):
    start_time = time.time()

    def _build_command() -> str:
        payload = {
            "cmd": code,
            "allTactics": allTactics,
            "ast": ast,
            "tactics": tactics,
            "premises": premises,
        }
        if last_env is not None:
            payload["env"] = last_env
        return json.dumps(payload, ensure_ascii=False)

    request_str = _build_command()
    
    system_messages = ""
    try:
        proc = subprocess.run(
            [lake_path, "exe", "repl"],
            input=request_str,
            capture_output=True,
            text=True,
            cwd=lean_workspace,
            timeout=timeout,
        )
        raw = json.loads(proc.stdout)
        ast_results = lean4_parser(code, raw.get("ast", [])) if (ast and raw.get("ast")) else {}

        errors = [m for m in raw.get("messages", []) if m.get("severity") == "error"]
        warnings = [m for m in raw.get("messages", []) if m.get("severity") == "warning"]
        infos = [m for m in raw.get("messages", []) if m.get("severity") == "info"]

        result = {
            "sorries": raw.get("sorries", []),
            "tactics": raw.get("tactics", []),
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "system_messages": system_messages or (proc.stderr or ""),
            "system_errors": None,
            "ast": ast_results,
            "verified_code": code,
            "pass": len(errors) == 0,
        }
        result["complete"] = (
                len(errors) == 0
                and not result["sorries"]
                and not any(
                    ("declaration uses 'sorry'" in (w.get("data", ""))) or ("failed" in (w.get("data", "")))
                    for w in warnings
                )
            )
    except Exception as e:
        result = {
            "pass": False,
            "complete": False,
            "system_errors": traceback.format_exc(),
            "system_messages": system_messages,
        }
        

    result["verify_time"] = time.time() - start_time
    return result


class Lean4ServerProcess(mp.Process):
    def __init__(self, idx, task_queue, request_statuses, lock, extra_args=AttrDict()):
        super().__init__()
        self.idx = idx
        self.task_queue = task_queue
        self.request_statuses = request_statuses
        self.lock = lock
        self.extra_args = extra_args

        self.timeout = extra_args.get("timeout", 300)
        self.memory_limit = extra_args.get("memory_limit", -1)
        self.last_output_time = mp.Value(ctypes.c_double, time.time())
        self.complete_count = mp.Value(ctypes.c_int, 0)

    def run(self):
        if self.memory_limit > 0:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.memory_limit * (1000**3), self.memory_limit * (1000**3)),
            )
        while True:
            inputs = self.task_queue.get()
            if inputs is None:
                break
            for _, request_id, task in inputs:
                if isinstance(task, str):
                    task = dict(code=task)
                if "timeout" not in task:
                    task["timeout"] = self.timeout
                result = verify_lean4_file(**task)
                if len(result.get("system_messages", "")) > 0:
                    retry_start = time.time()
                    while (
                        "lean::exception: failed to create thread" in result.get("system_messages", "")
                        or "std::bad_alloc: std::bad_alloc" in result.get("system_messages", "")
                        or "Cannot allocate memory" in result.get("system_messages", "")
                    ) and time.time() - retry_start < self.timeout:
                        time.sleep(0.1)
                        result = verify_lean4_file(**task)
                with self.lock:
                    self.request_statuses[request_id] = result
                    self.last_output_time.value = time.time()
                    self.complete_count.value += 1


class Lean4ServerScheduler(ProcessScheduler):
    def __init__(self, max_concurrent_requests=64, timeout=300, memory_limit=-1, name="verifier"):
        super().__init__(batch_size=1, name=name)

        self.processes = [
            Lean4ServerProcess(
                idx=idx,
                task_queue=self.task_queue,
                request_statuses=self.request_statuses,
                lock=self.lock,
                extra_args=AttrDict(timeout=timeout, memory_limit=memory_limit),
            )
            for idx in range(max_concurrent_requests)
        ]
        for p in self.processes:
            p.start()

        self.timeout = timeout
        self._running_monitor = mp.Value(ctypes.c_bool, True)
        self._monitor_process = mp.Process(target=self._monitor)
        self._monitor_process.start()

    def _monitor(self):
        while self._running_monitor.value:
            time.sleep(1.0)
            try:
                subprocess.run(
                    ["killall", "repl", f"--older-than={int(self.timeout) + 600}s"],
                    capture_output=True,
                    check=False,
                )
            except Exception:
                pass

    def close(self):
        super().close()
        for p in self.processes:
            p.join()
        self._running_monitor.value = False
        self._monitor_process.join()


