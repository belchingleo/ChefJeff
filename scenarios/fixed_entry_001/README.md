# Fixed-entry development regression fixture

This deterministic, offline fixture checks urgent-pot handling and plate availability against the shared kitchen rules. It makes no model calls and is **not** the benchmark definition or evidence of model performance.

Run from the project root:

```sh
python3 scenarios/fixed_entry_001/run.py
python3 -m unittest discover -s tests -p test_fixed_entry.py
```

The runner generates state, decision-input examples and handwritten reference traces under `data/`. Generated JSONL traces are not part of the repository. These fixed reference actions are test utilities, never fallback agents for the real game.

Future benchmark work will use a scenario schema describing complete human–AI cooperative sessions and expand it through different players' participation. The schema and scoring protocol are not finalized.

本目录只用于开发回归。固定入口和人工参考动作不代表 benchmark 标准，也不代表模型已经具备合作能力。完整对局的 scenario schema 属于后续工作。
