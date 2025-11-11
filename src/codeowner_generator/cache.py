"""Cache management for repository analysis results."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AnalysisCache:
    """Manages caching of repository analysis results."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize cache manager.

        Args:
            cache_dir: Directory to store cache files (default: .codeowner-cache)
        """
        if cache_dir is None:
            cache_dir = Path.cwd() / ".codeowner-cache"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(
        self,
        repo_path: Path,
        branch: str,
        since: str | None,
        strategy: str,
        threshold: float,
        min_owners: int,
        max_owners: int,
        min_commits: int,
        min_lines: int,
        commits_weight: float,
        lines_weight: float,
        time_decay: bool,
        exclude_paths: list[str] | None,
        exclude_patterns: list[str] | None,
    ) -> str:
        """Generate cache key from analysis parameters.

        Args:
            repo_path: Repository path
            branch: Branch name
            since: Since date string
            strategy: Ownership strategy
            threshold: Ownership threshold
            min_owners: Minimum owners
            max_owners: Maximum owners
            min_commits: Minimum commits threshold
            min_lines: Minimum lines threshold
            commits_weight: Commits weight
            lines_weight: Lines weight
            time_decay: Time decay flag
            exclude_paths: Excluded paths
            exclude_patterns: Excluded patterns

        Returns:
            Cache key string
        """
        key_data = {
            "repo": str(repo_path.resolve()),
            "branch": branch,
            "since": since,
            "strategy": strategy,
            "threshold": threshold,
            "min_owners": min_owners,
            "max_owners": max_owners,
            "min_commits": min_commits,
            "min_lines": min_lines,
            "commits_weight": commits_weight,
            "lines_weight": lines_weight,
            "time_decay": time_decay,
            "exclude_paths": sorted(exclude_paths) if exclude_paths else [],
            "exclude_patterns": sorted(exclude_patterns) if exclude_patterns else [],
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _get_cache_file(self, cache_key: str) -> Path:
        """Get cache file path for a cache key.

        Args:
            cache_key: Cache key

        Returns:
            Path to cache file
        """
        return self.cache_dir / f"{cache_key}.json"

    def _get_repo_commit_hash(self, repo_path: Path, branch: str) -> str | None:
        """Get current commit hash for the repository.

        Args:
            repo_path: Repository path
            branch: Branch name

        Returns:
            Commit hash or None if unable to determine
        """
        try:
            from git import Repo

            repo = Repo(str(repo_path))
            try:
                commit = repo.commit(branch)
                return commit.hexsha
            except Exception:
                return None
        except Exception:
            return None

    def get(
        self,
        repo_path: Path,
        branch: str,
        since: str | None,
        strategy: str,
        threshold: float,
        min_owners: int,
        max_owners: int,
        min_commits: int,
        min_lines: int,
        commits_weight: float,
        lines_weight: float,
        time_decay: bool,
        exclude_paths: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Get cached analysis results if available and valid.

        Args:
            repo_path: Repository path
            branch: Branch name
            since: Since date string
            strategy: Ownership strategy
            threshold: Ownership threshold
            min_owners: Minimum owners
            max_owners: Maximum owners
            min_commits: Minimum commits threshold
            min_lines: Minimum lines threshold
            commits_weight: Commits weight
            lines_weight: Lines weight
            time_decay: Time decay flag
            exclude_paths: Excluded paths
            exclude_patterns: Excluded patterns

        Returns:
            Cached ownership data or None if cache miss/invalid
        """
        cache_key = self._get_cache_key(
            repo_path,
            branch,
            since,
            strategy,
            threshold,
            min_owners,
            max_owners,
            min_commits,
            min_lines,
            commits_weight,
            lines_weight,
            time_decay,
            exclude_paths,
            exclude_patterns,
        )
        cache_file = self._get_cache_file(cache_key)

        if not cache_file.exists():
            return None

        try:
            with cache_file.open() as f:
                cache_data = json.load(f)

            current_commit = self._get_repo_commit_hash(repo_path, branch)
            cached_commit = cache_data.get("commit_hash")

            if current_commit and cached_commit and current_commit != cached_commit:
                logger.debug(
                    f"Cache invalidated: commit hash changed "
                    f"({cached_commit} -> {current_commit})"
                )
                return None

            logger.info(f"Using cached analysis results from {cache_file.name}")
            return cache_data.get("ownership_data")

        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Failed to load cache: {e}")
            return None

    def set(
        self,
        repo_path: Path,
        branch: str,
        since: str | None,
        strategy: str,
        threshold: float,
        min_owners: int,
        max_owners: int,
        min_commits: int,
        min_lines: int,
        commits_weight: float,
        lines_weight: float,
        time_decay: bool,
        ownership_data: dict[str, Any],
        exclude_paths: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        """Store analysis results in cache.

        Args:
            repo_path: Repository path
            branch: Branch name
            since: Since date string
            strategy: Ownership strategy
            threshold: Ownership threshold
            min_owners: Minimum owners
            max_owners: Maximum owners
            min_commits: Minimum commits threshold
            min_lines: Minimum lines threshold
            commits_weight: Commits weight
            lines_weight: Lines weight
            time_decay: Time decay flag
            ownership_data: Ownership data to cache
            exclude_paths: Excluded paths
            exclude_patterns: Excluded patterns
        """
        cache_key = self._get_cache_key(
            repo_path,
            branch,
            since,
            strategy,
            threshold,
            min_owners,
            max_owners,
            min_commits,
            min_lines,
            commits_weight,
            lines_weight,
            time_decay,
            exclude_paths,
            exclude_patterns,
        )
        cache_file = self._get_cache_file(cache_key)

        commit_hash = self._get_repo_commit_hash(repo_path, branch)

        cache_data = {
            "commit_hash": commit_hash,
            "ownership_data": ownership_data,
        }

        try:
            with cache_file.open("w") as f:
                json.dump(cache_data, f, indent=2)
            logger.debug(f"Cached analysis results to {cache_file.name}")
        except OSError as e:
            logger.warning(f"Failed to write cache: {e}")

    def clear(self) -> None:
        """Clear all cache files."""
        if not self.cache_dir.exists():
            return

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except OSError:
                pass

        logger.info(f"Cleared {count} cache files")

    def serialize_ownership_data(
        self, ownership_data: dict[Path, list[tuple[str, str, float]]]
    ) -> dict[str, Any]:
        """Serialize ownership data for JSON storage.

        Args:
            ownership_data: Ownership data with Path keys

        Returns:
            Serialized dictionary
        """
        return {
            str(file_path): [
                {"email": email, "name": name, "score": score}
                for email, name, score in owners
            ]
            for file_path, owners in ownership_data.items()
        }

    def deserialize_ownership_data(
        self, serialized_data: dict[str, Any]
    ) -> dict[Path, list[tuple[str, str, float]]]:
        """Deserialize ownership data from JSON.

        Args:
            serialized_data: Serialized dictionary

        Returns:
            Ownership data with Path keys
        """
        return {
            Path(file_path): [
                (owner["email"], owner["name"], owner["score"])
                for owner in owners
            ]
            for file_path, owners in serialized_data.items()
        }
