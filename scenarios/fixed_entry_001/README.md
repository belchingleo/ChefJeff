# Fixed-entry development regression fixture

This deterministic, offline fixture checks urgent-pot handling and plate availability against the shared kitchen rules. It makes no model calls and is **not** the benchmark definition or evidence of model performance.

Run from the project root:

```sh
python3 scenarios/fixed_entry_001/run.py
python3 -m unittest discover -s tests -p test_fixed_entry.py
```

The runner generates state, decision-input examples and handwritten reference traces under `data/`. Generated JSONL traces are not part of the repository. These fixed reference actions are test utilities, never fallback agents for the real game.

Future benchmark work will use a scenario schema describing complete human–AI cooperative sessions and expand it through different players' participation. The schema and scoring protocol are not finalized.

---

## 中文说明

# 固定入口开发回归用例

此确定性的离线用例检查紧急锅处理与餐盘可用性，不调用模型。它是开发测试，不定义 benchmark，也不证明模型表现。

在项目根目录运行：

```sh
python3 scenarios/fixed_entry_001/run.py
python3 -m unittest discover -s tests -p test_fixed_entry.py
```

运行器在 `data/` 生成状态、决策输入示例和手写参考轨迹，生成的 JSONL 不进入仓库。固定动作仅用于测试，不作为真实游戏的脚本兜底。

未来 benchmark 以完整人类—AI 合作对局的 scenario schema 为基础，随不同玩家参与扩充，具体 schema 与评分协议由后续共创定义。
