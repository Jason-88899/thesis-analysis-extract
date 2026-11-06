# v1.1.0 token 验证 / Token validation

## 范围 / Scope

基线为 v1.0.0 代码所在的提交 `407cb39c98dd295641e1aef47c1b36bb9a382c85`。样本由测试代码生成，包含 12 页英文 PDF、含中文/表格的 Word 和普通文本；不含真实论文或个人文档。

The baseline is commit `407cb39c98dd295641e1aef47c1b36bb9a382c85`, containing v1.0.0. Tests generate a 12-page English PDF, a Word document with Chinese text and a table, and plain text. No actual papers or personal documents are used.

计数使用独立安装的 `tiktoken` 和 `o200k_base`，仅用于开发验证；提取脚本仍然无需第三方依赖。计数为文本的实际分词数，不包括客户端包装、工具调用、模型推理或按需加载的参考文件。

Counts use a separately installed `tiktoken` with `o200k_base` for development validation only. The extractor still has no third-party dependencies. Counts measure text tokens, excluding client wrappers, tool calls, model reasoning, and references loaded on demand.

## 结果 / Results

`SKILL.md`：810 → 562 tokens，减少 **30.62%**。

`SKILL.md`: 810 → 562 tokens, a **30.62%** reduction.

| 合成场景 / Synthetic scenario | 旧版合计 / Before | `--lean` 合计 / After | 减少 / Reduction |
|---|---:|---:|---:|
| PDF 全文 / Full PDF | 753 | 695 | 7.70% |
| PDF 大纲 / Outline | 121 | 107 | 11.57% |
| PDF 搜索 / Search | 534 | 479 | 10.30% |
| PDF 指定页 / Selected pages | 203 | 173 | 14.78% |
| PDF 压缩 / Compact | 152 | 95 | 37.50% |
| PDF 去参考 / Drop references | 753 | 695 | 7.70% |
| PDF 无页码标记 / No page markers | 680 | 659 | 3.09% |
| Word 全文 / Full Word | 107 | 86 | 19.63% |
| Word 大纲 / Outline | 24 | 15 | 37.50% |
| Word 搜索 / Search | 52 | 38 | 26.92% |
| Word 纯标题 / Plain headings | 102 | 81 | 20.59% |
| Word 去参考 / Drop references | 92 | 70 | 23.91% |
| 文本全文 / Full text | 47 | 33 | 29.79% |
| 文本搜索 / Text search | 44 | 31 | 29.55% |

合计 = 分别计算 stdout 与 stderr 后相加。只有接收两者的 AI 工作流才适用该口径；如果客户端只传 stdout，收益更小。Word 全文的 stdout 为 85 → 86 tokens，Word 纯标题为 80 → 81，说明减少空白不保证降低任意分词器的 token 数。不要将这些比例当作真实论文或所有模型的保证。

Combined totals add stdout and stderr token counts separately. This applies when an AI workflow receives both streams; stdout-only savings are smaller. Full Word stdout changes from 85 to 86 tokens, and plain-heading Word from 80 to 81. Removing whitespace does not guarantee fewer tokens for every tokenizer. These percentages are not guarantees for real papers or all models.

17 组旧命令的退出码、stdout、stderr 与基线完全一致（不比较版本号和帮助文本）。14 组 `--lean` 输出在统一页标记、删除空行和行末空白后逐行一致，验证了非空行、顺序、缩进、数值及单位保持不变。新模式不增加丢弃正文的规则；原有 `--compact`、`--drop-refs` 和截断选项仍有各自的删减行为。

For 17 legacy command cases, exit codes, stdout, and stderr match the baseline exactly (version and help text excluded). In 14 lean cases, lines match after normalizing page markers, blank lines, and trailing whitespace, preserving nonblank lines, order, indentation, values, and units. Lean mode adds no body-content deletion rules; existing compacting, reference removal, and truncation options retain their own deletion behavior.

## 复现 / Reproduce

```bash
python -m unittest discover -s tests -v
python tests/benchmark_tokens.py --tokenizer estimate
# 可选：在独立开发环境安装 tiktoken，使用精确计数。
# Optional: install tiktoken in a separate development environment for exact counts.
python tests/benchmark_tokens.py --tokenizer o200k_base
```

精确计数需预先安装 `tiktoken` 并缓存对应编码；首次下载编码可能联网。基准脚本需要 Git 及完整基线提交，源码压缩包没有 Git 历史时，应在完整克隆中复现。日常提取不需要这些开发工具。

Exact counting requires a separately installed `tiktoken` and its encoding cache; the first encoding download may use the network. The benchmark requires Git and the baseline commit. Reproduce it in a full clone when a source archive lacks Git history. Normal extraction needs none of these development tools.
