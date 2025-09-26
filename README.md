# Safe (Ruqola Impl)
This repository modify from the code for the paper: [Safe: Enhancing Mathematical Reasoning in Large Language Models via Retrospective Step-aware Formal Verification](https://arxiv.org/abs/2506.04592), specifying for our own server environment.

## Installation
```
# Install Lean 4.9.0-rc1
## Note: This will install elan, the Lean toolchain manager to your home directory (~/.elan)
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- --default-toolchain v4.9.0-rc1 -y
## Add Lean to PATH
PATH=~/.elan/bin:$PATH
elan toolchain install v4.24.0-rc1


# Install Python dependencies
## Create a virtual environment (optional but recommended)
## The pip will install the Lean interpreter automatically
python3 -m venv ruqola
source ruqola/bin/activate
pip3 install -e .

# Optional but recommended: Use the downloaded model weights to avoid repeated downloads
export HF_HOME=/scratch/datasets/.cache/huggingface
```

## Running Tests

**Other function has not yet ready for use. But the Lean interpreter would be enough for most use cases.
Please dig into `tests/lean/test_lean_interpreter.py` for more details of usage.** The original repository author clone the Lean interpreter from deepseek without further modification, leaving heavy but nonnecessary functions unused.

```
# Run tests to verify the installation
pytest tests/lean/test_lean_interpreter.py
```

