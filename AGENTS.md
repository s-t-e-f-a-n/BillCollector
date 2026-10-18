<!-- OPENWIKI:START -->

## OpenWiki

This repository has a generated `openwiki/` evidence index. It is optional just-in-time context, not required startup reading.

- Do not enumerate, preload, or search wikis at task start. Use retrieval when the user asks for it, when unfamiliar architecture or dependency behavior materially affects the task, or when source inspection leaves an important uncertainty. Stop once the question is grounded.
- When those conditions apply and OpenWiki retrieval tools are available, use `openwiki_search` for just-in-time context and `openwiki_read` for the relevant complete sections. If search returns `workspace_required`, ask which listed workspace to use and retry with its ID.
- Use `openwiki_list_workspaces` or `openwiki_list_wikis` when workspace membership itself needs to be discovered.
- If the retrieval tools are unavailable, read `openwiki/quickstart.md` and follow its links to the relevant pages.
- Treat source code and tests as authoritative. A brief's unknowns and review items are verification gaps, not automatic requirements.
- Prefer the narrowest quiet validation that proves the changed behavior. Preserve complete failure output.

The scheduled OpenWiki GitHub Actions workflow refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->

## Private agent artifacts

- `openwiki/`, this file, `.openwikiignore`, and
  `.github/workflows/openwiki-update.yml` are private local agent context; they
  must never be published to the GitHub mirror (enforced by the `STRIP` list in
  `.private/sync_github.sh`).
- The wiki is refreshed locally with `openwiki code --update`; the GitHub
  Actions workflow is kept in the private repo only as the record of the setup
  and is not published.
- When a wiki page and the code disagree, the code wins; hand-editing generated
  pages only when explicitly asked (consistent with the managed block above).
- Detailed openwiki usage policy (consult depth, claims usage, page updates on
  change) is deferred to a follow-up task.
