#!/usr/bin/env bash

# finds all Git repositories under a folder and rewrites their GitHub remote from git@github.com to git@github-personal
# ./migrate-git-remotes.sh ~/dev true   # Dry run only
# ./migrate-git-remotes.sh ~/dev	# apply changes


BASE_DIR="${1:-.}"
DRY_RUN="${2:-false}"

echo "Scanning recursively in: $BASE_DIR"
echo "Dry run: $DRY_RUN"
echo "----------------------------------------"

# Find all .git directories safely
find "$BASE_DIR" -type d -name ".git" 2>/dev/null | while read -r gitdir; do

    repo_dir="$(dirname "$gitdir")"

    echo "Repo: $repo_dir"

    (
        cd "$repo_dir" || exit 0

        remote_url=$(git remote get-url origin 2>/dev/null)

        if [[ -z "$remote_url" ]]; then
            echo "  No origin remote"
            echo "----------------------------------------"
            exit 0
        fi

        echo "  Current: $remote_url"

        # Only convert github.com SSH remotes
        if [[ "$remote_url" == git@github.com:* ]]; then

            repo_path="${remote_url#git@github.com:}"
            new_url="git@github-personal:${repo_path}"

            if [[ "$DRY_RUN" == "true" ]]; then
                echo "  [DRY RUN] Would set: $new_url"
            else
                git remote set-url origin "$new_url"
                echo "  ✔ Updated -> $new_url"
            fi

        else
            echo "  Skipped (not git@github.com SSH)"
        fi

        echo "----------------------------------------"
    )

done

echo "Done."
