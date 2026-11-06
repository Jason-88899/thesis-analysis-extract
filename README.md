# thesis-analysis-extract

**[下载最新版 / Download latest](https://github.com/Jason-88899/thesis-analysis-extract/releases/latest)**

请在发布页下载 `thesis-analysis-extract-v*.zip` 安装包。首页代码保留原版，新版请使用此入口。

Download the `thesis-analysis-extract-v*.zip` package from the release page. The code on this page keeps the original version; use this link for the latest version.

**帮助 AI 读论文，整理主要内容、创新点、机理和实验步骤。**

**Help AI read papers and summarize their main findings, innovations, mechanisms, and experimental steps.**

支持 PDF 和 Word，可先看目录、再找关键词、最后读需要的页面，减少无关内容。

Supports PDF and Word. Check the outline, search for keywords, then read the pages you need to avoid unnecessary text.

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
