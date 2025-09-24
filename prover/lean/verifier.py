import os
import time
import json
import ctypes
import resource
import tempfile
import traceback
import subprocess
import multiprocessing as mp
from pprint import pprint

from prover.lean.ast_parser import lean4_parser
from prover.workers import ProcessScheduler
from prover.utils import AttrDict

# Paths and defaults
HOME_DIR = os.path.expanduser("~")
DEFAULT_LAKE_PATH = os.environ.get("LAKE_BIN", f"{HOME_DIR}/.elan/bin/lake")
_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
DEFAULT_LEAN_WORKSPACE = os.environ.get("LEAN_WORKSPACE", os.path.join(_REPO_ROOT, "lean"))


def verify_lean4_file(
    code: str,
    lake_path: str = DEFAULT_LAKE_PATH,
    lean_workspace: str = DEFAULT_LEAN_WORKSPACE,
    last_env=None,
    verbose: bool = False,
    timeout: int = 300,
    allTactics: bool = False,
    ast: bool = False,
    premises: bool = False,
    tactics: bool = False,
):
    """Verify Lean 4 code using `lake exe repl` in the given workspace.

    Returns dict with keys: pass, complete, sorries, tactics, errors, warnings,
    infos, system_messages, system_errors, ast, verified_code, verify_time.
    """
    command = dict(
        cmd=code, allTactics=allTactics, ast=ast, tactics=tactics, premises=premises
    )
    if last_env is not None:
        command.update(env=last_env)
    message_str = json.dumps(command, ensure_ascii=False)
    if verbose:
        print(message_str)

    start_time = time.time()
    system_messages = ""
    try:
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as temp_file:
            temp_file.write(message_str + "\r\n\r\n")
            temp_file.seek(0)
            outputs = subprocess.run(
                [lake_path, "exe", "repl"],
                stdin=temp_file,
                capture_output=True,
                text=True,
                cwd=lean_workspace,
                timeout=timeout,
            )

        try:
            result_raw = json.loads(outputs.stdout)
        except json.JSONDecodeError:
            system_messages = (outputs.stderr or "") + ("\n" + outputs.stdout if outputs.stdout else "")
            raise

        ast_results = (
            lean4_parser(code, result_raw["ast"]) if ast and result_raw.get("ast") else {}
        )
        result = {
            "sorries": result_raw.get("sorries", []),
            "tactics": result_raw.get("tactics", []),
            "errors": [m for m in result_raw.get("messages", []) if m.get("severity") == "error"],
            "warnings": [m for m in result_raw.get("messages", []) if m.get("severity") == "warning"],
            "infos": [m for m in result_raw.get("messages", []) if m.get("severity") == "info"],
            "system_messages": system_messages or (outputs.stderr or ""),
            "system_errors": None,
            "ast": ast_results,
            "verified_code": code,
        }
        result["pass"] = not result["errors"]
        result["complete"] = (
            result["pass"]
            and not result["sorries"]
            and not any(
                "declaration uses 'sorry'" in (w.get("data", "")) or "failed" in (w.get("data", ""))
                for w in result["warnings"]
            )
        )
    except Exception:
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


if __name__ == "__main__":
    sample_path = os.path.join(
        _REPO_ROOT, "mathlib4", ".lake", "packages", "REPL", "test", "aime_1983_p9.code.in"
    )
    with open(sample_path, "r", encoding="utf-8") as f:
        code = f.read()
    lean4_scheduler = Lean4ServerScheduler(max_concurrent_requests=1, timeout=300, memory_limit=10, name="verifier")
    request_id_list = lean4_scheduler.submit_all_request([dict(code=code, ast=True, tactics=True)])
    outputs_list = lean4_scheduler.get_all_request_outputs(request_id_list)
    lean4_scheduler.close()
    pprint(outputs_list)
