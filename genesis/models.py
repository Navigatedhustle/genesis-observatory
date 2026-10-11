"""Trusted routing registry, never an inhabitant tool or prompt component."""

REGISTRY = {
    "llama": {
        "family": "Llama",
        "model": "llama3.1:8b",
        "digest": "46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e",
        "version": "3.1",
        "quantization": "Q4_K_M",
        "format": "GGUF",
        "runtime_version": "0.32.9",
        "runtime": "Ollama",
        "endpoint": "http://127.0.0.1:11434/api/chat",
        "context_limit": 6144,
        "temperature": 0,
        "max_tokens": 700,
        "ownership": "shared existing Ollama; no service changes",
        "weight_gib": 4.583,
    },
    "qwen": {
        "family": "Qwen",
        "model": "models/generation/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf",
        "version": "3.6-35B-A3B",
        "quantization": "UD-Q4_K_XL (server reports Q4_K Medium)",
        "format": "GGUF",
        "runtime_build": "b10950-ad6c66839",
        "runtime": "llama.cpp",
        "endpoint": "http://127.0.0.1:8081/v1/chat/completions",
        "context_limit": 6144,
        "server_context": 16384,
        "temperature": 0,
        "max_tokens": 700,
        "ownership": "already resident CampusCompass runtime; stateless requests only",
        "gpu_resident_measured_gib": 21.008,
        "weight_gib": 21.274,
    },
}


def request(route, messages, schema):
    r = REGISTRY[route]
    if route == "llama":
        return {
            "model": r["model"],
            "stream": False,
            "keep_alive": -1,
            "format": schema,
            "options": {
                "num_ctx": r["context_limit"],
                "num_predict": r["max_tokens"],
                "temperature": r["temperature"],
            },
            "messages": messages,
        }
    return {
        "model": r["model"],
        "messages": messages,
        "max_tokens": r["max_tokens"],
        "temperature": r["temperature"],
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "research", "strict": True, "schema": schema},
        },
    }


def normalize(route, raw):
    if route == "llama":
        return raw
    timing = raw.get("timings", {})
    return {
        "message": {"content": raw["choices"][0]["message"]["content"]},
        "eval_count": raw["usage"]["completion_tokens"],
        "prompt_eval_count": raw["usage"]["prompt_tokens"],
        "eval_duration": int(timing.get("predicted_ms", 1) * 1e6),
        "wire_response": raw,
    }


async def monitor(g):
    """Read-only runtime residency; no world measurements or implicit physics changes."""
    import asyncio
    import time

    import httpx

    while True:
        status = {}
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            for route in ["llama", "qwen"]:
                try:
                    if route == "llama":
                        response = await client.get("http://127.0.0.1:11434/api/ps")
                        response.raise_for_status()
                        loaded = [
                            m
                            for m in response.json().get("models", [])
                            if m["name"] == REGISTRY[route]["model"]
                        ]
                        status[route] = {
                            "runtime_available": True,
                            "resident": bool(loaded),
                            "gpu_gib": round(
                                loaded[0].get("size_vram", 0) / 1073741824, 3
                            )
                            if loaded
                            else 0,
                            "checked": time.time(),
                        }
                    else:
                        response = await client.get("http://127.0.0.1:8081/health")
                        status[route] = {
                            "runtime_available": response.status_code == 200,
                            "resident": response.status_code == 200,
                            "gpu_gib_measured": REGISTRY[route][
                                "gpu_resident_measured_gib"
                            ],
                            "checked": time.time(),
                        }
                except Exception as exc:
                    status[route] = {
                        "runtime_available": False,
                        "resident": False,
                        "failure": type(exc).__name__,
                        "checked": time.time(),
                    }
        g.store.put("runtime_status", status)
        await asyncio.sleep(10)
