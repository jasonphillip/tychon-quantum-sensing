# TVW repository layout

> Extracted verbatim from CLAUDE.md (2026-07-17 progressive-disclosure restructure).

```
~/projects/tychon-verification-workbench/
├── CLAUDE.md             this file
├── STAGES.md             stop-gate roadmap
├── README.md             project overview
├── .gitignore
└── tvw/
    ├── configs/          endpoints.yaml, model lineup, MCP wiring
    ├── audits/           audit-NNN.md punch lists, verdict CSVs
    ├── scripts/          render_report.sh, eod_close.sh (multi-repo EOD sweep + push driver),
    │                     dispatch.sh (file-based cross-lane dispatch queue)
    ├── services/         systemd unit drafts for NIMs / llama.cpp
    └── source/
        ├── repos/        symlinks → ~/projects/{4 repos}
        └── sbir/         symlink → ~/projects/tychon-sbir/docs
```

("this file" in the tree refers to CLAUDE.md at the repo root, where the tree
originally lived.)
