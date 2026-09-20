from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass

from ai_provider import (
    AIMessage,
    AIRequest,
    ChatClient,
    MessageRole,
    PrivacyClass,
    ensure_ollama_server,
)
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.factory import create_chat_client

DEFAULT_PROMPT = (
    "You are helping with a Python coding task. Explain the likely cause of a "
    "failing unit test and suggest the smallest safe fix in three concise bullets."
)


@dataclass(frozen=True, slots=True)
class BenchmarkSample:
    """One completed local latency benchmark run."""

    run_number: int
    latency_seconds: float


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Summary of local Ollama latency observations."""

    provider: str
    model: str
    prompt: str
    warmup_runs: int
    samples: tuple[BenchmarkSample, ...]

    @property
    def mean_latency_seconds(self) -> float:
        return statistics.fmean(sample.latency_seconds for sample in self.samples)

    @property
    def median_latency_seconds(self) -> float:
        return statistics.median(sample.latency_seconds for sample in self.samples)

    @property
    def min_latency_seconds(self) -> float:
        return min(sample.latency_seconds for sample in self.samples)

    @property
    def max_latency_seconds(self) -> float:
        return max(sample.latency_seconds for sample in self.samples)

    @property
    def typical_latency_seconds(self) -> float:
        return self.median_latency_seconds


def build_benchmark_request(prompt: str, *, max_output_tokens: int) -> AIRequest:
    """Build the fixed local-only request used for latency benchmarking."""

    return AIRequest(
        messages=(AIMessage(MessageRole.USER, prompt),),
        temperature=0,
        max_output_tokens=max_output_tokens,
        privacy_class=PrivacyClass.LOCAL_ONLY,
        metadata={"benchmark": "local_ollama_latency"},
    )


def run_latency_benchmark(
    client: ChatClient,
    *,
    prompt: str,
    runs: int,
    warmup_runs: int,
    max_output_tokens: int,
) -> BenchmarkResult:
    """Measure latency for repeated local Ollama chat completions."""

    samples: list[BenchmarkSample] = []
    total_runs = warmup_runs + runs
    for index in range(total_runs):
        response = client.complete(
            build_benchmark_request(prompt, max_output_tokens=max_output_tokens)
        )
        if response.latency_ms is None:
            raise RuntimeError("Provider response did not include latency_ms.")
        if index >= warmup_runs:
            samples.append(
                BenchmarkSample(
                    run_number=index - warmup_runs + 1,
                    latency_seconds=response.latency_ms / 1000,
                )
            )

    return BenchmarkResult(
        provider=client.backend.provider,
        model=client.backend.model,
        prompt=prompt,
        warmup_runs=warmup_runs,
        samples=tuple(samples),
    )


def format_catalog_estimate(result: BenchmarkResult) -> str:
    """Return a TOML estimate snippet suitable for manual catalog updates."""

    typical = round(result.typical_latency_seconds, 3)
    source = (
        "local benchmark: "
        f"{len(result.samples)} runs, {result.warmup_runs} warmup, "
        f"median latency for {result.model}"
    )
    return "\n".join(
        (
            "[models.estimate]",
            f"typical_latency_seconds = {typical:g}",
            "input_cost_per_million_tokens = 0",
            "output_cost_per_million_tokens = 0",
            f'source = "{source}"',
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure local Ollama latency for a fixed coding-style prompt."
    )
    parser.add_argument("--model", default="llama3.2", help="Local Ollama model to benchmark.")
    parser.add_argument("--base-url", help="Ollama base URL. Defaults to the adapter default.")
    parser.add_argument("--timeout-seconds", type=float, default=120.0, help="Provider timeout.")
    parser.add_argument("--runs", type=int, default=3, help="Measured runs after warmup.")
    parser.add_argument("--warmup-runs", type=int, default=1, help="Warmup runs to exclude.")
    parser.add_argument("--max-output-tokens", type=int, default=256, help="Response token cap.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt to benchmark.")
    parser.add_argument(
        "--start-ollama",
        action="store_true",
        help="Start `ollama serve` before running the benchmark.",
    )
    parser.add_argument(
        "--ollama-command",
        default="ollama",
        help="Ollama executable used with --start-ollama.",
    )
    parser.add_argument(
        "--ollama-startup-timeout-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait for Ollama to become reachable after starting it.",
    )
    args = parser.parse_args()

    if args.runs <= 0:
        raise SystemExit("--runs must be greater than zero.")
    if args.warmup_runs < 0:
        raise SystemExit("--warmup-runs must be zero or greater.")
    if args.max_output_tokens <= 0:
        raise SystemExit("--max-output-tokens must be greater than zero.")

    if args.start_ollama:
        ensure_ollama_server(
            args.base_url,
            command=args.ollama_command,
            startup_timeout_seconds=args.ollama_startup_timeout_seconds,
        )

    client = create_chat_client(
        BackendConfig(
            provider=ProviderKind.OLLAMA,
            model=args.model,
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
        )
    )
    result = run_latency_benchmark(
        client,
        prompt=args.prompt,
        runs=args.runs,
        warmup_runs=args.warmup_runs,
        max_output_tokens=args.max_output_tokens,
    )
    _print_result(result)


def _print_result(result: BenchmarkResult) -> None:
    print(f"provider: {result.provider}")
    print(f"model: {result.model}")
    print(f"warmup_runs: {result.warmup_runs}")
    print(f"measured_runs: {len(result.samples)}")
    for sample in result.samples:
        print(f"run_{sample.run_number}_seconds: {sample.latency_seconds:.3f}")
    print(f"mean_seconds: {result.mean_latency_seconds:.3f}")
    print(f"median_seconds: {result.median_latency_seconds:.3f}")
    print(f"min_seconds: {result.min_latency_seconds:.3f}")
    print(f"max_seconds: {result.max_latency_seconds:.3f}")
    print()
    print("catalog_estimate_snippet:")
    print(format_catalog_estimate(result))


if __name__ == "__main__":
    main()
