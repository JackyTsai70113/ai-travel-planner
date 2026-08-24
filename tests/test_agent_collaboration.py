from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.agent import collaboration
from scripts.agent.policy import (
    find_ownership_conflicts,
    load_policy,
    route_paths,
)
from scripts.agent.workspace import (
    WorkspaceError,
    assert_workspace,
    check_ownership,
    handoff,
    prepare_workspace,
)
from scripts.validate_agent_collaboration import ROOT, validate


def _git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True
    )


class CollaborationPolicyTests(unittest.TestCase):
    def test_travel_paths_route_to_high_risk_domain_reviewers(self) -> None:
        policy = load_policy(ROOT)

        result = route_paths(
            ["src/application/production.py", "src/sources/providers.py"], policy
        )

        self.assertEqual("high", result["risk"])
        self.assertIn("core.verifier", result["review_roles"])
        self.assertIn("domain.itinerary-invariant-reviewer", result["review_roles"])
        self.assertIn("domain.source-provenance-auditor", result["review_roles"])

    def test_write_ownership_overlap_fails_closed(self) -> None:
        conflicts = find_ownership_conflicts(
            ["src/planner/repair.py"],
            [(28, ["src/planner/**"]), (29, ["tests/test_sources.py"])],
        )

        self.assertEqual(1, len(conflicts))
        self.assertEqual(28, conflicts[0]["issue_number"])

    def test_repository_collaboration_contract_is_valid(self) -> None:
        result = validate()

        self.assertEqual("PASS", result["status"])
        self.assertEqual(92, result["snapshot_files"])
        self.assertEqual(3, result["domain_reviewers"])


class IssueWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "repo"
        _git(self.root, "init", "--bare", str(self.remote))
        _git(self.root, "clone", str(self.remote), str(self.repo))
        _git(self.repo, "config", "user.name", "Agent Test")
        _git(self.repo, "config", "user.email", "agent@example.test")
        (self.repo / "README.md").write_text("fixture\n", encoding="utf-8")
        (self.repo / "agent-collaboration").mkdir()
        source_policy = ROOT / "agent-collaboration" / "project-policy.json"
        (self.repo / "agent-collaboration" / "project-policy.json").write_bytes(
            source_policy.read_bytes()
        )
        _git(self.repo, "add", "README.md", "agent-collaboration/project-policy.json")
        _git(self.repo, "commit", "-m", "initial")
        _git(self.repo, "branch", "-M", "main")
        _git(self.repo, "push", "--set-upstream", "origin", "main")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _prepare(self):
        return prepare_workspace(
            repo_root=self.repo,
            issue_number=101,
            slug="intent-parser",
            write_paths=["src/intent/**", "tests/test_travel_intent.py"],
            base_ref="main",
            fetch=False,
            verify_issue=False,
        )

    def test_prepare_check_handoff_and_conflict_guard(self) -> None:
        workspace = self._prepare()

        verified = assert_workspace(self.repo, 101, workspace.worktree)
        self.assertEqual("agent/issue-101-intent-parser", verified.branch)
        self.assertEqual([], check_ownership(verified)["changed_files"])

        target = workspace.worktree / "src" / "intent" / "new_parser.py"
        target.parent.mkdir(parents=True)
        target.write_text("VALUE = 1\n", encoding="utf-8")
        self.assertEqual(
            ["src/intent/new_parser.py"], check_ownership(verified)["changed_files"]
        )

        outside = workspace.worktree / "README.md"
        outside.write_text("outside ownership\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "outside declared ownership"):
            check_ownership(verified)
        _git(workspace.worktree, "restore", "README.md")

        with self.assertRaisesRegex(WorkspaceError, "overlaps Issue #101"):
            prepare_workspace(
                repo_root=self.repo,
                issue_number=102,
                slug="parser-overlap",
                write_paths=["src/intent/parser.py"],
                base_ref="main",
                fetch=False,
                verify_issue=False,
            )

        _git(workspace.worktree, "add", "src/intent/new_parser.py")
        _git(workspace.worktree, "commit", "-m", "add parser")
        result = handoff(
            verified, ["python3 -m unittest tests.test_travel_intent=PASS"]
        )
        self.assertTrue(result["ready_for_push"])
        self.assertEqual(40, len(result["head_sha"]))
        self.assertEqual("medium", result["routing"]["risk"])

    def test_prepare_verifies_open_github_issue_and_derives_slug(self) -> None:
        binary_directory = self.root / "bin"
        binary_directory.mkdir()
        fake_gh = binary_directory / "gh"
        fake_gh.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' "
            '\'{"number":103,"state":"OPEN","title":"Add reservation evidence"}\'\n',
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)

        with mock.patch.dict(
            os.environ,
            {"PATH": str(binary_directory) + os.pathsep + os.environ["PATH"]},
        ):
            workspace = prepare_workspace(
                repo_root=self.repo,
                issue_number=103,
                slug=None,
                write_paths=["src/reservations/**"],
                base_ref="main",
                fetch=False,
            )

        self.assertEqual("agent/issue-103-add-reservation-evidence", workspace.branch)
        self.assertTrue(workspace.worktree.is_dir())

    def test_prepare_supports_mr_first_without_github_issue(self) -> None:
        workspace = prepare_workspace(
            repo_root=self.repo,
            issue_number=None,
            mr_slug="request-constraints",
            write_paths=["src/intent/**"],
            base_ref="main",
            fetch=False,
            verify_issue=False,
        )

        self.assertEqual("mr:request-constraints", workspace.work_item)
        self.assertEqual("agent/mr-request-constraints", workspace.branch)
        verified = assert_workspace(self.repo, None, workspace.worktree, mr_slug="request-constraints")
        self.assertEqual("mr:request-constraints", check_ownership(verified)["work_item"])

    def test_mr_first_ownership_conflict_is_rejected(self) -> None:
        self._prepare()
        with self.assertRaisesRegex(WorkspaceError, "overlaps Issue #101"):
            prepare_workspace(
                repo_root=self.repo,
                issue_number=None,
                mr_slug="parser-overlap",
                write_paths=["src/intent/parser.py"],
                base_ref="main",
                fetch=False,
                verify_issue=False,
            )

    def test_publish_opens_regular_pr_without_draft_flag(self) -> None:
        workspace = self._prepare()
        target = workspace.worktree / "src" / "intent" / "new_parser.py"
        target.parent.mkdir(parents=True)
        target.write_text("VALUE = 1\n", encoding="utf-8")
        _git(workspace.worktree, "add", "src/intent/new_parser.py")
        _git(workspace.worktree, "commit", "-m", "add parser")

        binary_directory = self.root / "bin"
        binary_directory.mkdir()
        command_log = self.root / "gh-commands.log"
        fake_gh = binary_directory / "gh"
        fake_gh.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$AGENT_GH_LOG"\n'
            'if [ "$1 $2" = "pr view" ]; then exit 1; fi\n'
            "printf '%s\\n' 'https://github.example/pull/101'\n",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)
        environment = {
            "PATH": str(binary_directory) + os.pathsep + os.environ["PATH"],
            "AGENT_GH_LOG": str(command_log),
        }
        output = io.StringIO()
        previous = Path.cwd()
        try:
            os.chdir(workspace.worktree)
            with (
                mock.patch.dict(os.environ, environment),
                contextlib.redirect_stdout(output),
            ):
                result = collaboration.main(
                    [
                        "publish",
                        "101",
                        "--title",
                        "feat: parser",
                        "--test-evidence",
                        "python3 -m unittest=PASS",
                    ]
                )
        finally:
            os.chdir(previous)

        self.assertEqual(0, result)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["pull_request"]["isDraft"])
        commands = command_log.read_text(encoding="utf-8")
        self.assertIn("pr create", commands)
        self.assertNotIn("--draft", commands)


if __name__ == "__main__":
    unittest.main()
