"""V4.0.4 文档生成引擎测试"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))

from services.document_generator import (
    DocumentGenerator, ExportOptions,
    parse_markdown_sections, AnalysisSection
)

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")

print("=" * 50)
print("V4.0.4 文档生成引擎测试")
print("=" * 50)

tmp = tempfile.gettempdir()
gen = DocumentGenerator()

SAMPLE_AI_TEXT = """# 球阀产品分析报告

## 文档概要

本报告对球阀产品进行深度分析。球阀是工业管道中广泛使用的截断阀。

## 核心数据

| 型号 | 压力 | 价格 |
|------|------|------|
| Q41F | PN16 | 1500元 |
| Q347F | PN25 | 3500元 |

## 深度解读

球阀具有以下优势：
- 密封性好
- 开关灵活
- 适用范围广

## 建议

建议采购部门优先考虑PN16系列，满足常规工况需求。

"""

sections = parse_markdown_sections(SAMPLE_AI_TEXT)
print(f"\n[1] Markdown 解析")
check("解析出 sections (>=4)", len(sections) >= 4, f"实际{len(sections)}")
check("sections 含文档概要", any("概要" in s.title for s in sections), f"{[s.title for s in sections]}")
print(f"  解析结果: {[s.title for s in sections]}")

# Word 测试
print(f"\n[2] Word 导出")
docx_path = os.path.join(tmp, "_v404_test.docx")
try:
    opts = ExportOptions(format="docx", output_path=docx_path,
                         title="球阀分析报告", author="AI知识库4.0")
    result = gen.generate(SAMPLE_AI_TEXT, opts)
    check("Word 文件生成成功", os.path.exists(result))
    size = os.path.getsize(result)
    check(f"Word 文件大小合理 ({size} bytes)", size > 1000)
    os.remove(docx_path)
except Exception as e:
    check("Word 导出异常", False, str(e))

# PDF 测试
print(f"\n[3] PDF 导出")
pdf_path = os.path.join(tmp, "_v404_test.pdf")
try:
    opts = ExportOptions(format="pdf", output_path=pdf_path,
                         title="球阀分析报告", author="AI知识库4.0")
    result = gen.generate(SAMPLE_AI_TEXT, opts)
    check("PDF 文件生成成功", os.path.exists(result))
    size = os.path.getsize(result)
    check(f"PDF 文件大小合理 ({size} bytes)", size > 500)
    os.remove(pdf_path)
except Exception as e:
    check("PDF 导出异常", False, str(e))

# PPT 测试
print(f"\n[4] PPT 导出")
pptx_path = os.path.join(tmp, "_v404_test.pptx")
try:
    opts = ExportOptions(format="pptx", output_path=pptx_path,
                         title="球阀分析报告", author="AI知识库4.0")
    result = gen.generate(SAMPLE_AI_TEXT, opts)
    check("PPTX 文件生成成功", os.path.exists(result))
    size = os.path.getsize(result)
    check(f"PPTX 文件大小合理 ({size} bytes)", size > 1000)
    os.remove(pptx_path)
except Exception as e:
    check("PPT 导出异常", False, str(e))

# Excel 测试
print(f"\n[5] Excel 导出")
xlsx_path = os.path.join(tmp, "_v404_test.xlsx")
try:
    opts = ExportOptions(format="xlsx", output_path=xlsx_path,
                         title="球阀分析报告", author="AI知识库4.0")
    result = gen.generate(SAMPLE_AI_TEXT, opts)
    check("Excel 文件生成成功", os.path.exists(result))
    size = os.path.getsize(result)
    check(f"Excel 文件大小合理 ({size} bytes)", size > 500)
    os.remove(xlsx_path)
except Exception as e:
    check("Excel 导出异常", False, str(e))

# 不支持格式测试
print(f"\n[6] 错误处理")
try:
    opts = ExportOptions(format="html", output_path=os.path.join(tmp, "_test.html"),
                         title="测试")
    gen.generate("test", opts)
    check("不支持格式抛出异常", False)
except ValueError as e:
    check("不支持格式抛出 ValueError", "不支持" in str(e))
except Exception:
    check("不支持格式抛出异常", False)

print("\n" + "=" * 50)
total = PASS + FAIL
print(f"测试结果: {PASS}/{total} 通过, {FAIL} 失败")
if FAIL == 0:
    print("🎉 V4.0.4 文档生成引擎全部通过!")
else:
    print(f"❌ 有 {FAIL} 项失败")
print("=" * 50)