# thesis-analysis-extract

**v1.1.1：修复部分 PDF 数学字符提取崩溃，完整保留多字符映射，延续精简阅读模式。**

**v1.1.1: Fix PDF math-character crashes and preserve multi-character mappings, with lean reading retained.**

**帮助 AI 读论文，整理主要内容、创新点、机理和实验步骤。**

**Help AI read papers and summarize their main findings, innovations, mechanisms, and experimental steps.**

支持 PDF 和 Word，可先看目录、再找关键词、最后读需要的页面，减少无关内容。

Supports PDF and Word. Check the outline, search for keywords, then read the pages you need to avoid unnecessary text.

**v1.1.0：更精简的指令和可选的 `--lean` 模式，减少空行与提示文字，保留正文和来源页码。旧版命令仍可使用。**

**v1.1.0: Shorter skill instructions and an optional `--lean` mode reduce blank lines and routine messages while keeping body text and source pages. Existing commands still work.**

节省效果和兼容性验证见 [测试报告](references/token-benchmark.md)。效果取决于文档及分词器，并非所有输出都会减少 token。

See the [validation report](references/token-benchmark.md) for measured savings and compatibility checks. Results depend on the document and tokenizer; not every output uses fewer tokens.

## 怎么用 / How to use

将这个目录安装到支持 `SKILL.md` 的 AI 助手中，然后说：

Install this folder as a skill in an AI assistant that supports `SKILL.md`, then ask:

> 帮我读这篇论文，总结主要内容和机理，并列出实验步骤、药品及用量。
>
> Read this paper, summarize its main findings and mechanisms, and list the experimental steps, chemicals, and amounts.

具体安装方式取决于你使用的客户端。下载仓库不会自动安装。

Installation depends on your client. Downloading the repository does not install the skill automatically.

也可以使用 Python 3.8 或以上版本直接运行，无需安装额外的 Python 库：

You can also run it directly with Python 3.8 or later, without installing additional Python packages:

```bash
python scripts/extract_text.py "paper.pdf" --outline
python scripts/extract_text.py "paper.pdf" --grep "实验|Experimental|Methods" -A 20
python scripts/extract_text.py "paper.pdf" --pages 3-5
```

想减少交给 AI 的文字，可以在这些命令后加 `--lean`。它会将页码标记简化为 `[p3]`，不自动删正文、参考文献或重要警告。处理普通文本时也会去掉空行；需要保留空白布局时，不加此参数。

Add `--lean` to these commands to reduce the text sent to AI. It shortens page markers to `[p3]` without automatically removing body text, references, or important warnings. It also removes blank lines in plain text; omit it when whitespace layout matters.

## 使用前了解 / Before you start

- 支持部分文字型 PDF、Word（`.docx` 等）和常见文本文件。
  Supports some text-based PDFs, Word files (such as `.docx`), and common text files.
- 扫描件需要另外识别文字；不支持加密文件和旧版 `.doc`。
  Scanned documents need a separate text recognition tool. Encrypted files and legacy `.doc` files are not supported.
- 公式、表格和复杂排版可能提取不准，重要数据请核对原文。
  Equations, tables, and complex layouts may not be extracted accurately. Check important data against the original.
- 脚本在本地读取文件，不联网、不上传；把结果交给云端 AI 后，内容会进入相应服务。
  The script reads files locally without internet access or uploads. If you send the results to a cloud AI, the content goes to that service.

详细阅读方法见 [SKILL.md](SKILL.md)，遇到问题查看 [排障说明](references/troubleshooting.md)。

See [SKILL.md](SKILL.md) for the reading workflow and [Troubleshooting](references/troubleshooting.md) for help.

## 测试与许可 / Tests and license

```bash
python -m unittest discover -s tests -v
```

使用 [MIT 许可证](LICENSE)。仓库不包含真实论文或个人文档。

Licensed under [MIT](LICENSE). The repository contains no actual papers or personal documents.
