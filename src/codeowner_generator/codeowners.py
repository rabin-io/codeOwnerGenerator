"""Generate GitLab CODEOWNERS file from ownership analysis."""

import json
from collections import defaultdict
from pathlib import Path

from .analyzer import RepositoryAnalyzer


class CodeOwnersGenerator:
    """Generates CODEOWNERS file from ownership analysis."""

    def __init__(
        self,
        analyzer: RepositoryAnalyzer | None = None,
        username_mapping: dict[str, str] | None = None,
    ) -> None:
        """Initialize CODEOWNERS generator.

        Args:
            analyzer: RepositoryAnalyzer instance (optional, not currently used)
            username_mapping: Dictionary mapping email/old_username to new username
        """
        self.analyzer = analyzer
        self.username_mapping = username_mapping or {}

    def generate(
        self,
        ownership_data: dict[Path, list[tuple[str, str, float]]],
        output_path: Path,
        group_by: str = "directory",
        granularity_level: int = 1,
        exclude_paths: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        """Generate CODEOWNERS file.

        Args:
            ownership_data: Ownership data from analyzer
            output_path: Path to write CODEOWNERS file
            group_by: How to group files: "directory", "extension", "file", or "mixed"
            granularity_level: Level of granularity (1=coarse, higher=more granular)
            exclude_paths: List of paths to exclude from output
            exclude_patterns: List of glob patterns to exclude from output
        """
        import fnmatch

        exclude_paths = exclude_paths or []
        exclude_patterns = exclude_patterns or []

        filtered_data = {}
        for file_path, owners in ownership_data.items():
            file_str = str(file_path)

            if any(file_str.startswith(exclude) for exclude in exclude_paths):
                continue

            if any(fnmatch.fnmatch(file_str, pattern) for pattern in exclude_patterns):
                continue

            filtered_data[file_path] = owners

        if group_by == "directory":
            patterns = self._generate_directory_patterns(filtered_data, granularity_level)
        elif group_by == "extension":
            patterns = self._generate_extension_patterns(filtered_data)
        elif group_by == "file":
            patterns = self._generate_file_patterns(filtered_data)
        elif group_by == "mixed":
            patterns = self._generate_mixed_patterns(filtered_data, granularity_level)
        else:
            raise ValueError(f"Unknown group_by value: {group_by}")

        patterns = self._optimize_patterns(patterns)
        self._write_codeowners_file(output_path, patterns)

    def _generate_directory_patterns(
        self,
        ownership_data: dict[Path, list[tuple[str, str, float]]],
        granularity_level: int = 1,
    ) -> list[tuple[str, list[str]]]:
        """Generate directory-level patterns.

        Args:
            ownership_data: Ownership data
            granularity_level: Level of granularity (1=coarse, higher=more granular)

        Returns:
            List of (pattern, owners) tuples
        """
        directory_owners: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for file_path, owners in ownership_data.items():
            parts = file_path.parts
            if len(parts) == 1:
                dir_path = "."
            else:
                depth = min(granularity_level, len(parts) - 1)
                dir_path = str(Path(*parts[:depth]))

            for email, name, score in owners:
                formatted_username = self._format_owner(email)
                directory_owners[dir_path][formatted_username] = max(
                    directory_owners[dir_path][formatted_username], score
                )

        patterns = []
        for dir_path, owner_scores in directory_owners.items():
            sorted_owners = sorted(owner_scores.items(), key=lambda x: x[1], reverse=True)
            owner_names = [username for username, _ in sorted_owners]
            pattern = f"{dir_path}/**" if dir_path != "." else "**"
            patterns.append((pattern, owner_names))

        return sorted(patterns, key=lambda x: (x[0].count("/"), x[0]))[::-1]

    def _generate_mixed_patterns(
        self,
        ownership_data: dict[Path, list[tuple[str, str, float]]],
        granularity_level: int = 1,
    ) -> list[tuple[str, list[str]]]:
        """Generate mixed patterns (directory + extension).

        Args:
            ownership_data: Ownership data
            granularity_level: Level of granularity

        Returns:
            List of (pattern, owners) tuples
        """
        dir_patterns = self._generate_directory_patterns(ownership_data, granularity_level)
        ext_patterns = self._generate_extension_patterns(ownership_data)

        return dir_patterns + ext_patterns

    def _generate_extension_patterns(
        self, ownership_data: dict[Path, list[tuple[str, str, float]]]
    ) -> list[tuple[str, list[str]]]:
        """Generate extension-level patterns.

        Args:
            ownership_data: Ownership data

        Returns:
            List of (pattern, owners) tuples
        """
        extension_owners: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for file_path, owners in ownership_data.items():
            ext = file_path.suffix or "no-extension"
            for email, name, score in owners:
                formatted_username = self._format_owner(email)
                extension_owners[ext][formatted_username] = max(
                    extension_owners[ext][formatted_username], score
                )

        patterns = []
        for ext, owner_scores in extension_owners.items():
            sorted_owners = sorted(owner_scores.items(), key=lambda x: x[1], reverse=True)
            owner_names = [username for username, _ in sorted_owners]
            pattern = f"*{ext}" if ext != "no-extension" else "*"
            patterns.append((pattern, owner_names))

        return patterns

    def _generate_file_patterns(
        self, ownership_data: dict[Path, list[tuple[str, str, float]]]
    ) -> list[tuple[str, list[str]]]:
        """Generate file-level patterns.

        Args:
            ownership_data: Ownership data

        Returns:
            List of (pattern, owners) tuples
        """
        patterns = []
        for file_path, owners in ownership_data.items():
            owner_usernames: dict[str, float] = {}
            for email, _, score in owners:
                formatted_username = self._format_owner(email)
                owner_usernames[formatted_username] = max(
                    owner_usernames.get(formatted_username, 0), score
                )
            sorted_owners = sorted(owner_usernames.items(), key=lambda x: x[1], reverse=True)
            owner_names = [username for username, _ in sorted_owners]
            patterns.append((str(file_path), owner_names))

        return sorted(patterns)

    def _format_owner(self, email: str) -> str:
        """Format owner email as GitLab username.

        Uses username mapping if available, otherwise extracts from email.

        Args:
            email: Contributor email

        Returns:
            Formatted owner string (e.g., @username)
        """
        if email in self.username_mapping:
            username = self.username_mapping[email]
        else:
            username = email.split("@")[0]
            if username in self.username_mapping:
                username = self.username_mapping[username]

        return f"@{username}"

    @classmethod
    def load_username_mapping(cls, mapping_file: Path) -> dict[str, str]:
        """Load username mapping from JSON file.

        Args:
            mapping_file: Path to JSON file with key-value pairs

        Returns:
            Dictionary mapping old username/email to new username
        """
        if not mapping_file.exists():
            return {}

        try:
            with mapping_file.open() as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to load username mapping: {e}") from e

    def _optimize_patterns(
        self, patterns: list[tuple[str, list[str]]]
    ) -> list[tuple[str, list[str]]]:
        """Optimize patterns by consolidating when all nested folders have same owners.

        Args:
            patterns: List of (pattern, owners) tuples

        Returns:
            Optimized list of (pattern, owners) tuples
        """
        if not patterns:
            return patterns

        pattern_dict = dict(patterns)
        changed = True

        while changed:
            changed = False
            patterns_by_depth: dict[int, list[str]] = defaultdict(list)

            for pattern in pattern_dict.keys():
                if pattern == "**":
                    continue
                pattern_path = pattern.rstrip("/**")
                depth = pattern_path.count("/") if pattern_path else 0
                patterns_by_depth[depth].append(pattern)

            if not patterns_by_depth:
                break

            max_depth = max(patterns_by_depth.keys())
            optimized: dict[str, list[str]] = {}
            patterns_to_remove: set[str] = set()

            for depth in range(max_depth, -1, -1):
                if depth not in patterns_by_depth:
                    continue

                parent_groups: dict[str, list[str]] = defaultdict(list)

                for pattern in patterns_by_depth[depth]:
                    if pattern in patterns_to_remove:
                        continue

                    if pattern == "**":
                        optimized[pattern] = pattern_dict[pattern]
                        continue

                    pattern_path = pattern.rstrip("/**")
                    if not pattern_path:
                        optimized[pattern] = pattern_dict[pattern]
                        continue

                    parts = pattern_path.split("/")
                    if len(parts) == 1:
                        optimized[pattern] = pattern_dict[pattern]
                        continue

                    parent = "/".join(parts[:-1])
                    parent_groups[parent].append(pattern)

                for parent, child_patterns in parent_groups.items():
                    if len(child_patterns) < 2:
                        for pattern in child_patterns:
                            if pattern not in optimized and pattern not in patterns_to_remove:
                                optimized[pattern] = pattern_dict[pattern]
                        continue

                    parent_pattern = f"{parent}/**"
                    child_owners_sets = [
                        tuple(sorted(pattern_dict[cp])) for cp in child_patterns
                    ]

                    if len(set(child_owners_sets)) == 1:
                        if parent_pattern not in pattern_dict or tuple(
                            sorted(pattern_dict[parent_pattern])
                        ) == child_owners_sets[0]:
                            optimized[parent_pattern] = pattern_dict[child_patterns[0]]
                            patterns_to_remove.update(child_patterns)
                            changed = True
                        else:
                            for pattern in child_patterns:
                                if pattern not in optimized and pattern not in patterns_to_remove:
                                    optimized[pattern] = pattern_dict[pattern]
                    else:
                        for pattern in child_patterns:
                            if pattern not in optimized and pattern not in patterns_to_remove:
                                optimized[pattern] = pattern_dict[pattern]

            for pattern, owners in pattern_dict.items():
                if pattern not in optimized and pattern not in patterns_to_remove:
                    optimized[pattern] = owners

            pattern_dict = optimized

        return sorted(pattern_dict.items(), key=lambda x: (x[0].count("/"), x[0]))[::-1]

    def _write_codeowners_file(
        self, output_path: Path, patterns: list[tuple[str, list[str]]]
    ) -> None:
        """Write CODEOWNERS file.

        Args:
            output_path: Path to write file
            patterns: List of (pattern, owners) tuples
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not patterns:
            with output_path.open("w") as f:
                f.write("# CODEOWNERS file generated by codeowner-generator\n")
                f.write("# This file defines code ownership for GitLab\n\n")
            return

        max_pattern_length = max(len(pattern) for pattern, _ in patterns)
        padding_length = max(max_pattern_length + 2, 40)

        with output_path.open("w") as f:
            f.write("# CODEOWNERS file generated by codeowner-generator\n")
            f.write("# This file defines code ownership for GitLab\n\n")

            for pattern, owners in patterns:
                owners_str = " ".join(owners)
                padded_pattern = pattern.ljust(padding_length)
                f.write(f"{padded_pattern}{owners_str}\n")
