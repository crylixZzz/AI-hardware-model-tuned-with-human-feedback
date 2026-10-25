"""k-sample code generation across the configured models and tasks.

Stochasticity is handled by drawing k samples per (model, task); single runs are
never trusted. Every sample records the exact api model string, decoding parameters,
prompt hash, and a UTC request timestamp so a run is reconstructible.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterable

import structlog

from ..config import ModelSpec, RunConfig
from ..oracles.confidence import aggregate_logprobs, parse_verbalized_confidence
from ..schemas import GenerationSample, Source
from ..taskset import TaskMeta
from .client import CompletionRequest, make_client

log = structlog.get_logger(__name__)

_DECODING = {"temperature": 0.7, "top_p": 0.95, "max_tokens": 2048.0}
_CODE_FENCE = re.compile(r"```(?:cpp|c\+\+|c)?\s*\n(.*?)```", re.DOTALL)


def _extract_code(raw_output: str) -> str:
    match = _CODE_FENCE.search(raw_output)
    return match.group(1).strip() if match else raw_output.strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def generate_samples(
    cfg: RunConfig,
    source: Source,
    tasks: Iterable[TaskMeta],
    models: Iterable[ModelSpec],
) -> list[GenerationSample]:
    tasks = list(tasks)
    emu_timing = cfg.emulation_backend in ("qemu", "mock")
    out: list[GenerationSample] = []

    for model in models:
        client = make_client(model.provider, source, cfg.seed, emu_timing)
        for task in tasks:
            prompt = task.spec_path(cfg.repo_root).read_text()
            prompt_hash = _sha(prompt)
            for k in range(cfg.k):
                decoding = {**_DECODING, "sample_seed": float(cfg.seed + k)}
                request = CompletionRequest(
                    prompt=prompt,
                    api_model_string=model.api_model_string,
                    model_id=model.id,
                    task_id=task.id,
                    sample_index=k,
                    failure_class=task.failure_class,
                    difficulty=task.difficulty,
                    decoding=decoding,
                )
                completion = client.complete(request)
                code = _extract_code(completion.raw_output)
                out.append(
                    GenerationSample(
                        sample_id=f"{task.id}:{model.id}:{k}",
                        task_id=task.id,
                        model_id=model.id,
                        api_model_string=model.api_model_string,
                        model_date=model.date,
                        open_weight=model.open_weight,
                        sample_index=k,
                        prompt_hash=prompt_hash,
                        code_hash=_sha(code),
                        raw_output=completion.raw_output,
                        extracted_code=code,
                        confidence_verbalized=parse_verbalized_confidence(completion.raw_output),
                        confidence_logprob=aggregate_logprobs(completion.token_logprobs),
                        decoding=decoding,
                        request_timestamp=datetime.now(timezone.utc),
                        source=source,
                    )
                )
        log.info("generated", model=model.id, tasks=len(tasks), k=cfg.k)
    return out
