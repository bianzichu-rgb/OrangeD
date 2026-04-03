"""
orangeD — Semantic document structure classifier.

Classifies document sections into 13 categories with multilingual keyword
matching (CN/EN/JP). Zero external dependencies beyond stdlib.

Domains: appliance manuals (original 9), academic papers, teaching materials.

Ported from CognoLiving 2.0 (schema_mapper, hams_visual_assembler).
"""

import re
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict

# ─── Section Categories (13-Category Taxonomy) ───────────────────────────────
# Original 9: appliance manuals.  +4: academic papers & teaching materials.

CATEGORIES = {
    "SAFETY": {
        "keywords_zh": ["安全", "警告", "注意", "危险", "重要安全", "安全信息", "安全注意事项",
                        "使用注意", "安全须知", "警示", "防止", "小心"],
        "keywords_en": ["safety", "warning", "caution", "danger", "hazard",
                        "important safety", "precautions", "risk", "do not"],
        "keywords_ja": ["安全", "警告", "注意", "危険"],
    },
    "TECHNICAL_SPEC": {
        "keywords_zh": ["规格", "参数", "技术数据", "技术规格", "产品规格", "性能参数",
                        "额定", "功率", "尺寸", "重量", "容量"],
        "keywords_en": ["specifications", "technical data", "dimensions", "capacity",
                        "ratings", "specs", "performance", "power supply",
                        "declaration of conformity"],
        "keywords_ja": ["仕様", "技術データ", "寸法"],
    },
    "INSTALLATION": {
        "keywords_zh": ["安装", "组装", "准备工作", "拆箱", "安装步骤", "安装前",
                        "连接管路", "固定", "水平调整"],
        "keywords_en": ["installation", "assembly", "getting started", "setup",
                        "mounting", "unpacking", "leveling", "plumbing", "wiring"],
        "keywords_ja": ["設置", "組み立て", "据付"],
    },
    "OPERATION": {
        "keywords_zh": ["操作", "使用方法", "功能介绍", "使用", "控制", "按钮",
                        "设置", "自定义", "程序", "模式", "开关", "日常使用",
                        "使用说明", "功能", "调节", "控制面板", "程序表", "洗涤程序"],
        "keywords_en": ["operation", "how to use", "using", "controls", "daily use",
                        "instructions", "cycles", "programs", "options", "buttons", "panel"],
        "keywords_ja": ["操作", "使い方", "使用方法"],
    },
    "PARTS": {
        "keywords_zh": ["零部件", "清单", "包装内容", "配件", "部件名称", "各部分名称"],
        "keywords_en": ["parts list", "components", "accessories", "packing list",
                        "what's in the box", "items included", "spare parts"],
        "keywords_ja": ["部品", "付属品", "同梱品"],
    },
    "MAINTENANCE": {
        "keywords_zh": ["保养", "维护", "清洁", "清洗", "养护", "除垢", "更换滤网",
                        "定期", "滤芯", "日常维护"],
        "keywords_en": ["maintenance", "cleaning", "care", "looking after",
                        "servicing", "storage", "descale", "filter"],
        "keywords_ja": ["お手入れ", "清掃", "メンテナンス"],
    },
    "TROUBLESHOOTING": {
        "keywords_zh": ["故障", "排查", "解决", "错误代码", "问题", "异常",
                        "报错", "维修", "检修", "闪烁"],
        "keywords_en": ["troubleshooting", "error codes", "problems", "fault",
                        "fix", "repair", "service info", "diagnosis"],
        "keywords_ja": ["故障", "トラブル", "エラー"],
    },
    "FAQ": {
        "keywords_zh": ["常见问题", "问答", "保修", "售后", "质保", "法律声明",
                        "免责", "版权", "合规"],
        "keywords_en": ["faq", "frequently asked questions", "warranty",
                        "copyright", "legal", "fcc", "regulatory"],
        "keywords_ja": ["よくある質問", "保証"],
    },
    "RECIPE": {
        "keywords_zh": ["食谱", "烹饪", "程序", "场景", "应用", "建议", "推荐"],
        "keywords_en": ["recipe", "cooking", "baking", "use case", "tips",
                        "recommended", "applications"],
        "keywords_ja": ["レシピ", "調理"],
    },
    # ─── Academic Paper Categories ───────────────────────────────────────────
    "ABSTRACT": {
        "keywords_zh": ["摘要", "概述", "综述", "引言", "导论", "前言", "背景",
                        "研究背景", "文献综述", "研究目的"],
        "keywords_en": ["abstract", "introduction", "overview", "background",
                        "literature review", "related work", "motivation",
                        "research objective", "purpose", "preamble"],
        "keywords_ja": ["要旨", "概要", "序論", "はじめに", "背景"],
    },
    "METHODOLOGY": {
        "keywords_zh": ["方法", "方法论", "实验", "实验设计", "实验方法", "研究方法",
                        "材料与方法", "数据集", "评估方法", "模型", "算法",
                        "实验结果", "结果", "讨论", "结论", "分析", "总结",
                        "致谢", "参考文献", "附录"],
        "keywords_en": ["method", "methodology", "experiment", "experimental",
                        "materials and methods", "dataset", "evaluation",
                        "model", "algorithm", "approach", "framework",
                        "results", "discussion", "conclusion", "analysis",
                        "findings", "acknowledgment", "references", "appendix",
                        "bibliography", "future work"],
        "keywords_ja": ["方法", "実験", "手法", "結果", "考察", "結論",
                        "参考文献", "付録"],
    },
    "MATH_FORMULA": {
        "keywords_zh": ["公式", "定理", "引理", "证明", "推论", "命题", "定义",
                        "方程", "等式", "不等式", "函数", "微积分", "线性代数",
                        "概率", "统计", "数学模型", "解题", "计算"],
        "keywords_en": ["theorem", "lemma", "proof", "corollary", "proposition",
                        "definition", "equation", "formula", "calculus",
                        "linear algebra", "probability", "statistics",
                        "mathematical model", "derivation", "notation"],
        "keywords_ja": ["定理", "証明", "公式", "方程式", "定義"],
    },
    # ─── Teaching Material Categories ────────────────────────────────────────
    "TEACHING": {
        "keywords_zh": ["教案", "教学目标", "教学目的", "课程", "学习目标",
                        "教学内容", "教学过程", "教学设计", "课时", "教学重点",
                        "教学难点", "教学方法", "教学准备", "教学反思",
                        "练习", "作业", "习题", "考试", "测验", "课后",
                        "预习", "复习", "知识点", "大纲", "教学计划",
                        "学时", "学分", "课程目标", "教学活动"],
        "keywords_en": ["lesson plan", "learning objective", "curriculum",
                        "syllabus", "course outline", "teaching method",
                        "assessment", "exercise", "homework", "assignment",
                        "exam", "quiz", "grading", "rubric", "lecture",
                        "tutorial", "seminar", "workshop", "module",
                        "learning outcome", "prerequisite", "credit"],
        "keywords_ja": ["教案", "学習目標", "カリキュラム", "授業", "課題",
                        "演習", "試験", "シラバス"],
    },
}


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class Section:
    title: str
    category: str
    confidence: float
    start_line: int
    end_line: int
    content_preview: str = ""


