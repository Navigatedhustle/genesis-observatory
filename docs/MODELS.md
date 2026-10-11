# Models, data and asset retrieval

Local Ollama `llama3.1:8b`, `llama3.1:70b`, and the current CampusCompass generation endpoint are referenced in `genesis/models.py`. Obtain models only from their upstream distributors after reviewing licenses. The ecology and unit suite do not require model weights.

Runtime downloads and external account connections are not automatic. Review the upstream model card/license, acquire assets using its official instructions, pin repository revision and record SHA-256 before use. Large binary assets stay outside Git, including Git LFS. The local operator map records already-installed paths for recovery; those paths are not uploaded.

Atlas synthetic data: run its seed-42 generator. CampusCompass fixtures and Beat the Guard missions contain fictional records. Genesis creates a fresh simulated world. Other missing input datasets/media must be supplied only with confirmed rights and synthetic/approved contents.

License references: [Meta Llama 3.1](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/blob/main/LICENSE), [Ultralytics licensing](https://www.ultralytics.com/license), [llama.cpp](https://github.com/ggml-org/llama.cpp), and locally retained model cards/manifests where supplied. Model terms are distinct from application source rights.
