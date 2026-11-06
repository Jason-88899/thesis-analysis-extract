# thesis-analysis-extract

**帮助 AI 读论文，整理主要内容、创新点、机理和实验步骤。**

支持 PDF 和 Word，可先看目录、再找关键词、最后读需要的页面，减少无关内容。

## 怎么用

将这个目录安装到支持 `SKILL.md` 的 AI 助手中，然后说：

> 帮我读这篇论文，总结主要内容和机理，并列出实验步骤、药品及用量。

具体安装方式取决于你使用的客户端。下载仓库不会自动安装。

也可以使用 Python 3.8 或以上版本直接运行，无需安装额外的 Python 库：

```bash
python scripts/extract_text.py "论文.pdf" --outline
python scripts/extract_text.py "论文.pdf" --grep "实验|Experimental|Methods" -A 20
python scripts/extract_text.py "论文.pdf" --pages 3-5
```

## 使用前了解

- 支持部分文字型 PDF、Word（`.docx` 等）和常见文本文件。
- 扫描件需要另外识别文字；不支持加密文件和旧版 `.doc`。
- 公式、表格和复杂排版可能提取不准，重要数据请核对原文。
- 脚本在本地读取文件，不联网、不上传；把结果交给云端 AI 后，内容会进入相应服务。

详细阅读方法见 [SKILL.md](SKILL.md)，遇到问题查看 [排障说明](references/troubleshooting.md)。

## 测试与许可

```bash
python -m unittest discover -s tests -v
```

使用 [MIT 许可证](LICENSE)。仓库不包含真实论文或个人文档。
