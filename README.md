# GitLab CODEOWNERS Generator

A Python tool that analyzes a Git repository's commit history and automatically generates a GitLab CODEOWNERS file based on code ownership patterns.

## Features

- **Multiple Ownership Strategies**: Choose how ownership is calculated:
  - `commits`: Based on number of commits per file
  - `lines`: Based on lines of code added
  - `recent`: Based on recent commits (configurable time window)
  - `weighted`: Configurable weighted combination of commits and lines with optional time decay

- **Configurable History**: Limit analysis to commits within a specific time window
- **Flexible Pattern Granularity**: Group ownership by directory, file extension, individual files, or mixed patterns with configurable granularity levels
- **Pattern Exclusion**: Exclude specific paths or glob patterns from analysis and output
- **Multiple Owners**: Configure minimum and maximum owners per pattern (default: 1-2 owners)
- **Minimum Thresholds**: Set minimum commits or lines of code required for ownership
- **Username Mapping**: Map old usernames/emails to new ones via JSON file
- **Configurable Weights**: Customize commit/line weights and time decay for weighted strategy
- **Branch Selection**: Analyze default branch (auto-detected) or specify a branch
- **Automatic Pattern Optimization**: Consolidates patterns when all nested folders have the same owners
- **GitLab Compatible**: Generates CODEOWNERS file in GitLab format, defaults to `.gitlab/CODEOWNERS`

## Installation

This project uses `uv` for dependency management. Install dependencies:

```bash
uv sync
```

## Usage

### Basic Usage

```bash
uv run codeowner-generator
```

This will analyze the current directory as a git repository and generate a `.gitlab/CODEOWNERS` file.

### Options

```bash
uv run codeowner-generator --help
```

**Common Options:**

- `--repo-path, -r`: Path to git repository (default: current directory)
- `--output, -o`: Output file path (default: `.gitlab/CODEOWNERS`)
- `--strategy, -s`: Ownership strategy (`commits`, `lines`, `recent`, `weighted`)
- `--threshold, -t`: Minimum ownership percentage 0-1 (default: 0.1)
- `--min-owners`: Minimum owners per pattern (default: 1)
- `--max-owners, -m`: Maximum owners per pattern (default: 2)
- `--min-commits`: Minimum number of commits required for an owner (default: 0)
- `--min-lines`: Minimum number of lines required for an owner (default: 0)
- `--since`: Only consider commits since date (e.g., `"6 months ago"`, `"2024-01-01"`)
- `--branch, -b`: Branch to analyze (default: auto-detect main/master)
- `--group-by`: Group files by `directory`, `extension`, `file`, or `mixed` (default: `directory`)
- `--granularity-level, -g`: Granularity level for patterns (1=coarse, higher=more granular, default: 1)
- `--exclude-path`: Exclude paths from analysis (can be specified multiple times)
- `--exclude-pattern`: Exclude glob patterns from analysis (can be specified multiple times)
- `--username-mapping`: JSON file mapping old usernames/emails to new ones
- `--commits-weight`: Weight for commits in weighted strategy (default: 0.4)
- `--lines-weight`: Weight for lines in weighted strategy (default: 0.6)
- `--no-time-decay`: Disable time decay for weighted strategy (default: enabled)
- `--no-cache`: Disable cache and force re-analysis
- `--clear-cache`: Clear all cached analysis results
- `--cache-dir`: Directory to store cache files (default: `.codeowner-cache`)
- `--dry-run`: Show analysis without generating file
- `--verbose, -v`: Enable verbose logging

### Examples

**Analyze with weighted strategy, last 6 months only:**
```bash
uv run codeowner-generator --strategy weighted --since "6 months ago"
```

**Generate CODEOWNERS for specific branch with custom output:**
```bash
uv run codeowner-generator --branch develop --output custom/path/CODEOWNERS
```

**Group by file extension with higher threshold:**
```bash
uv run codeowner-generator --group-by extension --threshold 0.2
```

**Exclude test files and node_modules:**
```bash
uv run codeowner-generator --exclude-path tests --exclude-pattern "node_modules/**" --exclude-pattern "*.test.js"
```

**Use username mapping file:**
```bash
uv run codeowner-generator --username-mapping username-map.json
```

