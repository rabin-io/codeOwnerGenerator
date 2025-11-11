"""CLI entry point for codeowner-generator."""

import logging
import sys
from pathlib import Path

import click

from .analyzer import OwnershipStrategy, RepositoryAnalyzer
from .cache import AnalysisCache
from .codeowners import CodeOwnersGenerator
from .git_utils import GitRepository

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--repo-path",
    "-r",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=Path.cwd(),
    help="Path to git repository (default: current directory)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path (default: .gitlab/CODEOWNERS)",
)
@click.option(
    "--strategy",
    "-s",
    type=click.Choice(
        [s.value for s in OwnershipStrategy], case_sensitive=False
    ),
    default=OwnershipStrategy.COMMITS.value,
    help="Ownership calculation strategy: commits, lines, recent, or weighted",
)
@click.option(
    "--threshold",
    "-t",
    type=float,
    default=0.1,
    help="Minimum ownership percentage (0-1, default: 0.1)",
)
@click.option(
    "--min-owners",
    type=int,
    default=1,
    help="Minimum owners per pattern (default: 1)",
)
@click.option(
    "--max-owners",
    "-m",
    type=int,
    default=2,
    help="Maximum owners per pattern (default: 2)",
)
@click.option(
    "--min-commits",
    type=int,
    default=0,
    help="Minimum number of commits required for an owner (default: 0)",
)
@click.option(
    "--min-lines",
    type=int,
    default=0,
    help="Minimum number of lines required for an owner (default: 0)",
)
@click.option(
    "--since",
    type=str,
    default=None,
    help="Only consider commits since date (e.g., '6 months ago', '2024-01-01')",
)
@click.option(
    "--branch",
    "-b",
    type=str,
    default=None,
    help="Branch to analyze (default: auto-detect main/master)",
)
@click.option(
    "--group-by",
    type=click.Choice(["directory", "extension", "file", "mixed"], case_sensitive=False),
    default="directory",
    help="Group files by directory, extension, file, or mixed (default: directory)",
)
@click.option(
    "--granularity-level",
    "-g",
    type=int,
    default=1,
    help="Granularity level for patterns (1=coarse, higher=more granular, default: 1)",
)
@click.option(
    "--exclude-path",
    multiple=True,
    help="Exclude paths from analysis (can be specified multiple times)",
)
@click.option(
    "--exclude-pattern",
    multiple=True,
    help="Exclude glob patterns from analysis (can be specified multiple times)",
)
@click.option(
    "--username-mapping",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="JSON file mapping old usernames/emails to new ones",
)
@click.option(
    "--commits-weight",
    type=float,
    default=0.4,
    help="Weight for commits in weighted strategy (default: 0.4)",
)
@click.option(
    "--lines-weight",
    type=float,
    default=0.6,
    help="Weight for lines in weighted strategy (default: 0.6)",
)
@click.option(
    "--no-time-decay",
    is_flag=True,
    help="Disable time decay for weighted strategy (default: time decay enabled)",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Disable cache and force re-analysis",
)
@click.option(
    "--clear-cache",
    is_flag=True,
    help="Clear all cached analysis results",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory to store cache files (default: .codeowner-cache)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show analysis without generating CODEOWNERS file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging",
)
def main(
    repo_path: Path,
    output: Path | None,
    strategy: str,
    threshold: float,
    min_owners: int,
    max_owners: int,
    min_commits: int,
    min_lines: int,
    since: str | None,
    branch: str | None,
    group_by: str,
    granularity_level: int,
    exclude_path: tuple[str, ...],
    exclude_pattern: tuple[str, ...],
    username_mapping: Path | None,
    commits_weight: float,
    lines_weight: float,
    no_time_decay: bool,
    no_cache: bool,
    clear_cache: bool,
    cache_dir: Path | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Generate GitLab CODEOWNERS file by analyzing git repository history."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        cache = AnalysisCache(cache_dir=cache_dir if cache_dir else repo_path / ".codeowner-cache")

        if clear_cache:
            cache.clear()
            logger.info("Cache cleared")
            return

        logger.info(f"Analyzing repository: {repo_path}")
        repo = GitRepository(repo_path)

        if output is None:
            output = repo_path / ".gitlab" / "CODEOWNERS"
            logger.info(f"Using default output: {output}")

        if branch is None:
            branch = repo.get_default_branch()
            logger.info(f"Using branch: {branch}")

        since_date = None
        if since:
            since_date = repo.parse_since_date(since)
            logger.info(f"Analyzing commits since: {since_date}")

        strategy_enum = OwnershipStrategy(strategy.lower())
        logger.info(f"Using strategy: {strategy_enum.value}")

        username_map = {}
        if username_mapping:
            username_map = CodeOwnersGenerator.load_username_mapping(username_mapping)
            logger.info(f"Loaded {len(username_map)} username mappings")

        ownership_data = None
        if not no_cache:
            cached_data = cache.get(
                repo_path=repo_path,
                branch=branch,
                since=since,
                strategy=strategy_enum.value,
                threshold=threshold,
                min_owners=min_owners,
                max_owners=max_owners,
                min_commits=min_commits,
                min_lines=min_lines,
                commits_weight=commits_weight,
                lines_weight=lines_weight,
                time_decay=not no_time_decay,
                exclude_paths=list(exclude_path) if exclude_path else None,
                exclude_patterns=list(exclude_pattern) if exclude_pattern else None,
            )

            if cached_data:
                ownership_data = cache.deserialize_ownership_data(cached_data)

        if ownership_data is None:
            analyzer = RepositoryAnalyzer(repo)
            ownership_data = analyzer.analyze(
                strategy=strategy_enum,
                since=since_date,
                branch=branch,
                threshold=threshold,
                min_owners=min_owners,
                max_owners=max_owners,
                min_commits=min_commits,
                min_lines=min_lines,
                commits_weight=commits_weight,
                lines_weight=lines_weight,
                time_decay=not no_time_decay,
                exclude_paths=list(exclude_path) if exclude_path else None,
                exclude_patterns=list(exclude_pattern) if exclude_pattern else None,
            )

            if not no_cache:
                cache.set(
                    repo_path=repo_path,
                    branch=branch,
                    since=since,
                    strategy=strategy_enum.value,
                    threshold=threshold,
                    min_owners=min_owners,
                    max_owners=max_owners,
                    min_commits=min_commits,
                    min_lines=min_lines,
                    commits_weight=commits_weight,
                    lines_weight=lines_weight,
                    time_decay=not no_time_decay,
                    ownership_data=cache.serialize_ownership_data(ownership_data),
                    exclude_paths=list(exclude_path) if exclude_path else None,
                    exclude_patterns=list(exclude_pattern) if exclude_pattern else None,
                )

        logger.info(f"Found ownership data for {len(ownership_data)} files")

        if dry_run:
            logger.info("Dry run mode - showing sample results:")
            sample_files = list(ownership_data.items())[:10]
            for file_path, owners in sample_files:
                owners_str = ", ".join(
                    [f"{name} ({email})" for email, name, score in owners]
                )
                logger.info(f"  {file_path}: {owners_str}")
            if len(ownership_data) > 10:
                logger.info(f"  ... and {len(ownership_data) - 10} more files")
            return

        generator = CodeOwnersGenerator(username_mapping=username_map)
        generator.generate(
            ownership_data,
            output,
            group_by=group_by,
            granularity_level=granularity_level,
            exclude_paths=list(exclude_path) if exclude_path else None,
            exclude_patterns=list(exclude_pattern) if exclude_pattern else None,
        )

        logger.info(f"CODEOWNERS file generated: {output}")

    except ValueError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
