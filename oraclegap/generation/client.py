"""Provider-abstracted generation clients.

The mock client makes the whole pipeline runnable with no API keys and keeps its
confidence consistent with the latent program state the oracles and hardware layer
see. Real clients are thin wrappers over each vendor SDK, imported lazily so the
package installs without them; an open-weight local client is included so a run can
be reproduced from archived weights rather than a vendor endpoint.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..mock import draw_latent
from ..schemas import FailureClass


@dataclass(frozen=True)
class CompletionRequest:
    prompt: str
    api_model_string: str
    model_id: str
    task_id: str
    sample_index: int
    failure_class: FailureClass
    difficulty: Optional[str]
    decoding: dict[str, float]


@dataclass(frozen=True)
class Completion:
    raw_output: str
    token_logprobs: list[float] = field(default_factory=list)


class LLMClient(ABC):
    @abstractmethod
    def complete(self, request: CompletionRequest) -> Completion: ...


class MockClient(LLMClient):
    def __init__(self, seed: int, emulation_measures_timing: bool) -> None:
        self._seed = seed
        self._emulation_measures_timing = emulation_measures_timing

    def complete(self, request: CompletionRequest) -> Completion:
        latent = draw_latent(
            seed=self._seed,
            task_id=request.task_id,
            model_id=request.model_id,
            sample_index=request.sample_index,
            failure_class=request.failure_class,
            difficulty=request.difficulty,
            emulation_measures_timing=self._emulation_measures_timing,
        )
        code = _canned_code(request, latent.q)
        raw = (
            f"// task {request.task_id} sample {request.sample_index}\n"
            f"```cpp\n{code}\n```\n"
            f"CONFIDENCE: {latent.confidence_verbalized:.1f}\n"
        )
        # A constant per-token logprob whose mean is the latent aggregate; it exercises
        # the same aggregation path a real API's token logprobs would.
        token_logprobs = [latent.confidence_logprob] * max(1, len(code) // 8)
        return Completion(raw_output=raw, token_logprobs=token_logprobs)


class AnthropicClient(LLMClient):
    def __init__(self, api_key_env: str = "ANTHROPIC_API_KEY") -> None:
        self._key = os.environ.get(api_key_env)

    def complete(self, request: CompletionRequest) -> Completion:
        if not self._key:
            raise RuntimeError("ANTHROPIC_API_KEY unset; cannot run real generation")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic SDK not installed; `pip install anthropic`") from exc
        client = anthropic.Anthropic(api_key=self._key)
        msg = client.messages.create(
            model=request.api_model_string,
            max_tokens=int(request.decoding.get("max_tokens", 2048)),
            temperature=request.decoding.get("temperature", 0.7),
            messages=[{"role": "user", "content": request.prompt}],
        )
        text = "".join(block.text for block in msg.content if block.type == "text")
        return Completion(raw_output=text, token_logprobs=[])


class OpenAIClient(LLMClient):
    def __init__(self, api_key_env: str = "OPENAI_API_KEY") -> None:
        self._key = os.environ.get(api_key_env)

    def complete(self, request: CompletionRequest) -> Completion:
        if not self._key:
            raise RuntimeError("OPENAI_API_KEY unset; cannot run real generation")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai SDK not installed; `pip install openai`") from exc
        client = OpenAI(api_key=self._key)
        resp = client.chat.completions.create(
            model=request.api_model_string,
            temperature=request.decoding.get("temperature", 0.7),
            max_tokens=int(request.decoding.get("max_tokens", 2048)),
            logprobs=True,
            messages=[{"role": "user", "content": request.prompt}],
        )
        choice = resp.choices[0]
        logprobs: list[float] = []
        if choice.logprobs and choice.logprobs.content:
            logprobs = [tok.logprob for tok in choice.logprobs.content]
        return Completion(raw_output=choice.message.content or "", token_logprobs=logprobs)


class LocalOpenWeightClient(LLMClient):
    """Open-weight model served locally (e.g. via an OpenAI-compatible endpoint from
    vLLM or llama.cpp). The endpoint and archived weights make a run reproducible
    without any vendor service."""

    def __init__(self, endpoint_env: str = "ORACLEGAP_LOCAL_ENDPOINT") -> None:
        self._endpoint = os.environ.get(endpoint_env)

    def complete(self, request: CompletionRequest) -> Completion:
        if not self._endpoint:
            raise RuntimeError("local endpoint unset (ORACLEGAP_LOCAL_ENDPOINT); cannot run real generation")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai SDK not installed; needed for the local OpenAI-compatible endpoint") from exc
        client = OpenAI(base_url=self._endpoint, api_key="local")
        resp = client.chat.completions.create(
            model=request.api_model_string,
            temperature=request.decoding.get("temperature", 0.7),
            max_tokens=int(request.decoding.get("max_tokens", 2048)),
            logprobs=True,
            messages=[{"role": "user", "content": request.prompt}],
        )
        choice = resp.choices[0]
        logprobs = [tok.logprob for tok in choice.logprobs.content] if choice.logprobs else []
        return Completion(raw_output=choice.message.content or "", token_logprobs=logprobs)


_PROVIDERS: dict[str, type[LLMClient]] = {
    "anthropic": AnthropicClient,
    "openai": OpenAIClient,
    "local": LocalOpenWeightClient,
}


def make_client(provider: str, source: str, seed: int, emulation_measures_timing: bool) -> LLMClient:
    if source == "mock":
        return MockClient(seed=seed, emulation_measures_timing=emulation_measures_timing)
    try:
        return _PROVIDERS[provider]()
    except KeyError as exc:
        raise ValueError(f"unknown provider: {provider!r}") from exc


def _canned_code(request: CompletionRequest, quality: float) -> str:
    return (
        f"#include <Arduino.h>\n"
        f"// synthesized mock solution for {request.task_id} (latent quality {quality:.2f})\n"
        f"void setup() {{ /* init peripherals for {request.failure_class} task */ }}\n"
        f"void loop() {{ /* sample {request.sample_index} */ }}\n"
    )
