"""统一文档生成引擎 — 将 AI 分析结果导出为 Word/PDF/PPT/Excel"""
import os
import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ExportOptions:
    format: str
    output_path: str
    title: str = "AI分析报告"
    author: str = "AI知识库4.0"


@dataclass
class AnalysisSection:
    title: str
    content: str
    level: int = 1


def parse_markdown_sections(md_text: str) -> list[AnalysisSection]:
    """将 AI 输出的 Markdown 文本解析为结构化的 Section 列表"""
    sections = []
    current = AnalysisSection(title="", content="", level=1)
    buf = []

    def _flush():
        nonlocal current, buf
        if current.title or buf:
            current.content = "\n".join(buf).strip()
            sections.append(current)
        current = AnalysisSection(title="", content="", level=1)
        buf = []

    for line in md_text.split("\n"):
        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            _flush()
            current = AnalysisSection(
                title=m.group(2).strip(),
                content="",
                level=len(m.group(1)),
            )
        else:
            buf.append(line)

    _flush()
    return sections


class DocumentGenerator:
    """统一文档生成引擎"""

    def generate(self, analysis_text: str, options: ExportOptions) -> str:
        sections = parse_markdown_sections(analysis_text)
        exporters = {
            "docx": self._export_docx,
            "pdf": self._export_pdf,
            "pptx": self._export_pptx,
            "xlsx": self._export_xlsx,
        }
        exporter = exporters.get(options.format)
        if not exporter:
            raise ValueError(f"不支持的导出格式: {options.format}")
        return exporter(sections, options)

    # ── Word 导出 ──────────────────────────────────────

    def _export_docx(self, sections: list[AnalysisSection],
                      options: ExportOptions) -> str:
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor

        doc = Document()

        # 封面
        title_para = doc.add_heading(options.title, level=0)
        p = doc.add_paragraph()
        p.add_run(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}").font.size = Pt(12)
        p2 = doc.add_paragraph()
        p2.add_run(f"生成工具：{options.author}").font.size = Pt(12)
        p3 = doc.add_paragraph()
        p3.add_run(f"分析内容：{options.title}").font.size = Pt(12)
        doc.add_paragraph()

        # 目录（自动提取 section 标题）
        if any(s.title for s in sections):
            doc.add_heading("目录", level=1)
            for s in sections:
                if s.title:
                    prefix = "  " * (s.level - 1)
                    doc.add_paragraph(f"{prefix}• {s.title}", style="List Bullet")
            doc.add_paragraph()

        # 正文
        for section in sections:
            if not section.title and not section.content:
                continue
            if section.title:
                level = min(section.level, 3)
                doc.add_heading(section.title, level=level)
            if section.content:
                for para_text in section.content.strip().split("\n"):
                    t = para_text.strip()
                    if not t:
                        continue
                    doc.add_paragraph(t)

        doc.save(options.output_path)
        return options.output_path

    # ── PDF 导出 ────────────────────────────────────────

    def _export_pdf(self, sections: list[AnalysisSection],
                    options: ExportOptions) -> str:
        from fpdf import FPDF

        class PDFReport(FPDF):
            def header(self):
                fn = "cjk" if getattr(self, "font_ok", False) else "helvetica"
                self.set_font(fn, size=8)
                self.cell(0, 5, options.author, align="R")
                self.ln(5)

            def footer(self):
                self.set_y(-15)
                fn = "cjk" if getattr(self, "font_ok", False) else "helvetica"
                self.set_font(fn, size=8)
                self.cell(0, 10, f"Page {self.page_no()}", align="C")

        pdf = PDFReport()
        pdf.set_auto_page_break(auto=True, margin=15)

        # 加载中文字体 — fpdf2 v2.5.1+ 自动检测 Unicode 字体
        font_paths = [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\SIMHEI.TTF",
        ]
        cjk_font = next((fp for fp in font_paths if os.path.exists(fp)), None)

        font_ok = False
        if cjk_font:
            try:
                # fpdf2 v2.5.1+: 传入 fname 即可，自动检测 Unicode
                pdf.add_font("CJK", style="", fname=cjk_font)
                if "cjk" in pdf.fonts:
                    font_ok = True
            except Exception:
                font_ok = False

        # 将 font_ok 存入实例，让 header/footer 方法可以访问
        pdf.font_ok = font_ok

        def _f(size: int) -> None:
            # fpdf2 注册的字体 key 为小写 "cjk"
            pdf.set_font("helvetica" if not font_ok else "cjk", size=size)

        pdf.add_page()
        _f(18)
        try:
            if font_ok:
                pdf.cell(0, 15, options.title, align="C")
            else:
                pdf.set_font("helvetica", size=18)
                pdf.cell(0, 15, "AI Analysis Report", align="C")
        except Exception:
            pdf.set_font("helvetica", size=18)
            pdf.cell(0, 15, "AI Analysis Report", align="C")
        pdf.ln(20)
        _f(10)
        if font_ok:
            pdf.cell(0, 8, f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            pdf.ln(6)
            pdf.cell(0, 8, f"Tool: {options.author}")
        else:
            pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d')}")
        pdf.ln(12)

        for section in sections:
            if not section.title and not section.content:
                continue
            if pdf.get_y() > 250:
                pdf.add_page()
            if section.title:
                _f(14)
                pdf.ln(4)
                title_text = f"[{section.title}]"
                pdf.multi_cell(0, 8, title_text)
                pdf.ln(2)
            if section.content:
                _f(10)
                content_lines = section.content.strip().split("\n")
                for line in content_lines:
                    t = line.strip()
                    if not t:
                        continue
                    # 跳过纯ASCII表格分隔线（如 |------|------|），
                    # CJK字体中 ASCII 标点符号可能有映射问题
                    if t.startswith("|") and all(c in "|- " for c in t):
                        continue
                    # 表格行：移除所有 | 符号，避免 CJK 字体对 ASCII 标点的映射异常
                    if "|" in t:
                        t = "".join(c for c in t if c != "|").strip()
                    if pdf.get_y() > 270:
                        pdf.add_page()
                    pdf.multi_cell(0, 6, t)
                    # multi_cell 不改变 x 位置，需要手动换行到下一行开头
                    pdf.ln()

        pdf.output(options.output_path)
        return options.output_path

    # ── PPT 导出 ────────────────────────────────────────

    def _export_pptx(self, sections: list[AnalysisSection],
                     options: ExportOptions) -> str:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN

        prs = Presentation()
        blank_layout = prs.slide_layouts[6]

        # 封面幻灯片
        slide = prs.slides.add_slide(blank_layout)
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(9), Inches(1.5))
        tf = title_box.text_frame
        tf.text = options.title
        tf.paragraphs[0].font.size = Pt(32)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

        sub_box = slide.shapes.add_textbox(Inches(0.5), Inches(3.0), Inches(9), Inches(1))
        stf = sub_box.text_frame
        stf.text = f"AI知识库4.0 · {datetime.now().strftime('%Y-%m-%d')}"
        stf.paragraphs[0].font.size = Pt(18)
        stf.paragraphs[0].alignment = PP_ALIGN.CENTER

        # 内容幻灯片
        for section in sections:
            if not section.title and not section.content:
                continue
            slide = prs.slides.add_slide(blank_layout)

            # 标题
            if section.title:
                title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(0.8))
                ttf = title_box.text_frame
                ttf.text = section.title
                ttf.paragraphs[0].font.size = Pt(24)
                ttf.paragraphs[0].font.bold = True

            # 内容
            if section.content:
                content_box = slide.shapes.add_textbox(
                    Inches(0.5), Inches(1.5), Inches(9), Inches(5)
                )
                ctf = content_box.text_frame
                ctf.word_wrap = True
                ctf.text = section.content[:800]
                for para in ctf.paragraphs:
                    para.font.size = Pt(14)

        prs.save(options.output_path)
        return options.output_path

    # ── Excel 导出 ─────────────────────────────────────

    def _export_xlsx(self, sections: list[AnalysisSection],
                     options: ExportOptions) -> str:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment

        wb = Workbook()

        # Sheet1: 分析摘要
        ws = wb.active
        ws.title = "分析摘要"
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 60

        ws["A1"] = options.title
        ws["A1"].font = Font(size=14, bold=True)
        ws["A2"] = f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ws["A2"].font = Font(size=10)
        ws["A3"] = f"生成工具：{options.author}"
        ws["A3"].font = Font(size=10)

        row = 5
        ws.cell(row=row, column=1, value="章节").font = Font(bold=True)
        ws.cell(row=row, column=2, value="内容").font = Font(bold=True)
        row += 1

        for section in sections:
            ws.cell(row=row, column=1, value=section.title or "(无标题)")
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.cell(row=row, column=2, value=section.content[:500] if section.content else "")
            ws.cell(row=row, column=2).alignment = Alignment(wrap_text=True)
            row += 1

        # Sheet2: 纯文本（用于复制粘贴）
        ws2 = wb.create_sheet("纯文本")
        ws2.column_dimensions["A"].width = 100
        ws2["A1"] = options.title
        ws2["A1"].font = Font(size=14, bold=True)
        all_text = "\n".join(
            (f"【{s.title}】\n{s.content}" if s.title else s.content)
            for s in sections
        )
        ws2["A2"] = all_text
        ws2["A2"].alignment = Alignment(wrap_text=True)

        wb.save(options.output_path)
        return options.output_path