**Custom weighted strategy with time decay disabled:**
```bash
uv run codeowner-generator --strategy weighted --commits-weight 0.5 --lines-weight 0.5 --no-time-decay
```

**Require minimum commits and lines:**
```bash
uv run codeowner-generator --min-commits 5 --min-lines 100
```

**Mixed patterns with higher granularity:**
```bash
uv run codeowner-generator --group-by mixed --granularity-level 2
```

**Dry run to preview results:**
```bash
uv run codeowner-generator --dry-run --verbose
```

**Use cache to speed up repeated runs:**
```bash
# First run - analyzes and caches results
uv run codeowner-generator

# Second run - uses cached results (much faster)
uv run codeowner-generator

# Force re-analysis ignoring cache
uv run codeowner-generator --no-cache

# Clear all cached results
uv run codeowner-generator --clear-cache
```

## Ownership Strategies

### Commits Strategy
Calculates ownership based on the number of commits each author made to a file. Simple and straightforward.

### Lines Strategy
Calculates ownership based on lines of code added. Useful when commit frequency doesn't reflect actual contribution.

### Recent Strategy
Focuses on recent activity (last 6 months by default, or custom `--since` date). Useful for identifying current maintainers.

### Weighted Strategy
Combines commits and lines with configurable weights (default: 40% commits, 60% lines). Supports time decay to weight recent commits more heavily (enabled by default).

## Output Format

The generated CODEOWNERS file follows GitLab's format and is automatically optimized:

```
# CODEOWNERS file generated by codeowner-generator
# This file defines code ownership for GitLab

src/frontend/**	@alice @bob
src/backend/**	@charlie @dave
*.py	@python-team
*.js	@frontend-team
```

Patterns are automatically optimized to consolidate nested folders with the same owners, reducing file size while maintaining accuracy.

## Development

### Linting and Formatting

```bash
# Check for linting issues
uv run ruff check .

# Format code
uv run ruff format .
```

### Project Structure

```
codeOwnerGenerator/
├── src/
│   └── codeowner_generator/
│       ├── __init__.py
│       ├── main.py              # CLI entry point
│       ├── analyzer.py           # Git repository analysis logic
│       ├── codeowners.py         # CODEOWNERS file generation
│       └── git_utils.py          # Git operations wrapper
├── pyproject.toml
└── README.md
```

## Username Mapping

Create a JSON file to map old usernames or emails to new GitLab usernames:

```json
{
  "old-username": "new-username",
  "old.email@example.com": "new-username",
  "another@example.com": "another-username"
}
```

Then use it with:
```bash
uv run codeowner-generator --username-mapping username-map.json
```

## Pattern Granularity

The `--granularity-level` option controls how specific directory patterns are:

- **Level 1** (default): Coarse patterns like `src/**`, `tests/**`
- **Level 2**: More specific like `src/frontend/**`, `src/backend/**`
- **Level 3+**: Even more granular patterns

Higher levels create more specific patterns but may result in more entries in the CODEOWNERS file.

## Pattern Optimization

The tool automatically optimizes patterns by consolidating them when all nested folders have the same owners. This reduces the size of the CODEOWNERS file while maintaining the same ownership rules.

**Example:**

Before optimization:
```
ansible-playbooks/aggregated-logging/roles/**       @rabin-io
ansible-playbooks/aggregated-logging/group_vars/**  @rabin-io
ansible-playbooks/aggregated-logging/templates/**   @rabin-io
```

After optimization:
```
ansible-playbooks/aggregated-logging/**             @rabin-io
```

**How it works:**
- Patterns are processed bottom-up (deepest first)
- Sibling patterns (same parent directory) with identical owners are consolidated
- The process repeats until no more consolidations are possible
- Optimization preserves ownership accuracy while reducing file size

## Caching

The tool automatically caches analysis results to avoid re-analyzing unchanged code. Cache files are stored in `.codeowner-cache/` directory by default.

**How it works:**
- Cache is keyed by repository path, branch, analysis parameters, and commit hash
- If the commit hash changes, cache is automatically invalidated
- Cache significantly speeds up repeated runs with the same parameters
- Use `--no-cache` to force fresh analysis
- Use `--clear-cache` to remove all cached results

**Cache location:**
- Default: `.codeowner-cache/` in the repository root
- Custom: Use `--cache-dir` to specify a different location

## License

MIT
