"""Git repository utilities for analyzing commit history."""

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dateutil import parser as date_parser
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError


class GitRepository:
    """Wrapper for git repository operations."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize git repository wrapper.

        Args:
            repo_path: Path to git repository root

        Raises:
            ValueError: If repo_path is not a valid git repository
        """
        try:
            self.repo = Repo(str(repo_path))
        except InvalidGitRepositoryError as e:
            raise ValueError(f"Not a valid git repository: {repo_path}") from e
        self.repo_path = Path(self.repo.working_dir) if self.repo.working_dir else repo_path

    def get_tracked_files(self) -> list[Path]:
        """Get all tracked files in the repository.

        Returns:
            List of file paths relative to repository root
        """
        files = []
        for item in self.repo.tree().traverse():
            if item.type == "blob":
                files.append(Path(item.path))
        return files

    def get_file_contributors(
        self,
        file_path: Path,
        since: datetime | None = None,
        branch: str = "HEAD",
    ) -> dict[str, dict[str, int]]:
        """Get contributor statistics for a specific file.

        Args:
            file_path: Path to file relative to repo root
            since: Only consider commits since this date
            branch: Branch to analyze (default: HEAD)

        Returns:
            Dictionary mapping author email to stats:
            {
                "author@example.com": {
                    "commits": 5,
                    "lines_added": 100,
                    "lines_removed": 50,
                    "name": "Author Name"
                }
            }
        """
        stats: dict[str, dict[str, int | str]] = defaultdict(
            lambda: {"commits": 0, "lines_added": 0, "lines_removed": 0, "name": ""}
        )

        try:
            commits = self.repo.iter_commits(
                branch, paths=str(file_path), since=since, reverse=False
            )

            for commit in commits:
                if since and commit.committed_datetime < since:
                    continue

                author_email = commit.author.email
                author_name = commit.author.name

                stats[author_email]["commits"] += 1
                stats[author_email]["name"] = author_name

                try:
                    parent = commit.parents[0] if commit.parents else None
                    if parent:
                        diff = parent.diff(commit, paths=[str(file_path)])
                        for item in diff:
                            if item.diff:
                                lines_added = item.diff.count(b"\n+") - item.diff.count(b"\n+++")
                                lines_removed = item.diff.count(b"\n-") - item.diff.count(b"\n---")
                                stats[author_email]["lines_added"] += max(0, lines_added)
                                stats[author_email]["lines_removed"] += max(0, lines_removed)
                except (IndexError, GitCommandError):
                    pass

        except GitCommandError:
            pass

        return {k: dict(v) for k, v in stats.items()}

    def get_all_file_stats(
        self,
        since: datetime | None = None,
        branch: str = "HEAD",
    ) -> dict[Path, dict[str, dict[str, int | str]]]:
        """Get contributor statistics for all files.

        Args:
            since: Only consider commits since this date
            branch: Branch to analyze (default: HEAD)

        Returns:
            Dictionary mapping file paths to contributor stats
        """
        files = self.get_tracked_files()
        all_stats: dict[Path, dict[str, dict[str, int | str]]] = {}

        for file_path in files:
            stats = self.get_file_contributors(file_path, since=since, branch=branch)
            if stats:
                all_stats[file_path] = stats

        return all_stats

    def parse_since_date(self, since_str: str) -> datetime:
        """Parse a date string into datetime object.

        Supports formats like:
        - "6 months ago"
        - "2024-01-01"
        - "2024-01-01T10:00:00"

        Args:
            since_str: Date string to parse

        Returns:
            Parsed datetime object
        """
        try:
            return date_parser.parse(since_str, fuzzy=True)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid date format: {since_str}") from e

    def get_default_branch(self) -> str:
        """Get the default branch name (main or master).

        Returns:
            Default branch name
        """
        for branch_name in ["main", "master"]:
            try:
                self.repo.heads[branch_name]
                return branch_name
            except (IndexError, AttributeError):
                continue

        return "HEAD"
