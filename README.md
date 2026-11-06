# thesis-analysis-extract

面向科研论文与技术报告的本地文本提取 skill。使用纯 Python 标准库读取 PDF、Word 和常见文本文件，通过“大纲 → 关键词定位 → 目标页”按需提取内容，帮助 AI 助手整理研究内容、创新点、机理及实验流程（含药品与用量），减少无关全文占用上下文。

A Python standard-library skill for selective reading of local research papers and reports: outline → keyword context → target pages. Extract text first, then let an AI assistant produce evidence-grounded summaries and experimental procedures.

## 功能与适用场景

- **离线提取**：运行脚本无需 pip、Office、网络连接或 API 密钥。
- **按需阅读**：输出章节大纲、正则关键词上下文或指定 PDF 页，支持字符上限。
- **PDF**：支持部分文字型 PDF、FlateDecode 压缩流、对象流及部分单字节字体映射。
- **Word**：读取 OOXML 正文的段落、标题和表格；不执行宏或访问外部关系。
- **可追溯输出**：PDF 默认带物理页码，统计写入 stderr，文本写入 stdout。
- **科研整理**：skill 指导助手按原文概括机理、性能和实验步骤；脚本本身只提取文本。

适用于本地论文初读、实验方法定位、药品用量检索。关键数值、公式、图表和多栏排版须结合原文核对。实际上下文节省取决于文档、查询和模型分词方式，不承诺固定比例。

## 快速开始

需要 Python 3.8+。在仓库根目录执行，路径含空格时加引号。

```bash
python scripts/extract_text.py "paper.pdf" --outline
python scripts/extract_text.py "paper.pdf" --grep "Experimental|Materials|Methods" -A 20
python scripts/extract_text.py "paper.pdf" --pages 3-5 --max-chars 12000
python scripts/extract_text.py "report.docx" --grep "实验|制备|用量" -A 20
python scripts/extract_text.py "paper.pdf" --compact --drop-refs
```

大纲可能漏检标题；无法定位时用关键词搜索，再核对相关页。

## 作为 skill 使用

将本仓库目录放入支持 `SKILL.md` 的客户端技能目录，保留相对结构，再按客户端的安装方式加载。单独克隆仓库不会自动安装到 ChatGPT。

```text
thesis-analysis-extract/
├── SKILL.md
├── agents/openai.yaml
├── scripts/extract_text.py
└── references/
    ├── paper-reading-workflow.md
    └── troubleshooting.md
```

示例请求：“使用 thesis-analysis-extract 阅读这篇论文，总结主要内容、创新点和机理，并提取药品用量及制备流程。”助手应将脚本路径解析到实际安装的技能目录。

根目录还保留许可证、仓库说明、忽略规则、动态生成样本的测试及 GitHub Actions 配置，便于维护；无需上传论文或运行结果。

## 参数

| 参数 | 作用 |
|---|---|
| `path` | 本地输入文件 |
| `--outline` | PDF 启发式大纲；Word 标题层级 |
| `--grep PATTERN` | 正则搜索匹配行与上下文，默认忽略大小写 |
| `-A N` / `-B N` | 命中后/前上下文行数，默认 4 / 0 |
| `-c, --case-sensitive` | 区分大小写 |
| `-m N` | 最多采用 N 个命中，重叠上下文合并，默认 20 |
| `--pages 1-3,5` | PDF 页选择，从 1 开始；页号上限 100000 |
| `--compact` | 启发式去重复行、页码及合并断词，可能误删内容 |
| `--drop-refs` | 启发式截去参考文献，需核对截断位置 |
| `--max-chars N` | 输出字符上限，0 表示不限制；不限制解析开销 |
| `--no-page-marker` | 省略 PDF 页码标记 |
| `--plain` | Word 标题不加 Markdown 前缀 |
| `--stats` | PDF 非大纲模式逐页字符数与粗略 token 估算 |
| `--version` | 版本号 |

`--grep` 与 `--outline` 同时出现时以搜索为准。Word 的 `--pages` 会提示并忽略。

退出码：`0` 完成（搜索无命中也为 0）；`2` 输入、参数或解析错误；`3` PDF/Word 原始提取文字少于 50 字符。退出码 3 不等于确定是扫描件。

## 支持范围与限制

| 输入 | 支持情况 |
|---|---|
| `.pdf` | 部分文字型 PDF；不保证全部 PDF 兼容 |
| `.docx/.docm/.dotx/.dotm` | 正文段落、标题与表格；只读 XML，不执行宏 |
| `.txt/.md/.csv/.tsv/.json/.yaml` 等 | 按文本读取，不执行内容 |
| 二进制 `.doc` | 不支持，请先另存为 `.docx` |
| 扫描或加密文档 | 不提供 OCR 或密码解密 |

PDF 暂不完整支持继承/间接资源、Form XObject 正文、双字节 CID 字体、全部编码及过滤器；双栏顺序、图表、公式和上下标可能失真。Word 页眉页脚、脚注、批注、图表和复杂版式不在提取范围内。

输入限制为 64 MiB，单个 PDF 解压流及 Word 正文 XML 限制为 32 MiB；拒绝 Word XML 的 DTD/实体声明。这些限制不能代替操作系统隔离，不可信文件应在受限环境处理。

## 隐私

提取脚本没有网络请求、遥测、上传、命令执行或持久化输出功能，仅读取指定文件并打印结果。Python 导入或测试可能产生缓存/临时文件；测试文档由代码生成并清理。

**本地提取不代表整个 AI 工作流离线**：把 stdout 放入云端助手、终端日志或 CI 日志时，内容会进入相应服务或记录。处理未发表论文或保密数据时，先确认允许使用的环境。仓库不包含真实论文、用户文档、密钥、缓存或个人配置。

## 测试

```bash
python -m unittest discover -s tests -v
```

使用动态生成的 PDF/DOCX，覆盖提取、分页、搜索、压缩、参数校验与解析边界；合成样本通过不代表所有真实 PDF 兼容。可设置 `EXTRACT_TEST_TMPDIR` 指定临时目录。GitHub Actions 以只读仓库权限运行同一套测试。

## License

[MIT](LICENSE)