@dataclass
class FigureRef:
    label: str
    page_hint: Optional[int]
    line_num: int


@dataclass
class AnalysisResult:
    sections: List[Section] = field(default_factory=list)
    figures: List[FigureRef] = field(default_factory=list)
    cross_refs: List[Dict] = field(default_factory=list)
    total_lines: int = 0

    def to_dict(self) -> Dict:
        return {
            "sections": [asdict(s) for s in self.sections],
            "figures": [asdict(f) for f in self.figures],
            "cross_refs": self.cross_refs,
            "total_lines": self.total_lines,
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, **kwargs)

    def filter_by(self, category: str) -> "AnalysisResult":
        fc = category.upper()
        filtered = [s for s in self.sections if fc in s.category.upper()]
        return AnalysisResult(sections=filtered, figures=self.figures,
                              cross_refs=self.cross_refs, total_lines=self.total_lines)


# ─── Section Classifier ──────────────────────────────────────────────────────

def classify_heading(text: str) -> Tuple[str, float]:
    """
    3-tier classification:
      Tier 1: exact keyword match (confidence 1.0)
      Tier 2: substring match (confidence 0.9)
      Tier 3: partial word match (confidence 0.7)
    """
    text_lower = text.lower().strip()

    for cat, kw_groups in CATEGORIES.items():
        all_kw = []
        for lang in ("keywords_zh", "keywords_en", "keywords_ja"):
            all_kw.extend(kw_groups.get(lang, []))
        for kw in all_kw:
            if kw.lower() == text_lower:
                return cat, 1.0

    for cat, kw_groups in CATEGORIES.items():
        all_kw = []
        for lang in ("keywords_zh", "keywords_en", "keywords_ja"):
            all_kw.extend(kw_groups.get(lang, []))
        for kw in all_kw:
            if kw.lower() in text_lower:
                return cat, 0.9

    text_head = text_lower[:60]
    for cat, kw_groups in CATEGORIES.items():
        all_kw = []
        for lang in ("keywords_zh", "keywords_en", "keywords_ja"):
            all_kw.extend(kw_groups.get(lang, []))
        matches = sum(1 for kw in all_kw if kw.lower() in text_head)
        if matches >= 1:
            return cat, 0.7

    return "GENERAL", 0.5


