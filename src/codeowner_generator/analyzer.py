"""Analyze git repository to determine code ownership."""

from collections import defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from .git_utils import GitRepository


class OwnershipStrategy(str, Enum):
    """Ownership calculation strategies."""

    COMMITS = "commits"
    LINES = "lines"
    RECENT = "recent"
    WEIGHTED = "weighted"


class FileOwnership:
    """Represents ownership information for a file."""

    def __init__(self, file_path: Path) -> None:
        """Initialize file ownership.

        Args:
            file_path: Path to the file
        """
        self.file_path = file_path
        self.contributors: dict[str, dict[str, int | str]] = {}
        self.ownership_scores: dict[str, float] = {}

    def add_contributor(self, email: str, stats: dict[str, int | str]) -> None:
        """Add contributor statistics.

        Args:
            email: Contributor email
            stats: Contributor statistics
        """
        self.contributors[email] = stats

    def calculate_ownership(
        self,
        strategy: OwnershipStrategy,
        since: datetime | None = None,
        commits_weight: float = 0.4,
        lines_weight: float = 0.6,
        time_decay: bool = True,
    ) -> dict[str, float]:
        """Calculate ownership scores based on strategy.

        Args:
            strategy: Ownership calculation strategy
            since: Reference date for recent/weighted strategies
            commits_weight: Weight for commits in weighted strategy
            lines_weight: Weight for lines in weighted strategy
            time_decay: Whether to apply time decay in weighted strategy

        Returns:
            Dictionary mapping contributor email to ownership score (0-1)
        """
        if not self.contributors:
            return {}

        if strategy == OwnershipStrategy.COMMITS:
            return self._calculate_by_commits()
        elif strategy == OwnershipStrategy.LINES:
            return self._calculate_by_lines()
        elif strategy == OwnershipStrategy.RECENT:
            return self._calculate_by_recent(since)
        elif strategy == OwnershipStrategy.WEIGHTED:
            return self._calculate_weighted(since, commits_weight, lines_weight, time_decay)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _calculate_by_commits(self) -> dict[str, float]:
        """Calculate ownership based on number of commits."""
        total_commits = sum(
            int(stats.get("commits", 0)) for stats in self.contributors.values()
        )
        if total_commits == 0:
            return {}

        scores = {}
        for email, stats in self.contributors.items():
            commits = int(stats.get("commits", 0))
            scores[email] = commits / total_commits if total_commits > 0 else 0.0

        return scores

    def _calculate_by_lines(self) -> dict[str, float]:
        """Calculate ownership based on lines added."""
        total_lines = sum(
            int(stats.get("lines_added", 0)) for stats in self.contributors.values()
        )
        if total_lines == 0:
            return self._calculate_by_commits()

        scores = {}
        for email, stats in self.contributors.items():
            lines = int(stats.get("lines_added", 0))
            scores[email] = lines / total_lines if total_lines > 0 else 0.0

        return scores

    def _calculate_by_recent(self, since: datetime | None) -> dict[str, float]:
        """Calculate ownership based on recent commits (last 6 months if since not specified)."""
        if since is None:
            from datetime import timedelta

            since = datetime.now() - timedelta(days=180)

        recent_commits = defaultdict(int)
        for email, stats in self.contributors.items():
            recent_commits[email] = int(stats.get("commits", 0))

        total_recent = sum(recent_commits.values())
        if total_recent == 0:
            return self._calculate_by_commits()

        scores = {}
        for email, count in recent_commits.items():
            scores[email] = count / total_recent if total_recent > 0 else 0.0

        return scores

    def _calculate_weighted(
        self,
        since: datetime | None,
        commits_weight: float = 0.4,
        lines_weight: float = 0.6,
        time_decay: bool = True,
    ) -> dict[str, float]:
        """Calculate ownership using weighted combination of commits and lines.

        Args:
            since: Reference date for time decay
            commits_weight: Weight for commits (default: 0.4)
            lines_weight: Weight for lines (default: 0.6)
            time_decay: Whether to apply time decay to older commits
        """
        commits_scores = self._calculate_by_commits()
        lines_scores = self._calculate_by_lines()

        if not commits_scores:
            return {}

        if time_decay and since:
            commits_scores = self._apply_time_decay(commits_scores, since)

        scores = {}
        all_emails = set(commits_scores.keys()) | set(lines_scores.keys())
        for email in all_emails:
            commits_score = commits_scores.get(email, 0.0)
            lines_score = lines_scores.get(email, 0.0)
            total_weight = commits_weight + lines_weight
            scores[email] = (
                (commits_score * commits_weight) + (lines_score * lines_weight)
            ) / total_weight

        return scores

    def _apply_time_decay(
        self, scores: dict[str, float], since: datetime
    ) -> dict[str, float]:
        """Apply time decay to scores, giving more weight to recent commits."""
        return scores


