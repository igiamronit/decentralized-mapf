# Project instructions

- Do not create commits unless the user explicitly requests a commit.
- Never add the assistant, an AI tool, or an AI service as a commit coauthor. Do not add AI `Co-authored-by` trailers.
- Before implementing project modules, read `README.md`, `docs/TEAM_BUILD_GUIDE.md`, and `docs/PROJECT_SPEC.md`. Follow the guide's assignments and frozen interfaces, the specification's research requirements, and the core-before-extensions scope. Flag discrepancies rather than silently changing requirements.
- Update `README.md` when completing meaningful work. Briefly explain what changed, where it lives, how to use or verify it, and any remaining integration dependencies. Keep it an overview; link to the guide/specification instead of repeating their detailed content or listing every small edit.
- Leave enough context for the next teammate and their AI agent to build on the work. Document non-obvious behavior and assumptions in module/class/function docstrings; keep shared contracts and integration requirements synchronized with `docs/TEAM_BUILD_GUIDE.md`. Local scratch notes are not the project handoff.
- Keep implementations modular. Reuse the shared interfaces and existing helpers, pass collaborators into the runner, and avoid duplicate implementations or scripts that do the same work.
- Run checks appropriate to the change and report what was actually verified. Distinguish test doubles and illustrative figures from implemented features and experimental results; state unfinished work clearly.
- Keep observation and communication as independent settings.
- Keep generated animations, experiment results, and traces under `outputs/`; preserve selected documentation figures under `docs/figures/`.
- Do not commit local virtual environments, credentials, or generated caches.
