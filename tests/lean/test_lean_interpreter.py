import os
import uuid

from prover.lean.verifier import Lean4ServerScheduler


def _load_lean_import():
    proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = os.path.join(proj_root, "prompts", "lean_import.lean")
    with open(path, "r") as f:
        return f.read()


def _run_lean_code(code, timeout=60, memory_limit=10):
    scheduler = Lean4ServerScheduler(
        max_concurrent_requests=1,
        timeout=timeout,
        memory_limit=memory_limit,
        name=str(uuid.uuid4()),
    )
    try:
        request_id_list = scheduler.submit_all_request([dict(code=code, ast=False, tactics=False)])
        outputs_list = scheduler.get_all_request_outputs(request_id_list)
    finally:
        scheduler.close()
    return outputs_list[0]


lean_import = _load_lean_import()
formal_proof = "theorem test:  (16 ∣ 78 + 82) ∧ (16 ∣ 79 + 81) := by sorry"


def test_lean_interpreter():
    out = _run_lean_code(lean_import + formal_proof)
    assert out.get("pass") is True
    assert len(out.get("sorries", [])) == 1

# Run this in repo root:
# PYTHONPATH=. pytest tests/lean/test_lean_interpreter.py