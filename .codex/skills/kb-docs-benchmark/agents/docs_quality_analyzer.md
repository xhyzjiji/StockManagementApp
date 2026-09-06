# Docs Quality Analyzer Agent

Analyze a completed `kb-docs-benchmark` workspace and produce actionable documentation improvement suggestions.

## Inputs

The orchestrating agent provides:

- `benchmark_json_path`: path to `<workspace>/benchmark.json`
- `evals_json_path`: path to `<doc-root>/docs/evals/evals.json`
- `workspace_path`: benchmark workspace containing per-question runs
- `doc_root`: module root containing `CLAUDE.md` and `docs/`
- `doc_paths`: docs bundle paths
- `output_json_path`: `<workspace>/docs_quality_suggestions.json`
- `output_markdown_path`: `<workspace>/docs_quality_suggestions.md`

## Rules

- Do not rerun the benchmark.
- Do not call model subprocesses.
- You may inspect the same repository/code scope used by the answer workers.
- You may read the docs bundle.
- Base suggestions on concrete benchmark evidence: pass/fail deltas, answer differences, assertions, timing/token deltas, and code/docs conflicts.
- Do not optimize for making the benchmark easier. Suggest docs improvements or eval fixes only when evidence supports them.
- **Write all prose fields in Chinese** (`summary`, `overall_recommendation`, `problem`, `evidence`, `recommendation`, `expected_impact`). Preserve category IDs, priorities, code symbols, file paths, class names, method names, protocols, and assertion IDs **verbatim** — translate the explanation, never the identifier.
  These suggestions are not an archive entry; they are read on a result card by the people who own the docs, and that audience reads Chinese. English prose there costs a translation step at exactly the moment someone is deciding whether to act.

## Categories

Which set applies depends on which configurations ran.

**Docs-vs-no-docs run** (`with_docs` + `without_docs` present) — the question is "are these docs worth anything":

- `coverage_gap`: `with_docs` still fails because the docs do not cover the behavior.
- `redundant_docs`: `without_docs` already passes consistently, so docs add little signal for this question.
- `misleading_docs`: `with_docs` performs worse than `without_docs`, suggesting stale or confusing docs.
- `navigation_gap`: `with_docs` is correct but materially slower or more token-heavy, suggesting poor docs navigation.

**Compare run** (`with_docs` + `with_docs_compare`, no `without_docs`) — the question is "did this docs change help". `with_docs` is the current docs, `with_docs_compare` is the `--compare-docs-ref` version. Judge every suggestion against that axis; never fall back to the docs-vs-no-docs categories, and never assert anything about a `without_docs` baseline that did not run:

- `regression`: `with_docs_compare` passes and `with_docs` fails — the change lost information the previous version carried. Name the removed or altered content.
- `improvement`: `with_docs` passes and `with_docs_compare` fails — the change fixed a real gap. Worth recording so it is not undone later.
- `unchanged_gap`: both versions fail — the change neither helped nor hurt here; the gap predates it. Do not attribute it to the change.
- `navigation_regression`: both versions pass but the current one is materially slower or more token-heavy — the change hurt navigability without hurting correctness. (Distinct from the docs-vs-no-docs `navigation_gap`, which compares against having no docs at all; reusing one id for two different baselines makes the suggestions unreadable in aggregate.)

**Either shape**:

- `stale_or_inconsistent`: docs conflict with code evidence.
- `eval_issue`: the eval assertion is low quality or measures the wrong thing.

In a compare run, evidence must cite **both** versions for the question at hand (what each answered, which assertion split them). A suggestion that only inspects one side cannot support a `regression` or `improvement` claim.

## Output JSON

Write exactly this shape:

```json
{
  "summary": "Short explanation of current docs quality.",
  "overall_recommendation": "先补 workflow.md 里的 adapter 交接（q1 就栽在这），再顺手删掉过期的重试段；两处都在同一个文件，一次改完即可。",
  "suggestions": [
    {
      "priority": "high",
      "category": "coverage_gap",
      "question_id": "q1",
      "doc_paths": ["docs/workflow.md"],
      "problem": "The docs do not describe the adapter handoff.",
      "evidence": "with_docs failed assertion mentions_manager_adapter.",
      "recommendation": "Add the manager adapter handoff and owning class to docs/workflow.md.",
      "expected_impact": "Should improve q1 with_docs correctness."
    }
  ]
}
```

Allowed priorities: `high`, `medium`, `low`.

### `overall_recommendation` — 把这一轮的全部建议合成**一段话**

`suggestions` 是清单，`overall_recommendation` 是**推荐**。两者服务的不是同一件事：
清单给的是排查坐标（命中哪道题、动哪个文件），推荐回答的是「我现在该做什么」。

结果卡上显示的是这一段，不是清单。**这一段必须自己成立**——读的人不看清单也知道
先做什么、后做什么、为什么。

写法要求：

- **一段连贯的话，不是把 N 条建议用连接词串起来。** 后端拼得出后者，之所以要你来写，
  就是因为它需要判断：哪几条其实是同一处改动、哪条先做能顺带解决另一条、哪条可以缓。
  串接出来的模板腔一眼能看出来，那等于这个字段白加。
- **给顺序和理由**，不要平铺。「先 A，因为 B 依赖它」比「A、B 都要做」有用得多。
- **落到动作上**，别停在「文档质量有待提升」这种话上。
- 只有一条建议时也照写——那时它就是一句「只需要做这一件事：……」，仍然比一条
  裸的 `recommendation` 更像给人的交代。
- 一条建议都没有（文档没问题）时 **omit 这个字段**，不要写「没什么要改的」。
  空着由后端处理，写一句废话会占掉卡上最显眼的位置。
- 长度以在卡片上三五行读完为准。它是推荐，不是报告。

## Output Markdown

Write a concise human-readable report:

```markdown
# Docs Quality Suggestions

Summary paragraph.

## High Priority

- `[coverage_gap] q1`: recommendation...
```

The orchestrating agent should present these suggestions to the user and ask whether to optimize the docs based on the report. Do not apply documentation changes automatically as part of analysis.
