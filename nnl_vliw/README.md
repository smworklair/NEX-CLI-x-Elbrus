# `nnl_vliw`: NNL Cores Selecting a Portfolio Group

> **Status: experiment.** Not wired into the CLI. The active NNL scheduler wrapper is `nex_core/` (see [`../docs/TINY.md`](../docs/TINY.md)).

Evaluation of the NNL (Neural Network Lego) architecture on Elbrus VLIW scheduling.
Two cores of two blocks each (~100K and ~200K parameters) were trained to predict which TINY AI portfolio group achieves the best result on a graph, and to cross-check each other.

**Bottom line.** Technically, NNL works: blocks assemble cleanly, pass the linter, and hot-plugging does not perturb neighbors. In quality, the cores match standard classifiers on the same features, group selection is weak, and cross-core verification performs no better than random abstention. The production path (`TinyFlashScheduler`) does not need this.

## How NNL Maps to the Task

- **Single composition.** Each core is a motherboard with blocks; output is a joint softmax over "none" and block answers. "None" means "unsure, run the full portfolio".
- **Blocks partition the graph domain.** Core A partitions by dividers; Core B partitions by memory operations.
- **Bus.** One block writes its domain concept; the second reads it on cycle 2.
- **Cross-core check.** Different partitions, token dimensions (48 vs. 64), and hashing salts.
- **Language.** A graph is encoded as a bag of tokens: op types, critical path, resource bound, width, edges, and operations on the critical path. A unit test verifies the token language leaks no ground-truth label.

## Directory Layout

```text
nnl_vliw/
  NNL/ архитектуры/ обучение/ СТАНДАРТ_БЛОКА.md   unmodified copy of NNL core
  язык.py           graph -> tokens and concepts
  ядра.py           two cores: domains, dimensions, answers
  данные.py         labels and tokens -> training rows
  обучить.py        training
  оценка.py         loading via Motherboard, composition, policies
  база_sklearn.py   control baseline: standard classifiers
  блоки/А, блоки/Б  trained blocks: passport + weights
  блоки_помощь/     block for the setup assistant screen
  результаты/       evaluation across 3 seeds and sklearn baseline
tools/portfolio_labels.py   portfolio group labels
tools/gen_graphs.py         raw graphs
tests/test_nnl_vliw.py      tests
```

## Data

Groups ordered from cheap to expensive: `greedy`, `prio`, `defer`, `hold`, `rule`, `beam`.
For each graph, the best makespan of every group is computed. The label is the cheapest group achieving the full portfolio's best makespan.

Training: 64,100 graphs, 2,502 of which are hard. The training pool includes all hard graphs plus an equal number of greedy-optimal graphs.
Evaluation: `eval_hard` (300, 267 hard), `eval_wide` (300, greedy suffices everywhere), `eval_real` (947 real blocks, 43 hard). The cores were never trained on real code.

## Results

Excess cycles relative to the full portfolio (lower is better):

| `eval_hard`, 267 of 300 hard | excess cycles |
|---|---:|
| always greedy | 275 |
| Core A | 97 / 89 / 122 |
| Core B | 148 / 118 / 120 |
| logistic regression / boosting / random forest | 130 / 132 / 176 |
| cross-check A & B | 66 / 62 / 70 |
| random abstention at same rates | 55 / 57 / 79 |

| `eval_real`, 43 of 947 hard | excess cycles |
|---|---:|
| always greedy | 47 |
| rule "has DIV -> full portfolio" | 41 |
| Core A | 41 / 39 / 38 |
| Core B | 45 / 44 / 46 |
| cross-check A & B | 33 / 34 / 33 |
| random abstention | 31 / 28 / 25 |

Macro accuracy on dev across six groups (random = 0.17): Core A ~0.375, Core B ~0.34, logistic regression 0.390. On `eval_wide`, all methods tie greedy.

## Conclusions

- **The NNL machinery works.** Motherboard verifies SHA-256, rejects tampered weights, and blocks pass the linter.
- **Quality matches standard classifiers.** There is no quality-based case for adding NNL here.
- **Group selection from these features is weak:** ~0.37 across six groups.
- **Negligible effect on real code:** greedy misses optimal on only 43 of 947 graphs, and the cores recover less than a fifth of those lost cycles.
- **Cross-core verification does not signal errors:** when cores agree, Core A is right 62% of the time; when they disagree, 77%. In excess cycles, cross-checking loses to random abstention in 5 of 6 cases.

## Limitations

- Portfolio groups partially overlap; the "cheapest" label depends on group ordering.
- Only three seeds, one real-block dataset, 43 hard graphs.
- Cycles are model-based, not hardware; `loop_mode` is not modeled.
- Core inference latency was not benchmarked — only selection quality.
- Training labels are excluded from the repository (tens of MB).

## Reproducing

```bash
python3 tools/portfolio_labels.py eval_hard.jsonl eval_wide.jsonl eval_real.jsonl --out labels/
python3 tools/portfolio_labels.py train_hard.jsonl train_merged.jsonl --unique --out labels/ \
    --exclude eval_hard.jsonl,eval_hard_dev.jsonl,eval_wide.jsonl,eval_real.jsonl
python3 tools/gen_graphs.py --n 24000 --out labels/train_gen.jsonl
python3 tools/portfolio_labels.py labels/train_gen.jsonl --out labels/
python3 -m nnl_vliw.обучить --метки labels/ --выход /tmp/блоки --зерно 1
python3 -m nnl_vliw.оценка  --метки labels/ --блоки /tmp/блоки --json /tmp/оценка.json
python3 -m nnl_vliw.база_sklearn --метки labels/      # requires scikit-learn
python3 -m unittest tests.test_nnl_vliw
```

## Help Block

`nnl_vliw/блоки_помощь/Помощь_ассистент` handles questions about installing and using NEX CLI: 548 questions, 13 topics + chat + off-topic, dev accuracy 0.655. Inference runs via `vliw/help_nnl.py` in pure Python using the weight copy at `vliw/help_weights.json`. Retrain with `python tools/train_help_block.py`.

## Next Steps

Features and problem formulation need to change, not the architecture: bag-of-tokens group selection hits a ~0.4 ceiling. Promising directions include per-instruction TINY AI features, a different target ("is the lower bound already reached?"), and more real hard examples.