# ─── Figure & Cross-Reference Registry ───────────────────────────────────────

FIGURE_PATTERN = re.compile(
    r'\[Image on page (\d+)[^\]]*\]|(?:Figure|Fig\.|Table)\s+(\d+|[A-Z])',
    re.IGNORECASE
)
CROSSREF_PATTERN = re.compile(
    r'(?:see|refer to|as shown in|图|表)\s+(?:Figure|Fig\.|Table|图|表)\s*\.?\s*(\d+|[A-Z])',
    re.IGNORECASE
)


def extract_figures_and_refs(lines: List[str]) -> Tuple[List[FigureRef], List[Dict]]:
    figures = []
    cross_refs = []

    for i, line in enumerate(lines):
        m = FIGURE_PATTERN.search(line)
        if m:
            page = int(m.group(1)) if m.group(1) else None
            label = m.group(0)
            figures.append(FigureRef(label=label, page_hint=page, line_num=i + 1))

        cx = CROSSREF_PATTERN.search(line)
        if cx:
            cross_refs.append({"line": i + 1, "ref": cx.group(0), "target": cx.group(1)})

    return figures, cross_refs


# ─── Main Analysis ────────────────────────────────────────────────────────────

HEADING_PATTERN = re.compile(r'^(#{1,4})\s+(.+)$')

SKIP_PATTERNS = re.compile(
    r'^(table of contents|目录|<!-- |figures?\s*\(|\[image on page)', re.IGNORECASE
)


def analyse_markdown(text: str) -> AnalysisResult:
    """Analyse a Markdown document and classify its sections."""
    lines = text.split('\n')
    result = AnalysisResult(total_lines=len(lines))

    headings: List[Tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = HEADING_PATTERN.match(line.strip())
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if len(title) > 100:
                continue
            if SKIP_PATTERNS.match(title):
                continue
            headings.append((i, level, title))

    for idx, (line_num, level, title) in enumerate(headings):
        end_line = len(lines) - 1
        for j in range(idx + 1, len(headings)):
            if headings[j][1] <= level:
                end_line = headings[j][0] - 1
                break

        cat, conf = classify_heading(title)

        section_lines = lines[line_num + 1: min(line_num + 6, end_line + 1)]
        preview = " ".join(l.strip() for l in section_lines if l.strip())[:120]

        result.sections.append(Section(
            title=title, category=cat, confidence=conf,
            start_line=line_num + 1, end_line=end_line + 1,
            content_preview=preview,
        ))

    if not headings and text.strip():
        cat, conf = classify_heading(text[:100])
        result.sections.append(Section(
            title="(no headings detected)", category=cat, confidence=conf,
            start_line=1, end_line=len(lines), content_preview=text[:120],
        ))

    result.figures, result.cross_refs = extract_figures_and_refs(lines)
    return result