class RepositoryAnalyzer:
    """Analyzes git repository to determine code ownership."""

    def __init__(self, repo: GitRepository) -> None:
        """Initialize repository analyzer.

        Args:
            repo: GitRepository instance
        """
        self.repo = repo

    def analyze(
        self,
        strategy: OwnershipStrategy = OwnershipStrategy.COMMITS,
        since: datetime | None = None,
        branch: str = "HEAD",
        threshold: float = 0.1,
        min_owners: int = 1,
        max_owners: int = 2,
        min_commits: int = 0,
        min_lines: int = 0,
        commits_weight: float = 0.4,
        lines_weight: float = 0.6,
        time_decay: bool = True,
        exclude_paths: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> dict[Path, list[tuple[str, str, float]]]:
        """Analyze repository and determine ownership.

        Args:
            strategy: Ownership calculation strategy
            since: Only consider commits since this date
            branch: Branch to analyze
            threshold: Minimum ownership percentage (0-1)
            min_owners: Minimum number of owners per file
            max_owners: Maximum number of owners per file
            min_commits: Minimum number of commits required for an owner
            min_lines: Minimum number of lines required for an owner
            commits_weight: Weight for commits in weighted strategy
            lines_weight: Weight for lines in weighted strategy
            time_decay: Whether to apply time decay in weighted strategy
            exclude_paths: List of paths to exclude from analysis
            exclude_patterns: List of glob patterns to exclude

        Returns:
            Dictionary mapping file paths to list of (email, name, score) tuples
            sorted by score descending
        """
        import fnmatch

        all_stats = self.repo.get_all_file_stats(since=since, branch=branch)
        ownership_results: dict[Path, list[tuple[str, str, float]]] = {}

        exclude_paths = exclude_paths or []
        exclude_patterns = exclude_patterns or []

        for file_path, contributors in all_stats.items():
            file_str = str(file_path)

            if any(file_str.startswith(exclude) for exclude in exclude_paths):
                continue

            if any(fnmatch.fnmatch(file_str, pattern) for pattern in exclude_patterns):
                continue

            file_ownership = FileOwnership(file_path)
            for email, stats in contributors.items():
                commits = int(stats.get("commits", 0))
                lines = int(stats.get("lines_added", 0))

                if commits < min_commits or lines < min_lines:
                    continue

                file_ownership.add_contributor(email, stats)

            if not file_ownership.contributors:
                continue

            scores = file_ownership.calculate_ownership(
                strategy, since, commits_weight, lines_weight, time_decay
            )
            owners = self._get_top_owners(
                file_ownership.contributors,
                scores,
                threshold,
                min_owners,
                max_owners,
            )
            if owners:
                ownership_results[file_path] = owners

        return ownership_results

    def _get_top_owners(
        self,
        contributors: dict[str, dict[str, int | str]],
        scores: dict[str, float],
        threshold: float,
        min_owners: int,
        max_owners: int,
    ) -> list[tuple[str, str, float]]:
        """Get top owners based on scores and thresholds.

        Args:
            contributors: Contributor statistics
            scores: Ownership scores
            threshold: Minimum score threshold
            min_owners: Minimum number of owners
            max_owners: Maximum number of owners

        Returns:
            List of (email, name, score) tuples sorted by score descending
        """
        owners = []
        for email, score in scores.items():
            if score >= threshold:
                name = contributors[email].get("name", email.split("@")[0])
                owners.append((email, name, score))

        owners.sort(key=lambda x: x[2], reverse=True)

        if len(owners) < min_owners:
            return owners[:max_owners] if owners else []

        return owners[:max_owners]
