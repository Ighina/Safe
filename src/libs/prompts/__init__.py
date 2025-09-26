# From the same directory:
# (ruqola) pohungyeh@wsserver1:~/projects/safe/ruqola/src/libs/prompts$ ls
# __init__.py  check_answer.txt  divide_steps.txt  formalize.txt  lean_import.lean  zero_shot_cot.txt

with open("src/libs/prompts/lean_import.lean", "r") as f:
    LEAN_IMPORT_SNIPPET = f.read()

with open("src/libs/prompts/formalize.txt", "r") as f:
    FORMALIZE_PROMPT = f.read()

with open("src/libs/prompts/divide_steps.txt", "r") as f:
    DIVIDE_STEPS_PROMPT = f.read()

with open("src/libs/prompts/check_answer.txt", "r") as f:
    CHECK_ANSWER_PROMPT = f.read()

with open("src/libs/prompts/zero_shot_cot.txt", "r") as f:
    ZERO_SHOT_COT_PROMPT = f.read()

def wrap_lean_import(code: str) -> str:
    return LEAN_IMPORT_SNIPPET + "\n\n" + code

