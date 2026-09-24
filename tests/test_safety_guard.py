from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


HOOK = Path(__file__).resolve().parents[1] / ".cursor" / "hooks" / "safety_guard.py"


class SafetyGuardTest(unittest.TestCase):
    def _run(
        self,
        payload: dict[str, object],
        *,
        encoding: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if encoding is not None:
            env["PYTHONIOENCODING"] = encoding
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def _verdict(self, payload: dict[str, object]) -> dict[str, object]:
        result = self._run(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _shell(self, command: str) -> dict[str, object]:
        return self._verdict(
            {"tool_name": "Shell", "tool_input": {"command": command}}
        )

    def assertShell(self, expected: str, command: str) -> None:
        verdict = self._shell(command)
        self.assertEqual(verdict["permission"], expected, f"{command}: {verdict}")

    def assertEdit(
        self,
        expected: str,
        tool_name: str,
        path: str,
        *,
        patch: str | None = None,
    ) -> None:
        if tool_name == "ApplyPatch":
            tool_input: dict[str, object] = {"patch": patch or ""}
        else:
            tool_input = {"path": path}
        verdict = self._verdict({"tool_name": tool_name, "tool_input": tool_input})
        self.assertEqual(
            verdict["permission"], expected, f"{tool_name} {path}: {verdict}"
        )

    def test_git_config_read_allowed(self) -> None:
        for command in (
            "git config user.name",
            "git config --get user.email",
            "git config --get-regexp ^remote",
            "git config -l",
            "git config --global --get core.editor",
            "git config --file .git/config --get core.bare",
        ):
            self.assertShell("allow", command)

    def test_git_config_write_denied(self) -> None:
        for command in (
            "git config user.email me@example.com",
            "git config --global user.name Example",
            "git config core.hooksPath /dev/null",
            "git config --unset user.email",
            "git config --remove-section remote.origin",
            "git config --add safe.directory /tmp",
            "git config --file .git/config core.bare true",
            "git config user.name X",
        ):
            self.assertShell("deny", command)

    def test_other_destructive_git_still_denied(self) -> None:
        for command in (
            "git reset --hard",
            "git reset --hard HEAD~1",
            "git push --force",
            "git push --force origin master",
            "git push origin --delete br",
            "git clean -fd",
            "git stash drop",
        ):
            self.assertShell("deny", command)

    def test_ordinary_git_allowed(self) -> None:
        for command in (
            "git status",
            "git status -sb",
            "git add -A",
            "git commit -m x",
            "git commit -m wip",
            "git push",
            "git push origin feature/dwh-bb8",
        ):
            self.assertShell("allow", command)

    def test_positive_shell_controls(self) -> None:
        for command in (
            "venv/bin/python -m pytest tests -q",
            "python3 .cursor/state/kg.py add --type run --summary x",
            "rm file.txt",
            "mv a b",
        ):
            self.assertShell("allow", command)

    def test_recursive_remove_denied(self) -> None:
        for command in (
            "rm -rf dir",
            "/bin/rm -rf dir",
            "sudo -n rm -rf dir",
        ):
            self.assertShell("deny", command)

    def test_positive_edits_allowed(self) -> None:
        self.assertEdit("allow", "Write", "scripts/x.py")
        self.assertEdit("allow", "Write", ".env.example")

    def test_secret_edits_denied(self) -> None:
        for tool_name in ("Write", "StrReplace", "Delete"):
            self.assertEdit("deny", tool_name, ".env")
            self.assertEdit("deny", tool_name, "data/.env.local")
        self.assertEdit(
            "deny",
            "ApplyPatch",
            ".env",
            patch="*** Update File: .env\n",
        )

    def test_ascii_stdout_deny_is_readable(self) -> None:
        result = self._run(
            {
                "tool_name": "Shell",
                "tool_input": {"command": "rm -rf dir"},
            },
            encoding="ascii",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout, "stdout пуст при PYTHONIOENCODING=ascii")
        verdict = json.loads(result.stdout)
        self.assertEqual(verdict["permission"], "deny")

    def test_unrecognized_payload_allowed(self) -> None:
        """Как в cube: не dict, битый JSON, пустой ввод и неизвестный tool → allow."""
        for raw in ("", "null", "[]", "not-json", "{}"):
            result = subprocess.run(
                [sys.executable, str(HOOK)],
                input=raw,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            verdict = json.loads(result.stdout)
            self.assertEqual(verdict["permission"], "allow", raw)
        verdict = self._verdict(
            {"tool_name": "UnknownTool", "tool_input": {"command": "rm -rf dir"}}
        )
        self.assertEqual(verdict["permission"], "allow")

    def test_worktree_discard_denied(self) -> None:
        for command in (
            "git checkout -- .",
            "git checkout -- file.txt",
            "git checkout .",
            "git checkout -f",
            "git checkout -f main",
            "git checkout --force main",
            "git checkout HEAD -- file.txt",
            "git restore .",
            "git restore file.txt",
            "git restore --worktree file.txt",
            "git restore --source HEAD file.txt",
            "git restore --staged --worktree file.txt",
        ):
            self.assertShell("deny", command)

    def test_worktree_switch_and_index_restore_allowed(self) -> None:
        for command in (
            "git checkout main",
            "git checkout -b feature",
            "git switch main",
            "git restore --staged file",
            "git restore --staged f",
        ):
            self.assertShell("allow", command)

    def test_quoted_and_heredoc_data_allowed(self) -> None:
        for command in (
            'rg -n "x; rm -rf y" .',
            "echo 'rm -rf x'",
            "python3 - <<'EOF'\nprint(\"rm -rf x\")\nEOF",
            "python3 - <<'EOF'\nrm -rf x\nEOF",
            "python3 - <<\"WORD\"\nrm -rf x\nWORD",
            "python3 - <<-WORD\n\trm -rf x\nWORD",
        ):
            self.assertShell("allow", command)

    def test_real_command_still_denied_around_quotes_and_heredoc(self) -> None:
        for command in (
            'rm -rf "my dir"',
            'git reset --hard "HEAD~1"',
            "python3 - <<'EOF'\nprint(1)\nEOF\nrm -rf x",
        ):
            self.assertShell("deny", command)

    def test_env_and_assignment_wrappers_denied(self) -> None:
        for command in (
            "env -u FOO rm -rf x",
            "env -i rm -rf x",
            "env A=1 rm -rf x",
            "FOO=1 rm -rf x",
        ):
            self.assertShell("deny", command)

    def test_git_global_options_do_not_hide_subcommand(self) -> None:
        for command in (
            "git -C /tmp reset --hard",
            "git -c core.x=y push --force",
            "git --git-dir=.git --work-tree=. clean -fd",
            "git --git-dir .git --work-tree . reset --hard",
            "git --no-pager -P reset --hard",
        ):
            self.assertShell("deny", command)
        for command in (
            "git -C /home/budnik_an/todo status",
            "git -C x log",
        ):
            self.assertShell("allow", command)

    def test_shell_secret_write_denied(self) -> None:
        for command in (
            "echo X >> .env",
            "echo X > data/.env.local",
            "cat a | tee .env",
            "tee -a .env",
            "echo X>.env",
            "echo X>>.env",
            "echo X 1> .env",
            "echo X 1>> .env",
            "cmd &> .env",
            "cmd >| .env",
            'echo X > ".env"',
            "echo X>>data/.env.local",
        ):
            self.assertShell("deny", command)

    def test_redirect_not_a_secret_write_allowed(self) -> None:
        for command in (
            "python3 x.py > output/log.txt 2>&1",
            "cmd 2>/dev/null",
            "cmd 2>&1 | cat",
            'echo "a>.env"',
            "echo X >> .env.example",
            "echo X>out.txt",
            "cat < .env",
            "python3 - <<'EOF'\nopen('.env','w')\nEOF",
            'rg -o "^A=" .env',
        ):
            self.assertShell("allow", command)

    def test_shell_secret_read_and_example_allowed(self) -> None:
        for command in (
            "cat .env | head",
            'rg -o "^X=" .env',
            "grep -c A .env",
            ". ./.env",
            "set -a; . ./.env; set +a",
            "echo X >> .env.example",
        ):
            self.assertShell("allow", command)

    def test_known_bypass_limitation_allowed(self) -> None:
        """Намеренный обход через вложенный shell сторож не разбирает."""
        for command in (
            "bash -c 'rm -rf x'",
            "echo $(rm -rf x)",
        ):
            self.assertShell("allow", command)

    def test_validator_allow_regression(self) -> None:
        for command in (
            "git status",
            "git log | cat",
            'git add -A && git commit -m "x" && git push',
            "git add -f",
            "git mv",
            "git fetch -q && git status -sb",
            'rg -n "rm -rf" .',
            'echo "git reset --hard"',
            "python3 - <<'EOF'\nprint(1)\nEOF",
            "find . -name '*.pyc' | head",
            "rm -f /tmp/x.txt",
            "mkdir -p data/x && mv data/a data/b",
            "env -u BND_WEBBI_DIR /usr/bin/python3 scripts/ingestion/bnd_sync/run_nightly.py --no-notify",
            "crontab -l",
        ):
            self.assertShell("allow", command)


if __name__ == "__main__":
    unittest.main()
