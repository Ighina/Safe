import os
import uuid

from lean.prover.lean.verifier import Lean4ServerScheduler
from libs.prompts import wrap_lean_import





formal_proof = "theorem test:  (16 ∣ 78 + 82) ∧ (16 ∣ 79 + 81) := by sorry"
complete_proof = """
theorem and_commutative (p q : Prop) : p ∧ q → q ∧ p :=
  fun hpq : p ∧ q =>
  have hp : p := And.left hpq
  have hq : q := And.right hpq
  show q ∧ p from And.intro hq hp
"""

def test_lean_interpreter():
    scheduler = Lean4ServerScheduler(
        max_concurrent_requests=2,
        timeout=60,
        memory_limit=10,
        name=str(uuid.uuid4()),
    )
    request_id_list = scheduler.submit_all_request([
        dict(code=formal_proof, ast=False, tactics=False),
        dict(code=complete_proof, ast=False, tactics=False),
    ])
    outputs_list = scheduler.get_all_request_outputs(request_id_list)
    # print(outputs_list)
    out = outputs_list[0]
    assert out.get("pass") is True
    assert len(out.get("sorries", [])) == 1
    scheduler.close()

# Run this in repo root:
# PYTHONPATH=. pytest tests/lean/test_lean_interpreter.py