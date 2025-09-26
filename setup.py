# to run pip install -e .
from setuptools import setup, find_packages

setup(
    name="ruqola_libs",
    version="0.1",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "huggingface-hub[cli]",
        "openai",
        "python-dotenv",
        "transformers",
        "loguru",
        "ray[default]",
        "tqdm",
        "pandas",
        "easydict",
        "backoff",
        "httpx[socks]",
        "rank-bm25",
        "hydra-core",
        "sexpdata",
        "pylspclient",
        "pampy",
        "jsonlines",
        "dataclasses-json",
        "parglare",
        "protobuf",
        "tiktoken",
        "accelerate",
        "blobfile",
        "sentencepiece",
        "datasets",
        "vllm",
        "pytest",
    ],
    python_requires=">=3.9",
)
# To install the package, run:
# pip install -e .
# To uninstall the package, run:
# pip uninstall ruqola_libs