"""Language runtime registry for E2B code execution."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.code.constants import SupportedLanguage

PYTHON_RUNNER_BODY = '''
from solution import solution
import json, io, os, sys, traceback, time

RESULTS_PATH = __RESULTS_PATH__
SCHEMA_VERSION = __SCHEMA_VERSION__

test_cases = json.loads(__TEST_CASES_JSON__)


def _format_output(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, tuple):
        return " ".join(_format_output(part) for part in value)
    return str(value)


def _run_invocation(inv):
    args = inv.get("args", [])
    kwargs = inv.get("kwargs", {})
    result = solution(*args, **kwargs)
    if inv.get("stdout", True):
        captured = io.StringIO()
        if inv.get("unpack") and isinstance(result, tuple):
            print(*result, file=captured)
        else:
            print(result, file=captured)
        return captured.getvalue().strip()
    return _format_output(result)


results = []
for tc in test_cases:
    try:
        start = time.monotonic()
        actual = _run_invocation(tc["invocation"])
        elapsed = (time.monotonic() - start) * 1000
        results.append({
            "test_case_id": tc["id"],
            "passed": actual == tc["expected_output"].strip(),
            "actual_output": actual,
            "expected_output": tc["expected_output"],
            "execution_time_ms": elapsed,
            "error": None
        })
    except Exception:
        results.append({
            "test_case_id": tc["id"],
            "passed": False,
            "actual_output": "",
            "expected_output": tc["expected_output"],
            "execution_time_ms": 0.0,
            "error": traceback.format_exc(limit=3)
        })

os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
with open(RESULTS_PATH, "w", encoding="utf-8") as f:
    json.dump({"schema_version": SCHEMA_VERSION, "results": results}, f)
'''

JAVASCRIPT_RUNNER_BODY = '''
const fs = require("fs");
const path = require("path");
const { solution } = require(__SOLUTION_PATH__);

const RESULTS_PATH = __RESULTS_PATH__;
const SCHEMA_VERSION = __SCHEMA_VERSION__;
const test_cases = JSON.parse(__TEST_CASES_JSON__);

function formatOutput(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (Array.isArray(value)) return value.map((part) => String(part)).join(" ");
  return String(value);
}

function captureStdout(fn) {
  const lines = [];
  const original = console.log;
  console.log = (...parts) => {
    lines.push(parts.map((p) => String(p)).join(" "));
  };
  try {
    fn();
  } finally {
    console.log = original;
  }
  return lines.join("\\n").trim();
}

function runInvocation(inv) {
  const args = inv.args || [];
  const result = solution(...args);
  if (inv.stdout !== false) {
    if (inv.unpack && Array.isArray(result)) {
      return captureStdout(() => console.log(...result));
    }
    return captureStdout(() => console.log(result));
  }
  return formatOutput(result);
}

const results = [];
for (const tc of test_cases) {
  const start = Date.now();
  try {
    const actual = runInvocation(tc.invocation);
    results.push({
      test_case_id: tc.id,
      passed: actual === String(tc.expected_output).trim(),
      actual_output: actual,
      expected_output: tc.expected_output,
      execution_time_ms: Date.now() - start,
      error: null,
    });
  } catch (err) {
    results.push({
      test_case_id: tc.id,
      passed: false,
      actual_output: "",
      expected_output: tc.expected_output,
      execution_time_ms: Date.now() - start,
      error: String(err && err.stack ? err.stack : err),
    });
  }
}

fs.mkdirSync(path.dirname(RESULTS_PATH), { recursive: true });
fs.writeFileSync(
  RESULTS_PATH,
  JSON.stringify({ schema_version: SCHEMA_VERSION, results }),
  "utf8"
);
'''


@dataclass(frozen=True)
class LanguageRuntime:
    language: SupportedLanguage
    monaco_language: str
    solution_path: str
    runner_path: str
    run_command: str
    runner_body_template: str
    solution_module_export_hint: str
    legacy_test_example: str
    e2b_template: str | None = None
    executable: bool = True


_RUNTIMES: dict[SupportedLanguage, LanguageRuntime] = {
    SupportedLanguage.PYTHON: LanguageRuntime(
        language=SupportedLanguage.PYTHON,
        monaco_language="python",
        solution_path="/home/user/solution.py",
        runner_path="/home/user/runner.py",
        run_command="python /home/user/runner.py",
        runner_body_template=PYTHON_RUNNER_BODY,
        solution_module_export_hint="def solution(...):",
        legacy_test_example='print(solution("hello"))',
        e2b_template="code-interpreter-v1",
    ),
    SupportedLanguage.JAVASCRIPT: LanguageRuntime(
        language=SupportedLanguage.JAVASCRIPT,
        monaco_language="javascript",
        solution_path="/home/user/solution.js",
        runner_path="/home/user/runner.js",
        run_command="node /home/user/runner.js",
        runner_body_template=JAVASCRIPT_RUNNER_BODY,
        solution_module_export_hint="function solution(...) { } module.exports = { solution };",
        legacy_test_example='console.log(solution("hello"))',
        e2b_template="code-interpreter-v1",
    ),
    SupportedLanguage.TYPESCRIPT: LanguageRuntime(
        language=SupportedLanguage.TYPESCRIPT,
        monaco_language="typescript",
        solution_path="/home/user/solution.js",
        runner_path="/home/user/runner.js",
        run_command="node /home/user/runner.js",
        runner_body_template=JAVASCRIPT_RUNNER_BODY,
        solution_module_export_hint=(
            "export function solution(...): ReturnType { } // transpile-safe JS subset"
        ),
        legacy_test_example='console.log(solution("hello"))',
        e2b_template="code-interpreter-v1",
    ),
    SupportedLanguage.JAVA: LanguageRuntime(
        language=SupportedLanguage.JAVA,
        monaco_language="java",
        solution_path="/home/user/Solution.java",
        runner_path="/home/user/runner.py",
        run_command="python /home/user/runner.py",
        runner_body_template=PYTHON_RUNNER_BODY,
        solution_module_export_hint="public static ... solution(...)",
        legacy_test_example='print(solution("hello"))',
        executable=False,
    ),
    SupportedLanguage.GO: LanguageRuntime(
        language=SupportedLanguage.GO,
        monaco_language="go",
        solution_path="/home/user/solution.go",
        runner_path="/home/user/runner.py",
        run_command="python /home/user/runner.py",
        runner_body_template=PYTHON_RUNNER_BODY,
        solution_module_export_hint="func solution(...) ...",
        legacy_test_example='print(solution("hello"))',
        executable=False,
    ),
    SupportedLanguage.CSHARP: LanguageRuntime(
        language=SupportedLanguage.CSHARP,
        monaco_language="csharp",
        solution_path="/home/user/Solution.cs",
        runner_path="/home/user/runner.py",
        run_command="python /home/user/runner.py",
        runner_body_template=PYTHON_RUNNER_BODY,
        solution_module_export_hint="public static ... Solution(...)",
        legacy_test_example='print(solution("hello"))',
        executable=False,
    ),
    SupportedLanguage.RUBY: LanguageRuntime(
        language=SupportedLanguage.RUBY,
        monaco_language="ruby",
        solution_path="/home/user/solution.rb",
        runner_path="/home/user/runner.py",
        run_command="python /home/user/runner.py",
        runner_body_template=PYTHON_RUNNER_BODY,
        solution_module_export_hint="def solution(...)",
        legacy_test_example='print(solution("hello"))',
        executable=False,
    ),
    SupportedLanguage.RUST: LanguageRuntime(
        language=SupportedLanguage.RUST,
        monaco_language="rust",
        solution_path="/home/user/solution.rs",
        runner_path="/home/user/runner.py",
        run_command="python /home/user/runner.py",
        runner_body_template=PYTHON_RUNNER_BODY,
        solution_module_export_hint="fn solution(...) -> ...",
        legacy_test_example='print(solution("hello"))',
        executable=False,
    ),
    SupportedLanguage.CPP: LanguageRuntime(
        language=SupportedLanguage.CPP,
        monaco_language="cpp",
        solution_path="/home/user/solution.cpp",
        runner_path="/home/user/runner.py",
        run_command="python /home/user/runner.py",
        runner_body_template=PYTHON_RUNNER_BODY,
        solution_module_export_hint="auto solution(...)",
        legacy_test_example='print(solution("hello"))',
        executable=False,
    ),
}


def get_language_runtime(language: str | SupportedLanguage) -> LanguageRuntime:
    lang = language if isinstance(language, SupportedLanguage) else SupportedLanguage(language)
    runtime = _RUNTIMES.get(lang)
    if runtime is None:
        raise ValueError(f"No runtime registered for language: {language}")
    return runtime


def list_executable_languages() -> list[SupportedLanguage]:
    return [lang for lang, runtime in _RUNTIMES.items() if runtime.executable]


def build_runner_script(runtime: LanguageRuntime, *, test_cases_json: str) -> str:
    body = runtime.runner_body_template
    body = body.replace("__TEST_CASES_JSON__", repr(test_cases_json))
    body = body.replace("__RESULTS_PATH__", repr("/home/user/.masaar/results.json"))
    body = body.replace("__SCHEMA_VERSION__", "1")
    if runtime.language in (
        SupportedLanguage.JAVASCRIPT,
        SupportedLanguage.TYPESCRIPT,
    ):
        body = body.replace("__SOLUTION_PATH__", repr(runtime.solution_path))
    return body
