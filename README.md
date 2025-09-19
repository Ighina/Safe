# Safe (Ruqola Impl)
This repository modify from the code for the paper: [Safe: Enhancing Mathematical Reasoning in Large Language Models via Retrospective Step-aware Formal Verification](https://arxiv.org/abs/2506.04592), specifying for our own server environment.

## Installation
```
# Install Lean 4.9.0-rc1
## Note: This will install elan, the Lean toolchain manager to your home directory (~/.elan)
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- --default-toolchain v4.9.0-rc1 -y
## Add Lean to PATH
PATH=~/.elan/bin:$PATH
elan toolchain install v4.9.0-rc1

# Building libraries (It takes 10-20 minutes to build mathlib4)
## Install mathlib 
cd mathlib4
lake build
lake build repl
cd - # Project root

## Install Copra
cd copra/src/tools/repl
lake build repl
cd - # Project root
cd copra/data/test/lean4_proj
lake build
cd - # Project root

# Install Python dependencies
## Create a virtual environment (optional but recommended)
python3 -m venv ruqola
source ruqola/bin/activate
pip3 install --no-cache-dir -r requirements.txt

# Optional but recommended: Use the downloaded model weights to avoid repeated downloads
export HF_HOME=/scratch/datasets/.cache/huggingface

# Download datasets
python download.py
```


## Running
Note: The safe paper maintain two modules: the prover and the reasoning model. The prover is Deepseek Prover 1.5. The reasoning model is a large language model (LLM); we adhere to the conventions of the original repository to use vllm. For example, let the model be `openai/gpt-oss-20b`, you can run the vllm server with the following command:
```
CUDA_VISIBLE_DEVICES=1 vllm serve openai/gpt-oss-20b --async-scheduling --port 8000
CUDA_VISIBLE_DEVICES=2 vllm serve deepseek-ai/DeepSeek-Prover-V1.5-RL --port 8001
```

Make sure that the vllm server is running before executing the scripts (and prevent using the same GPU for both the vllm server and the prover). 

```
python collect_trace.py
```

## Paper Reproduction

To reproduce our experiments, execute these four scripts in order. You can modify the configuration at the beginning of each script, including the reasoning model and prover to be used, as well as the dataset and hyperparameters, among other settings.
1. `collect_trace.py` - Collects reasoning traces (train traces for aggregator training, test traces for evaluation)
2. `aggregator.py` - Trains the LSTM aggregator
3. `benchmark.py` - Evaluates SAFE framework performance using test traces
4. `benchmark_ensemble.py` - Tests hyperparameter alpha's impact on framework performance

## Citation
If you find our work useful, please consider citing our paper.

```
@misc{liu2025safe,
      title={Safe: Enhancing Mathematical Reasoning in Large Language Models via Retrospective Step-aware Formal Verification}, 
      author={Chengwu Liu and Ye Yuan and Yichun Yin and Yan Xu and Xin Xu and Zaoyu Chen and Yasheng Wang and Lifeng Shang and Qun Liu and Ming Zhang},
      year={2025},
      eprint={2506.04592},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2506.04592}, 
}
```

