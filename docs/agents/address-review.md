# Address a review

1. **List the open threads** of the pull request: its Files changed tab on GitHub shows which are still open. `gh api --paginate repos/<owner>/<repo>/pulls/<number>/comments` lists every inline review comment, resolved ones included (`gh pr view --comments` shows only the conversation).
2. **Reproduce first.** For each thread, confirm the problem before changing anything. Then fix it, or decide not to, with a reason.
3. **Fix in new commits** (no force-push), and run every check again (see `prepare-pr.md`).
4. **Reply in every thread:** the commit that fixes it, or why nothing changed. Leave resolving threads to the person who asked for the review, unless they ask you to.
5. **Summarise** in one comment on the pull request: what changed, what didn't, and why.
