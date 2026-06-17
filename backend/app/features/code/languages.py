"""Sandbox language configuration for code challenges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SupportedLanguage = Literal["python", "javascript"]

SUPPORTED_LANGUAGES: tuple[SupportedLanguage, ...] = ("python", "javascript")

_DEFAULT_LANGUAGE: SupportedLanguage = "python"


@dataclass(frozen=True)
class LanguageConfig:
    """Execution and authoring rules for one sandbox language."""

    id: SupportedLanguage
    label: str
    solution_filename: str
    runner_filename: str
    run_command: str
    monaco_language: str


def normalize_language(language: str | None) -> SupportedLanguage:
    """Return a supported language id or raise ``ValueError``."""
    if language is None:
        return _DEFAULT_LANGUAGE
    normalized = language.strip().lower()
    aliases = {
        "python": "python",
        "py": "python",
        "javascript": "javascript",
        "js": "javascript",
        "node": "javascript",
    }
    mapped = aliases.get(normalized)
    if mapped is None or mapped not in SUPPORTED_LANGUAGES:
        supported = ", ".join(SUPPORTED_LANGUAGES)
        raise ValueError(f"Unsupported language '{language}'. Supported: {supported}")
    return mapped  # type: ignore[return-value]


def get_language_config(language: str | None) -> LanguageConfig:
    """Resolve sandbox settings for ``language``."""
    lang = normalize_language(language)
    if lang == "python":
        return LanguageConfig(
            id="python",
            label="Python",
            solution_filename="solution.py",
            runner_filename="runner.py",
            run_command="python /home/user/runner.py",
            monaco_language="python",
        )
    return LanguageConfig(
        id="javascript",
        label="JavaScript",
        solution_filename="solution.js",
        runner_filename="runner.js",
        run_command="node /home/user/runner.js",
        monaco_language="javascript",
    )


def solution_path(config: LanguageConfig) -> str:
    return f"/home/user/{config.solution_filename}"


def runner_path(config: LanguageConfig) -> str:
    return f"/home/user/{config.runner_filename}"


_PYTHON_RUNNER = '''
from solution import solution
import json, io, sys, traceback, time

test_cases = json.loads(__TEST_CASES_JSON__)

results = []
for tc in test_cases:
    try:
        captured = io.StringIO()
        sys.stdout = captured
        start = time.monotonic()
        exec(tc["input"], {"solution": solution})
        elapsed = (time.monotonic() - start) * 1000
        sys.stdout = sys.__stdout__
        actual = captured.getvalue().strip()
        results.append({
            "test_case_id": tc["id"],
            "passed": actual == tc["expected_output"].strip(),
            "actual_output": actual,
            "expected_output": tc["expected_output"],
            "execution_time_ms": elapsed,
            "error": None
        })
    except Exception:
        sys.stdout = sys.__stdout__
        results.append({
            "test_case_id": tc["id"],
            "passed": False,
            "actual_output": "",
            "expected_output": tc["expected_output"],
            "execution_time_ms": 0.0,
            "error": traceback.format_exc(limit=3)
        })

print(json.dumps(results))
'''

_JAVASCRIPT_RUNNER = '''
const solutionModule = require("/home/user/solution.js");
const solution = typeof solutionModule === "function" ? solutionModule : solutionModule.solution;

if (typeof solution !== "function") {
  console.error("solution.js must export a function via module.exports");
  process.exit(1);
}

const testCases = JSON.parse(__TEST_CASES_JSON__);
const results = [];

for (const tc of testCases) {
  try {
    let output = "";
    const console = {
      log: (...args) => {
        output = args.map(String).join(" ");
      },
    };
    const start = performance.now();
    const runner = new Function("solution", "console", tc.input);
    runner(solution, console);
    const elapsed = performance.now() - start;
    const actual = output.trim();
    results.push({
      test_case_id: tc.id,
      passed: actual === String(tc.expected_output).trim(),
      actual_output: actual,
      expected_output: tc.expected_output,
      execution_time_ms: elapsed,
      error: null,
    });
  } catch (err) {
    results.push({
      test_case_id: tc.id,
      passed: false,
      actual_output: "",
      expected_output: tc.expected_output,
      execution_time_ms: 0.0,
      error: err && err.stack ? err.stack.split("\\n").slice(0, 3).join("\\n") : String(err),
    });
  }
}

console.log(JSON.stringify(results));
'''


def build_runner_script(language: str | None) -> tuple[LanguageConfig, str]:
    """Return language config and the runner source for the sandbox."""
    config = get_language_config(language)
    template = _PYTHON_RUNNER if config.id == "python" else _JAVASCRIPT_RUNNER
    return config, template


def generator_system_prompt(language: str | None) -> str:
    """LLM system prompt for challenge generation in ``language``."""
    config = get_language_config(language)
    if config.id == "python":
        return (
            "You are an expert coding-assessment author. Produce ONE original Python "
            "challenge for a learner.\n\n"
            "Rules:\n"
            "- Define exactly one entry point: def solution(...)\n"
            "- starter_code must include that function with a TODO/pass body\n"
            "- Every test case input MUST be valid Python that calls solution, "
            "typically print(solution(...))\n"
            "- expected_output is the stdout the sandbox expects (no trailing newline)\n"
            "- Include at least 2 visible tests (is_hidden=false) and at least 1 hidden test\n"
            "- Do not reuse titles from the avoid list\n"
            "- Keep problems fair and self-contained — no imports beyond the standard library\n"
            "- Return JSON matching the schema exactly"
        )
    return (
        "You are an expert coding-assessment author. Produce ONE original JavaScript "
        "(Node.js) challenge for a learner.\n\n"
        "Rules:\n"
        "- Export exactly one entry point: module.exports = function solution(...) { ... }\n"
        "- starter_code must use CommonJS module.exports with a TODO body\n"
        "- Every test case input MUST be valid JavaScript that calls solution, "
        "typically console.log(solution(...))\n"
        "- expected_output is the stdout the sandbox expects (no trailing newline)\n"
        "- Include at least 2 visible tests (is_hidden=false) and at least 1 hidden test\n"
        "- Do not reuse titles from the avoid list\n"
        "- Use only Node.js built-ins — no npm packages\n"
        "- Return JSON matching the schema exactly"
    )


def generator_retry_prompt(language: str | None) -> str:
    config = get_language_config(language)
    if config.id == "python":
        return (
            "Invalid challenge spec. Ensure test inputs are executable Python like "
            "print(solution('abc')), include hidden and visible tests, and use def solution(...)."
        )
    return (
        "Invalid challenge spec. Ensure test inputs are executable JavaScript like "
        "console.log(solution('abc')), export module.exports = function solution(...), "
        "and include hidden and visible tests."
    )


def generator_test_case_description(language: str | None) -> str:
    config = get_language_config(language)
    if config.id == "python":
        return "Executable Python that calls solution(...), e.g. print(solution('hi'))"
    return "Executable JavaScript that calls solution(...), e.g. console.log(solution('hi'))"


def generator_starter_description(language: str | None) -> str:
    config = get_language_config(language)
    if config.id == "python":
        return "Python starter with def solution(...) and a TODO body"
    return "JavaScript starter with module.exports = function solution(...) { ... }"


__all__ = [
    "LanguageConfig",
    "SUPPORTED_LANGUAGES",
    "SupportedLanguage",
    "build_runner_script",
    "generator_retry_prompt",
    "generator_starter_description",
    "generator_system_prompt",
    "generator_test_case_description",
    "get_language_config",
    "normalize_language",
    "runner_path",
    "solution_path",
]
