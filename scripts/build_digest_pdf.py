#!/usr/bin/env python3
"""Generate a consolidated PDF digest for all technology tracks."""
from __future__ import annotations

import datetime as _dt
import math
import os
import struct
import textwrap
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "reports" / "tech-digest.pdf"
PAGE_WIDTH = 595.28  # A4 portrait in points
PAGE_HEIGHT = 841.89
MARGIN_LEFT = 56.0
MARGIN_RIGHT = 56.0
MARGIN_TOP = 72.0
MARGIN_BOTTOM = 64.0


class TrueTypeFont:
    """Minimal TrueType font parser for PDF embedding."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        self.tables: Dict[str, Tuple[int, int]] = {}
        self._parse_offset_table()
        self.units_per_em = self._parse_head()
        self.ascender, self.descender, self.line_gap, self.num_h_metrics = self._parse_hhea()
        self.num_glyphs = self._parse_maxp()
        self.advance_widths = self._parse_hmtx()
        self.cmap = self._parse_cmap()
        self.s_typo_ascender, self.s_typo_descender, self.s_cap_height = self._parse_os2()
        self.x_min, self.y_min, self.x_max, self.y_max = self._head_bbox
        self.italic_angle = self._parse_post()

    def _parse_offset_table(self) -> None:
        scaler, num_tables, _, _, _ = struct.unpack(">IHHHH", self.data[:12])
        offset = 12
        for _ in range(num_tables):
            tag, check, table_offset, length = struct.unpack(">4sIII", self.data[offset : offset + 16])
            self.tables[tag.decode("ascii")] = (table_offset, length)
            offset += 16

    def _parse_head(self) -> int:
        offset, length = self.tables["head"]
        table = self.data[offset : offset + length]
        units_per_em = struct.unpack(">H", table[18:20])[0]
        x_min, y_min, x_max, y_max = struct.unpack(">hhhh", table[36:44])
        self._head_bbox = (x_min, y_min, x_max, y_max)
        return units_per_em

    def _parse_hhea(self) -> Tuple[int, int, int, int]:
        offset, length = self.tables["hhea"]
        table = self.data[offset : offset + length]
        ascender, descender, line_gap = struct.unpack(">hhh", table[4:10])
        num_h_metrics = struct.unpack(">H", table[34:36])[0]
        return ascender, descender, line_gap, num_h_metrics

    def _parse_maxp(self) -> int:
        offset, length = self.tables["maxp"]
        table = self.data[offset : offset + length]
        num_glyphs = struct.unpack(">H", table[4:6])[0]
        return num_glyphs

    def _parse_hmtx(self) -> List[int]:
        offset, length = self.tables["hmtx"]
        table = self.data[offset : offset + length]
        widths: List[int] = []
        pos = 0
        for _ in range(self.num_h_metrics):
            advance_width, _lsb = struct.unpack(">HH", table[pos : pos + 4])
            widths.append(advance_width)
            pos += 4
        if self.num_glyphs > self.num_h_metrics:
            last_width = widths[-1]
            widths.extend([last_width] * (self.num_glyphs - self.num_h_metrics))
        return widths

    def _parse_cmap(self) -> Dict[int, int]:
        offset, length = self.tables["cmap"]
        table = self.data[offset : offset + length]
        version, num_tables = struct.unpack(">HH", table[:4])
        cmap: Dict[int, int] = {}
        preferred_subtable = None
        for i in range(num_tables):
            platform_id, encoding_id, sub_offset = struct.unpack(">HHI", table[4 + i * 8 : 12 + i * 8])
            if platform_id == 3 and encoding_id in {1, 10}:
                preferred_subtable = offset + sub_offset
                break
        if preferred_subtable is None:
            raise RuntimeError("Unicode cmap subtable not found in font")
        format_type = struct.unpack(">H", self.data[preferred_subtable : preferred_subtable + 2])[0]
        if format_type == 4:
            cmap.update(self._parse_cmap_format4(preferred_subtable))
        elif format_type == 12:
            cmap.update(self._parse_cmap_format12(preferred_subtable))
        else:
            raise RuntimeError(f"Unsupported cmap format: {format_type}")
        return cmap

    def _parse_cmap_format4(self, offset: int) -> Dict[int, int]:
        data = self.data
        length, language, seg_count_x2 = struct.unpack(">HHH", data[offset + 2 : offset + 8])
        seg_count = seg_count_x2 // 2
        end_offset = offset + 14
        end_count = struct.unpack(">" + "H" * seg_count, data[end_offset : end_offset + 2 * seg_count])
        reserved_pad_offset = end_offset + 2 * seg_count
        start_count = struct.unpack(">" + "H" * seg_count, data[reserved_pad_offset + 2 : reserved_pad_offset + 2 + 2 * seg_count])
        id_delta_offset = reserved_pad_offset + 2 + 2 * seg_count
        id_delta = struct.unpack(">" + "h" * seg_count, data[id_delta_offset : id_delta_offset + 2 * seg_count])
        id_range_offset_offset = id_delta_offset + 2 * seg_count
        id_range_offset = struct.unpack(">" + "H" * seg_count, data[id_range_offset_offset : id_range_offset_offset + 2 * seg_count])
        glyph_array_offset = id_range_offset_offset + 2 * seg_count
        cmap: Dict[int, int] = {}
        for i in range(seg_count):
            start = start_count[i]
            end = end_count[i]
            delta = id_delta[i]
            ro = id_range_offset[i]
            for code in range(start, end + 1):
                if ro == 0:
                    glyph = (code + delta) & 0xFFFF
                else:
                    ro_address = id_range_offset_offset + 2 * i
                    glyph_index_offset = ro_address + ro + 2 * (code - start)
                    if glyph_index_offset >= offset + length:
                        continue
                    glyph_index = struct.unpack(">H", data[glyph_index_offset : glyph_index_offset + 2])[0]
                    if glyph_index == 0:
                        glyph = 0
                    else:
                        glyph = (glyph_index + delta) & 0xFFFF
                cmap[code] = glyph
        return cmap

    def _parse_cmap_format12(self, offset: int) -> Dict[int, int]:
        data = self.data
        _format, _reserved = struct.unpack(">HH", data[offset : offset + 4])
        length, _language, num_groups = struct.unpack(">III", data[offset + 4 : offset + 16])
        cmap: Dict[int, int] = {}
        pos = offset + 16
        for _ in range(num_groups):
            start_char, end_char, start_glyph = struct.unpack(">III", data[pos : pos + 12])
            for code in range(start_char, end_char + 1):
                cmap[code] = start_glyph + (code - start_char)
            pos += 12
        return cmap

    def _parse_os2(self) -> Tuple[int, int, int]:
        offset, length = self.tables["OS/2"]
        table = self.data[offset : offset + length]
        version = struct.unpack(">H", table[:2])[0]
        s_typo_ascender = struct.unpack(">h", table[68:70])[0]
        s_typo_descender = struct.unpack(">h", table[70:72])[0]
        s_cap_height = s_typo_ascender
        if version >= 2 and len(table) >= 88:
            s_cap_height = struct.unpack(">h", table[88:90])[0]
        return s_typo_ascender, s_typo_descender, s_cap_height

    def _parse_post(self) -> float:
        offset, length = self.tables.get("post", (None, None))
        if offset is None:
            return 0.0
        table = self.data[offset : offset + length]
        italic_angle_fixed = struct.unpack(">l", table[4:8])[0]
        return italic_angle_fixed / 65536.0


class FontEncoder:
    """Encapsulates glyph metrics and encoding for PDF output."""

    def __init__(self, font: TrueTypeFont) -> None:
        self.font = font
        self.used_chars: List[str] = []
        self.char_set: Dict[str, None] = {}
        self.char_to_gid: Dict[str, int] = {}
        self.used_glyphs: Dict[int, None] = {}
        self.space_char = " "
        self.base_font_name = "/DejaVuSans"

    def _glyph_for_char(self, ch: str) -> int:
        code = ord(ch)
        glyph = self.font.cmap.get(code, 0)
        return glyph

    def ensure_text(self, text: str) -> None:
        for ch in text:
            if ch not in self.char_set:
                self.char_set[ch] = None
                glyph = self._glyph_for_char(ch)
                self.char_to_gid[ch] = glyph
                self.used_glyphs[glyph] = None
                self.used_chars.append(ch)

    def measure_text(self, text: str, font_size: float) -> float:
        total = 0
        for ch in text:
            glyph = self.char_to_gid.get(ch)
            if glyph is None:
                self.ensure_text(ch)
                glyph = self.char_to_gid[ch]
            width_units = self.font.advance_widths[glyph]
            total += width_units
        return total / self.font.units_per_em * font_size

    def encode_text(self, text: str) -> str:
        if text:
            self.ensure_text(text)
        hex_buffer = [f"{self.char_to_gid[ch]:04X}" for ch in text]
        return "<" + "".join(hex_buffer) + ">"

    def _widths_1000(self) -> Dict[int, int]:
        widths: Dict[int, int] = {}
        for glyph in self.used_glyphs:
            width_units = self.font.advance_widths[glyph]
            widths[glyph] = int(round(width_units * 1000 / self.font.units_per_em))
        return widths

    def build_pdf_objects(self, pdf: "PDFDocument") -> int:
        if not self.used_chars:
            self.ensure_text(" ")
        widths = self._widths_1000()
        max_gid = max(widths.keys()) if widths else 0
        cid_to_gid = bytearray((max_gid + 1) * 2)
        for glyph in range(max_gid + 1):
            value = glyph if glyph in self.used_glyphs else 0
            struct.pack_into(">H", cid_to_gid, glyph * 2, value)
        cid_map_obj = pdf.add_stream({}, bytes(cid_to_gid), compress=True)

        # ToUnicode CMap
        entries = []
        for ch in sorted(self.used_chars, key=lambda c: (ord(c))):
            gid = self.char_to_gid[ch]
            cid_hex = f"{gid:04X}"
            unicode_hex = ch.encode("utf-16-be").hex().upper()
            entries.append(f"<{cid_hex}> <{unicode_hex}>")
        chunks = []
        for i in range(0, len(entries), 100):
            chunk = entries[i : i + 100]
            chunks.append(f"{len(chunk)} beginbfchar\n" + "\n".join(chunk) + "\nendbfchar\n")
        cmap_content = (
            "/CIDInit /ProcSet findresource begin\n"
            "12 dict begin\n"
            "begincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /Adobe-Identity-UCS def\n"
            "/CMapType 2 def\n"
            "1 begincodespacerange\n"
            "<0000> <FFFF>\n"
            "endcodespacerange\n"
            + "".join(chunks)
            + "endcmap\n"
            "CMapName currentdict /CMap defineresource pop\n"
            "end\nend\n"
        )
        to_unicode_obj = pdf.add_stream({}, cmap_content.encode("utf-8"), compress=True)

        font_file_obj = pdf.add_stream({"Length1": str(len(self.font.data))}, self.font.data, compress=True)

        ascent = int(round(self.font.s_typo_ascender * 1000 / self.font.units_per_em))
        descent = int(round(self.font.s_typo_descender * 1000 / self.font.units_per_em))
        cap_height = int(round(self.font.s_cap_height * 1000 / self.font.units_per_em))
        bbox = [
            int(round(self.font.x_min * 1000 / self.font.units_per_em)),
            int(round(self.font.y_min * 1000 / self.font.units_per_em)),
            int(round(self.font.x_max * 1000 / self.font.units_per_em)),
            int(round(self.font.y_max * 1000 / self.font.units_per_em)),
        ]
        default_width = widths.get(self.char_to_gid.get(self.space_char, 0), 600)

        # Build W array string
        w_entries: List[str] = []
        for glyph in sorted(widths.keys()):
            width = widths[glyph]
            if width == default_width and glyph != 0:
                continue
            w_entries.append(f"{glyph} {width}")
        w_array = "[" + " ".join(w_entries) + "]"

        font_descriptor_obj = pdf.add_object({
            "Type": "/FontDescriptor",
            "FontName": self.base_font_name,
            "Flags": "4",
            "Ascent": str(ascent),
            "Descent": str(descent),
            "CapHeight": str(cap_height),
            "ItalicAngle": str(self.font.italic_angle),
            "StemV": "80",
            "FontBBox": "[{} {} {} {}]".format(*bbox),
            "FontFile2": f"{font_file_obj} 0 R",
        })

        descendant_obj = pdf.add_object({
            "Type": "/Font",
            "Subtype": "/CIDFontType2",
            "BaseFont": self.base_font_name,
            "CIDSystemInfo": "<< /Registry (Adobe) /Ordering (Identity) /Supplement 0 >>",
            "FontDescriptor": f"{font_descriptor_obj} 0 R",
            "DW": str(default_width),
            "W": w_array,
            "CIDToGIDMap": f"{cid_map_obj} 0 R",
        })

        font_obj = pdf.add_object({
            "Type": "/Font",
            "Subtype": "/Type0",
            "BaseFont": self.base_font_name,
            "Encoding": "/Identity-H",
            "DescendantFonts": f"[{descendant_obj} 0 R]",
            "ToUnicode": f"{to_unicode_obj} 0 R",
        })
        return font_obj


class PDFDocument:
    def __init__(self) -> None:
        self.objects: List[bytes] = []
        self.trailer_extra: Dict[str, str] = {}

    def add_object(self, dictionary: Dict[str, str]) -> int:
        parts = ["<<"]
        for key, value in dictionary.items():
            parts.append(f"/{key} {value}")
        parts.append(">>")
        obj_bytes = " ".join(parts).encode("utf-8")
        self.objects.append(obj_bytes)
        return len(self.objects)

    def add_stream(self, dictionary: Dict[str, str], data: bytes, compress: bool = False) -> int:
        if compress:
            data = zlib.compress(data)
            dictionary = dict(dictionary)
            dictionary["Filter"] = "/FlateDecode"
        dictionary = dict(dictionary)
        dictionary["Length"] = str(len(data))
        header_parts = ["<<"]
        for key, value in dictionary.items():
            header_parts.append(f"/{key} {value}")
        header_parts.append(">>")
        header = " ".join(header_parts).encode("utf-8")
        stream_bytes = b"\n".join([header, b"stream", data, b"endstream"])
        self.objects.append(stream_bytes)
        return len(self.objects)

    def set_trailer_entry(self, key: str, value: str) -> None:
        self.trailer_extra[key] = value

    def write(self, path: Path, root_object: int) -> None:
        with path.open("wb") as fh:
            fh.write(b"%PDF-1.6\n%\xE2\xE3\xCF\xD3\n")
            offsets = [0]
            for index, obj in enumerate(self.objects, start=1):
                offsets.append(fh.tell())
                fh.write(f"{index} 0 obj\n".encode("ascii"))
                fh.write(obj)
                fh.write(b"\nendobj\n")
            xref_position = fh.tell()
            fh.write(f"xref\n0 {len(self.objects) + 1}\n".encode("ascii"))
            fh.write(b"0000000000 65535 f \n")
            for offset in offsets[1:]:
                fh.write(f"{offset:010d} 00000 n \n".encode("ascii"))
            trailer_parts = ["<<", f"/Size {len(self.objects) + 1}", f"/Root {root_object} 0 R"]
            for key, value in self.trailer_extra.items():
                trailer_parts.append(f"/{key} {value}")
            trailer_parts.append(">>")
            fh.write("\n".join(["trailer", " ".join(trailer_parts), "startxref", str(xref_position), "%%EOF"]).encode("ascii"))


@dataclass
class Paragraph:
    text: str
    kind: str = "body"  # body, heading, label
    size: float = 11.5
    space_before: float = 0.0
    space_after: float = 10.0
    color: Tuple[float, float, float] | None = None
    bullet: bool = False
    indent: float = 0.0


class LayoutEngine:
    def __init__(self, font: FontEncoder) -> None:
        self.font = font
        self.pages: List[Dict[str, object]] = []
        self.current_page: Dict[str, object] | None = None
        self.cursor_y: float = 0.0
        self.line_spacing_factor = 1.45

    def _new_page(self) -> None:
        self.current_page = {"commands": []}
        self.pages.append(self.current_page)
        self.cursor_y = PAGE_HEIGHT - MARGIN_TOP

    def _ensure_page(self) -> None:
        if self.current_page is None:
            self._new_page()

    def _append_command(self, command: str) -> None:
        assert self.current_page is not None
        self.current_page["commands"].append(command)

    def _set_color(self, color: Tuple[float, float, float] | None) -> None:
        if color is None:
            return
        r, g, b = color
        self._append_command(f"{r:.3f} {g:.3f} {b:.3f} rg")

    def add_heading(self, text: str, level: int = 1) -> None:
        size = 26 if level == 1 else 17 if level == 2 else 14
        space_before = 0 if level == 1 and not self.pages else 24
        paragraph = Paragraph(
            text=text,
            kind="heading",
            size=size,
            space_before=space_before,
            space_after=16 if level == 1 else 12,
            color=(0.05, 0.24, 0.55) if level <= 2 else (0.1, 0.28, 0.6),
        )
        self.add_paragraph(paragraph)

    def add_label(self, text: str) -> None:
        self.add_paragraph(
            Paragraph(
                text=text.upper(),
                kind="label",
                size=11.5,
                space_before=6,
                space_after=6,
                color=(0.16, 0.38, 0.66),
            )
        )

    def add_paragraph(self, paragraph: Paragraph) -> None:
        self._ensure_page()
        text = paragraph.text.replace("\u00a0", " ")
        if not text:
            self.cursor_y -= paragraph.space_before + paragraph.space_after
            return
        words = text.split()
        if paragraph.bullet:
            prefix = "• "
            self.font.ensure_text(prefix)
        else:
            prefix = ""
        max_width = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
        self.cursor_y -= paragraph.space_before
        space_width = self.font.measure_text(" ", paragraph.size)
        bullet_indent = 14.0
        line_indent = paragraph.indent
        line_text = prefix
        line_width = self.font.measure_text(prefix, paragraph.size) if prefix else 0.0
        available_width = max_width - line_indent
        lines: List[Tuple[float, str]] = []
        for word in words:
            word_width = self.font.measure_text(word, paragraph.size)
            add_space = bool(line_text.strip())
            projected = line_width + (space_width if add_space else 0.0) + word_width
            if projected <= available_width or not line_text.strip():
                if add_space:
                    line_text += " "
                    line_width += space_width
                line_text += word
                line_width += word_width
            else:
                lines.append((line_indent, line_text))
                line_indent = paragraph.indent + (bullet_indent if paragraph.bullet else 0.0)
                available_width = max_width - line_indent
                line_text = word
                line_width = word_width
        if line_text:
            lines.append((line_indent, line_text))
        leading = paragraph.size * self.line_spacing_factor
        for idx, (indent, line) in enumerate(lines):
            if self.cursor_y < MARGIN_BOTTOM + paragraph.size:
                self._new_page()
            x = MARGIN_LEFT + indent
            y = self.cursor_y
            color = paragraph.color
            if color:
                self._set_color(color)
            self._append_command(
                f"BT /F1 {paragraph.size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm {self.font.encode_text(line)} Tj ET"
            )
            if color:
                self._append_command("0 0 0 rg")
            self.cursor_y -= leading
        self.cursor_y += leading - paragraph.size * self.line_spacing_factor
        self.cursor_y -= paragraph.space_after

    def add_bullet_list(self, items: Sequence[str]) -> None:
        for item in items:
            self.add_paragraph(
                Paragraph(text=item, bullet=True, indent=6.0, space_after=6.0)
            )
        if items:
            self.cursor_y -= 4.0

    def add_spacing(self, amount: float) -> None:
        self.cursor_y -= amount

    def finalize(self) -> None:
        pass


def build_content() -> List[Tuple[str, List[Dict[str, object]]]]:
    today = _dt.date.today().strftime("%d.%m.%Y")
    return [
        (
            "Инфраструктура данных и блокчейн",
            [
                {
                    "title": "Корпоративные блокчейн-платформы",
                    "summary": (
                        "Корпоративные блокчейн-платформы обеспечивают прозрачность и неизменяемость транзакций"
                        " в мультистейкхолдерских процессах. Они используют permissioned DLT с BFT/RAFT, позволяют"
                        " строить смарт-контракты, токенизировать активы, автоматизировать комплаенс и обеспечивать"
                        " traceability в цепочках поставок, документообороте и финансовых операциях."
                    ),
                    "drivers": [
                        "Регуляторные требования к прозрачности цепочек поставок и ESG-отчётности.",
                        "Цифровые валюты центральных банков и институциональная токенизация.",
                        "Борьба с фродом и ускорение трансграничных расчётов.",
                    ],
                    "status": [
                        "Массовое внедрение ожидается через 3–5 лет в цепочках поставок и 5–7 лет на капитальных рынках.",
                        "Успешные пилоты в ритейле, энергетике, логистике и масштабные программы в банках (JP Morgan Onyx, HSBC Orion).",
                        "Основные вендоры: IBM, R3, ConsenSys, Digital Asset, Hedera, VMware.",
                    ],
                    "scenarios": [
                        "Цифровые активы и токенизация: выпуск security tokens, рынки токенизированных товаров, KYC/AML-контроль.",
                        "Цепочки поставок: прослеживаемость происхождения, автоматизация сертификаций и таможенных процедур.",
                        "Документооборот и идентичность: self-sovereign ID, цифровые паспорта продукции, zero-knowledge доказательства.",
                        "Инфраструктура платежей: instant settlement, интеграция с ERP, смарт-контракты для escrow и trade finance.",
                    ],
                },
                {
                    "title": "Управление данными и целостность на основе блокчейна",
                    "summary": (
                        "Корпоративные системы управления данными фиксируют lineage и качество через блокчейн, моделируя"
                        " корпоративные знания в RDF/RDFS/OWL 2 и SKOS. Они валидируют структуры по SHACL, выполняют"
                        " запросы SPARQL 1.2, а леджеры сохраняют хэши преобразований для доказуемой неизменности и аудита."
                    ),
                    "drivers": [
                        "Рост выручки за счёт персонализации и семантического поиска на онтологиях и GraphRAG.",
                        "Снижение OPEX благодаря виртуализации данных через OBDA/OBDI и R2RML вместо тяжёлых ETL.",
                        "Командный compliance за счёт автоматизированной валидации SHACL и провенанса PROV-O.",
                    ],
                    "status": [
                        "Массовое внедрение ожидается через 2–5 лет, консолидация RDF/SPARQL 1.2 и отраслевых data spaces.",
                        "Рынок растёт на 26–31% CAGR (2025), спрос формируют BFSI и здравоохранение.",
                        "Ключевые игроки: Amazon Neptune, Ontotext GraphDB, Fluree Nexus, TopBraid EDG и другие.",
                    ],
                    "focus": [
                        "Модели и онтологии: RDF, RDFS, OWL 2, SKOS, SHACL, DCAT/Schema.org.",
                        "Семантическая интеграция: OBDA/OBDI, R2RML, виртуализация данных и выравнивание онтологий.",
                        "Хранение и качество: триплсторы, доказательства lineage, PROV-O, каталоги метаданных.",
                    ],
                },
            ],
        ),
        (
            "Семантические данные и аналитика",
            [
                {
                    "title": "Дезагрегированные архитектуры хранения",
                    "summary": (
                        "Платформы объединяют HL7 FHIR R4/R5 и OMOP CDM для загрузки, гармонизации и предоставления"
                        " продольных клинических данных. Подход поддерживает FHIR REST/Bulk Data, Terminology Services"
                        " и SMART on FHIR, обеспечивая интероперабельность, прозрачный аудит и безопасную интеграцию API."
                    ),
                    "drivers": [
                        "Снижение OPEX благодаря стандартизованным FHIR-интерфейсам и терминологическому сопоставлению.",
                        "Ускорение time-to-insight для когортостроения, фенотипирования и популяционной аналитики.",
                        "Соответствие требованиям CMS/ONC и TEFCA к FHIR API, Bulk Data и прозрачному аудиту.",
                    ],
                    "status": [
                        "Горизонт внедрения 2–5 лет при росте инфраструктуры FHIR/OMOP и managed-сервисов.",
                        "Рынок растёт на 12–15% CAGR (2025), инвесторы концентрируются на интероперабельности.",
                        "Вендоры: Google Cloud Healthcare API, Azure Health Data Services, AWS HealthLake, InterSystems IRIS for Health.",
                    ],
                    "focus": [
                        "Модели данных: HL7 FHIR R4/R5, OMOP CDM, patient-centric и longitudinal модели.",
                        "Интеграция: ETL/ELT EHR→FHIR, FHIR→OMOP mapping, SNOMED CT, LOINC, RxNorm, Terminology Services.",
                        "Хранилища и аналитика: FHIR JSON stores, реляционный OMOP, parquet, BigQuery exports, population health аналитика.",
                    ],
                },
                {
                    "title": "Платформы корпоративных графов знаний",
                    "summary": (
                        "Оркестрованные пайплайны данных объединяют источники, обогащают онтологиями и публикуют"
                        " унифицированные данные для аналитики, графов знаний и LLM RAG. Ядро строится на RDF/OWL,"
                        " SKOS, валидации SHACL/SHEx, запросах SPARQL 1.2, публикациях JSON-LD и провенансе PROV-O."
                    ),
                    "drivers": [
                        "Персонализация и семантический поиск (GraphRAG, гибридный поиск).",
                        "Снижение OPEX через семантическую федерацию и унификацию схем.",
                        "Ускорение time-to-insight за счёт воспроизводимых оркестраций и семантических запросов.",
                    ],
                    "status": [
                        "Массовое внедрение ожидается через 2–5 лет (SPARQL 1.2, RDF 1.2, канонизация наборов).",
                        "Рынок растёт на 22–30% CAGR (2025).",
                        "Ключевые вендоры: Stardog, Amazon Neptune, Franz AllegroGraph, Deloitte×Neo4j и др.",
                    ],
                    "focus": [
                        "Модели и семантика: онтологии, таксономии, справочники, RDF/OWL, SHACL/SHEx, PROV-O.",
                        "Языки и доступ: SPARQL 1.2, JSON-LD, SKOS, R2RML/CSVW, XPath/XQuery.",
                        "Операции: lineage, каталоги метаданных, управляемые пайплайны публикации, интеграция с LLM.",
                    ],
                },
                {
                    "title": "Семантические конвейеры интеграции данных",
                    "summary": (
                        "Специализированные хранилища и индексные движки объединяют векторное сходство с реляционной"
                        " фильтрацией, гибридными предикатами и объединёнными планами запросов. Поддержка ANN/HNSW,"
                        " гибридных представлений, ISO GQL, SPARQL 1.2 и lineage по W3C PROV-O ускоряет RAG и"
                        " семантическое извлечение на масштабе предприятия."
                    ),
                    "drivers": [
                        "Персонализация и рекомендации на эмбеддингах с гибридной фильтрацией.",
                        "Снижение OPEX за счёт консолидации векторного поиска и SQL в одном движке.",
                        "Ускорение time-to-insight благодаря конвейерам семантического извлечения и RAG.",
                    ],
                    "status": [
                        "Горизонт массового внедрения 0–2 года.",
                        "Рынок растёт на 32–38% CAGR (2025).",
                        "Ключевые вендоры: Weaviate, AlloyDB for PostgreSQL, Azure AI Search, Amazon OpenSearch Service.",
                    ],
                    "focus": [
                        "Модели и схемы: плотные эмбеддинги, гибридные Vector+SQL схемы, метаданные атрибутов.",
                        "Индексы и движки: ANN/HNSW, обучаемые индексы, векторные и гибридные БД, managed DBaaS.",
                        "Конвейеры: semantic ETL, RAG pipelines, баланс точность/задержка, масштабирование NNS.",
                    ],
                },
            ],
        ),
        (
            "Стриминг и реальное время",
            [
                {
                    "title": "Распределённая потоковая обработка событий",
                    "summary": (
                        "Платформы объединяют долговечные журналы событий, pub/sub, stateful stream processing и"
                        " управление схемами. Поддерживаются обработка по event time, водяные знаки, оконные модели"
                        " и complex event processing. Вендоры снижают OPEX через потоковый ETL/ELT, ускоряют"
                        " аналитические циклы и обеспечивают соблюдение требований за счёт lineage и data contracts."
                    ),
                    "drivers": [
                        "Персонализация и оперативная аналитика в реальном времени.",
                        "Замена batch-ETL потоковыми пайплайнами и сокращение CapEx/OPEX.",
                        "Управляемый lineage, schema registry и контракты данных для compliance.",
                    ],
                    "status": [
                        "Горизонт массового внедрения 2–5 лет.",
                        "CloudEvents получил статус Graduated в CNCF (2024).",
                        "Рынок растёт на 14–19% CAGR (2025).",
                    ],
                    "focus": [
                        "Семантика потоков: event time, watermarks, session/sliding windows, stateful processing.",
                        "Обработка: streaming SQL, CEP, windowed joins, continuous queries.",
                        "Качество и операции: schema registry, data contracts, потоковый ETL/ELT, out-of-order handling.",
                    ],
                },
                {
                    "title": "Платформы real-time продуктов",
                    "summary": (
                        "Реализация low-latency сценариев для цифровых продуктов строится на тех же потоковых"
                        " движках, но акцентирует бизнес-ценность: персонализацию, сокращение издержек, time-to-insight"
                        " и доверенный аудит данных. Глобальные программы расширяют managed сервисы, SLA и операционную"
                        " наблюдаемость stateful пайплайнов."
                    ),
                    "value": [
                        "Персонализация в реальном времени за счёт CEP и оконных агрегатов.",
                        "Снижение OPEX/CapEx благодаря потоковому ETL/ELT поверх журналов событий.",
                        "Time-to-insight: непрерывные агрегаты, автоматические алерты и метрики.",
                        "Качество и compliance: schema registry, политика совместимости, lineage.",
                        "Data loss prevention: exactly-once семантика, чекпойнты и обработка внепорядковых событий.",
                        "Time-to-market: декларативные операторы и развязка продюсеров/консьюмеров.",
                        "Доступность и SLA: масштабирование, репликация, управление состоянием и чекпойнты.",
                    ],
                    "roadmap": [
                        "0–2 года: stateful stream processing и watermarks по умолчанию, CloudEvents в стандартах, обязательные метрики и lineage.",
                        "2–5 лет: консолидация streaming SQL/CEP, кросс-облачная интероперабельность и управляемое governance.",
                        "5–10 лет: глобальная exactly-once семантика, стандартизация edge-to-cloud синхронизации и contract-driven потоки.",
                    ],
                    "market": [
                        "TAM $5.6–6.1B, SAM $1.43–1.72B, SOM $1.0–1.6B (оценка 2025).",
                        "CAGR 2025–2029: около 14–19% благодаря AI/LLM пайплайнам и managed-сервисам.",
                        "Региональный фокус: Северная Америка (low-latency trading, AdTech), Европа (IoT, энерготрейдинг), АТР (суперприложения).",
                    ],
                },
            ],
        ),
        (
            "SaaS рост и монетизация",
            [
                {
                    "title": "Customer Intelligence & Success AI",
                    "summary": (
                        "AI-помощник customer success объединяет usage telemetry, поддержку, биллинг и NPS для"
                        " построения единого customer graph. Модели прогнозируют отток, сигнализируют о расширениях"
                        " и подсказывают playbook для CSM-команд."
                    ),
                    "value": [
                        "Снижение оттока платящих клиентов на 25–35%.",
                        "Рост расширений на 10–18% благодаря AI-рекомендациям.",
                        "Трёхкратное ускорение подготовки health review и QBR.",
                    ],
                    "components": [
                        "Единый customer graph с телеметрией, биллингом, поддержкой и NPS.",
                        "ML-модели churn & expansion и генеративный success assistant.",
                        "Дашборды ранних сигналов и интеграции со Slack/Teams для моментальных действий.",
                    ],
                    "steps": [
                        "Поднимите качество данных: синхронизируйте события продукта и биллинга в near-real-time.",
                        "Постройте health-score модель с весами по активации, частоте использования и финансам.",
                        "Автоматизируйте реакцию: плейбуки для risk, expansion, renewal и контроль конверсии.",
                    ],
                },
                {
                    "title": "Pricing & Packaging Experiments",
                    "summary": (
                        "Платформа управляет экспериментами по ценообразованию и упаковке, объединяя биллинг, usage"
                        " и CRM. Наблюдение за эластичностью и willingness-to-pay помогает находить оптимальные"
                        " монетизационные стратегии без потери NRR."
                    ),
                    "value": [
                        "До +12% к ARR за счёт динамической корректировки планов.",
                        "Сокращение времени запуска эксперимента с недель до дней.",
                        "Прозрачность влияния на LTV/CAC, маржинальность и churn."
                    ],
                    "components": [
                        "Каталог гипотез и управление экспериментами с трекингом аудиторий.",
                        "Интеграции с биллингом, CRM и продуктовой телеметрией для расчёта метрик.",
                        "AI-аналитика willingness-to-pay и рекомендации по следующему тесту.",
                    ],
                    "steps": [
                        "Соберите базовую метрику монетизации: NRR, LTV/CAC, ARPU по сегментам.",
                        "Определите гипотезы по ценовым уровням, лимитам, бандлам и допродажам.",
                        "Запускайте A/B и многорукавые тесты с автоматическим расчётом значимости и rollout-планом.",
                    ],
                },
                {
                    "title": "Product-Led Growth Automation",
                    "summary": (
                        "Автоматизация PLG связывает активацию, расширения и монетизацию через продуктовые сигналы."
                        " Пайплайны оркестрируют триггеры в продукте, коммуникации и upsell-модели, фокусируясь"
                        " на self-serve сегменте."
                    ),
                    "value": [
                        "Ускорение активации и paywall-conversion на 15–25%.",
                        "Рост expansion revenue и платёжных апгрейдов за счёт таргетированных плейбуков.",
                        "Снижение стоимости привлечения через self-serve рост и прогрев лидов.",
                    ],
                    "components": [
                        "Сегментация пользователей по событиям продукта и сигналам ценности.",
                        "Автоматические journeys с in-product сообщениями, email и уведомлениями.",
                        "Usage-based scoring для передачи горячих лидов в продажи.",
                    ],
                    "steps": [
                        "Соберите единый event taxonomy и определите North Star Metrics.",
                        "Постройте scoring-модель для product qualified leads и expansion сигналов.",
                        "Организуйте эксперименты с триггерами, paywall и PQL handoff в CRM.",
                    ],
                },
                {
                    "title": "Revenue Operations Automation",
                    "summary": (
                        "RevOps-автоматизация синхронизирует маркетинг, продажи и успех клиентов. Единые данные"
                        " и playbooks обеспечивают прогнозируемость выручки, прозрачность воронки и согласованность"
                        " команд."
                    ),
                    "value": [
                        "Повышение точности прогноза выручки и сокращение cycle time сделок.",
                        "Единый взгляд на pipeline, покрытие аккаунтов и ресурсную нагрузку.",
                        "Согласованность GTM-команд и автоматизированные триггеры на этапах сделки.",
                    ],
                    "components": [
                        "Объединённый data layer из CRM, маркетинговых и продуктовых систем.",
                        "Pipeline analytics, сценарии what-if и автоматические оповещения.",
                        "Playbooks для handoff между маркетингом, продажами и success-командой.",
                    ],
                    "steps": [
                        "Синхронизируйте источники данных и устраните дубликаты аккаунтов.",
                        "Определите единый SLA handoff и метрики качества лида/сделки.",
                        "Автоматизируйте обновления pipeline, алерты по рискам и постпродажный контроль.",
                    ],
                },
            ],
        ),
    ]


def build_pdf() -> None:
    font = TrueTypeFont(FONT_PATH)
    encoder = FontEncoder(font)
    layout = LayoutEngine(encoder)
    layout.add_heading("Tech Digest 2025", level=1)
    layout.add_paragraph(
        Paragraph(
            text=(
                "Консолидированный обзор ключевых технологических направлений SciArticle."
                " Документ объединяет инфраструктурные платформы, семантические данные, потоковую"
                " обработку и стратегии роста SaaS-продуктов. Актуальность на {}.".format(
                    _dt.date.today().strftime("%d.%m.%Y")
                )
            ),
            size=12.5,
            space_after=18.0,
        )
    )
    layout.add_paragraph(
        Paragraph(
            text=(
                "Материал построен по единым блокам: краткое описание ценности, основные драйверы,"
                " зрелость рынка и практические фокусы внедрения."
            ),
            size=12.5,
            space_after=24.0,
        )
    )

    for group_title, items in build_content():
        layout.add_heading(group_title, level=2)
        for item in items:
            layout.add_heading(item["title"], level=3)
            layout.add_paragraph(Paragraph(text=item.get("summary", ""), space_after=12.0))
            if "drivers" in item:
                layout.add_label("Драйверы")
                layout.add_bullet_list(item["drivers"])
            if "status" in item:
                layout.add_label("Рынок и зрелость")
                layout.add_bullet_list(item["status"])
            if "scenarios" in item:
                layout.add_label("Ключевые сценарии")
                layout.add_bullet_list(item["scenarios"])
            if "focus" in item:
                layout.add_label("Фокус технологий")
                layout.add_bullet_list(item["focus"])
            if "value" in item:
                layout.add_label("Ценность")
                layout.add_bullet_list(item["value"])
            if "components" in item:
                layout.add_label("Компоненты")
                layout.add_bullet_list(item["components"])
            if "steps" in item:
                layout.add_label("Практические шаги")
                layout.add_bullet_list(item["steps"])
            if "roadmap" in item:
                layout.add_label("Горизонт внедрения")
                layout.add_bullet_list(item["roadmap"])
            if "market" in item:
                layout.add_label("Метрики рынка")
                layout.add_bullet_list(item["market"])
            layout.add_spacing(6.0)

    # Add page numbers
    total_pages = len(layout.pages)
    for idx, page in enumerate(layout.pages, start=1):
        page_label = f"{idx} / {total_pages}"
        width = encoder.measure_text(page_label, 9.0)
        x = (PAGE_WIDTH - width) / 2
        y = MARGIN_BOTTOM / 2
        page["commands"].append(f"0.45 0.45 0.45 rg")
        page["commands"].append(
            f"BT /F1 9 Tf 1 0 0 1 {x:.2f} {y:.2f} Tm {encoder.encode_text(page_label)} Tj ET"
        )
        page["commands"].append("0 0 0 rg")

    pdf = PDFDocument()
    font_obj = encoder.build_pdf_objects(pdf)

    pages_objects: List[int] = []
    for page in layout.pages:
        content = "\n".join(page["commands"]).encode("utf-8")
        content_obj = pdf.add_stream({}, content, compress=True)
        page_obj = pdf.add_object(
            {
                "Type": "/Page",
                "Parent": "2 0 R",
                "MediaBox": f"[0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}]",
                "Contents": f"{content_obj} 0 R",
                "Resources": f"<< /Font << /F1 {font_obj} 0 R >> >>",
            }
        )
        pages_objects.append(page_obj)

    kids = "[" + " ".join(f"{obj} 0 R" for obj in pages_objects) + "]"
    pages_obj = pdf.add_object({"Type": "/Pages", "Kids": kids, "Count": str(len(pages_objects))})
    catalog_obj = pdf.add_object({"Type": "/Catalog", "Pages": f"{pages_obj} 0 R"})
    pdf.write(OUTPUT_PATH, catalog_obj)
    print(f"PDF сохранён: {OUTPUT_PATH}")


if __name__ == "__main__":
    if not FONT_PATH.exists():
        raise SystemExit(f"Font not found at {FONT_PATH}")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    build_pdf()
