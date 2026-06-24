import os
import re
import win32com.client as win32
import pandas as pd
import pythoncom
import time
from collections import Counter, defaultdict
from win32com.client import Dispatch
from datetime import datetime

# 圈数字符号常量
CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩"
POSITION_RE = re.compile(r"row\[(\d+)\]\[(\d+)\]\[(\d+)\]")
LINE_BREAK_RE = re.compile(r"[\r\n]+")

# 当前目录
CURRENT_DIR = os.getcwd()


def num_to_circled(n: int) -> str:
    """将数字 1-10 转换为对应的圈数字符号"""
    if n < 1 or n > 10:
        raise ValueError(f"序号 {n} 超出范围(1-10)，无法生成圈数字符号")
    return CIRCLED_NUMBERS[n - 1]


def get_circle_num_val(text: str) -> int:
    """从文本中提取最后出现的圈数字的值，如果没有返回0"""
    found = [c for c in text if c in CIRCLED_NUMBERS]
    if not found:
        return 0
    return CIRCLED_NUMBERS.index(found[-1]) + 1


def read_mismatch_block_win32(filepath: str, excel_app=None) -> pd.DataFrame:
    """从校对结果xlsx中读取不匹配项，返回[编码, K3型号, 规格型号] DataFrame"""
    own_com = False
    own_excel = False
    wb = None
    try:
        if excel_app is None:
            pythoncom.CoInitialize()
            own_com = True
            excel_app = Dispatch('Excel.Application')
            excel_app.Visible = False
            excel_app.DisplayAlerts = False
            own_excel = True

        wb = excel_app.Workbooks.Open(filepath)
        ws = wb.Sheets(1)  # 默认读取第一个工作表

        data_list = []
        used_rows = ws.UsedRange.Rows.Count

        for row in range(1, used_rows + 1):
            b_val = ws.Cells(row, 2).Value
            if not b_val:
                continue
            b_val_str = str(b_val).strip()

            if b_val_str in ("物料名称 不匹配", "规格型号 不匹配"):
                a_val = ws.Cells(row, 1).Value
                c_val = ws.Cells(row, 3).Value
                d_val = ws.Cells(row, 4).Value

                # 清洗A列: 去掉 "编码 "
                if a_val:
                    a_val = str(a_val).strip()
                    if a_val.startswith("编码 "):
                        a_val = a_val.replace("编码 ", "", 1)

                # 清洗D列: 去掉 "❌ 设计文件描述: "
                if d_val:
                    d_val = str(d_val).strip()
                    prefix = "❌ 设计文件描述: "
                    if d_val.startswith(prefix):
                        d_val = d_val[len(prefix):]

                data_list.append([a_val, c_val, d_val])

        return pd.DataFrame(data_list, columns=["编码", "K3型号", "规格型号"])

    finally:
        if wb is not None:
            try:
                wb.Close(False)
            except Exception:
                pass
        if own_excel and excel_app is not None:
            try:
                excel_app.Quit()
            except Exception:
                pass
        if own_com:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def read_word_tables_from_doc(doc, include_page: bool = False, max_retries: int = 3):
    """
    从已打开的Word文档中读取所有表格，返回DataFrame。
    位置格式: row[表格编号][行][列]（表格编号从1开始，行列从0开始）
    include_page=True 时，DataFrame 额外包含「页码」列（通过 cell.Range.Information(3) 获取）。

    # 注意: 当前第一维度使用「表格编号」。如需改为「页码」，
    # 可将 pos 中的 t_index 替换为 page_num，即:
    #   pos = f"row[{page_num}][{r}][{c}]"
    # 同时需要同步修改所有解析位置字符串的函数。
    """
    try:
        all_data = []
        table_count = doc.Tables.Count
        for t_index in range(1, table_count + 1):
            rows = cols = 0
            for attempt in range(max_retries):
                try:
                    table = doc.Tables(t_index)
                    rows = table.Rows.Count
                    cols = table.Columns.Count
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(0.2 * (attempt + 1))

            for r in range(rows):
                for c in range(cols):
                    cell_value = ""
                    page_num = 0
                    try:
                        cell = table.Cell(r + 1, c + 1)
                        cell_value = cell.Range.Text
                        cell_value = cell_value.strip("\r\x07").strip()
                        if include_page:
                            page_num = int(cell.Range.Information(3))  # wdActiveEndPageNumber
                    except Exception:
                        cell_value = ""
                        page_num = 0

                    if not cell_value:
                        continue

                    pos = f"row[{t_index}][{r}][{c}]"
                    if include_page:
                        all_data.append((t_index, pos, cell_value, page_num))
                    else:
                        all_data.append((t_index, pos, cell_value))

        if include_page:
            df = pd.DataFrame(all_data, columns=["表格编号", "位置", "值", "页码"])
        else:
            df = pd.DataFrame(all_data, columns=["表格编号", "位置", "值"])
        return df
    except Exception as e:
        print(f"读取Word表格时出错: {str(e)}")
        raise e


def build_position_value_map(df):
    """构建 位置 -> 值 映射，避免频繁筛选 DataFrame。"""
    return {
        str(pos).strip(): val
        for pos, val in zip(df["位置"], df["值"])
    }


def get_value_from_df(df, table_index, position_str, position_value_map=None):
    """按位置字符串查询 DataFrame 中的值"""
    if position_value_map is not None:
        return position_value_map.get(position_str.strip())

    row = df[df["位置"].astype(str).str.strip() == position_str.strip()]
    if row.empty:
        return None
    return row.iloc[0]["值"]


def replace_word_with_values(doc, values, df):
    """
    用 values["规格型号"] 和 df["值"] 对比，如果有多个候选，
    则用 values["编码"] 在同一行内辅助定位。
    返回 modified_positions: set，记录所有成功修改的位置。
    """
    modified_positions = set()
    if values.empty or df.empty:
        return modified_positions

    # 一次性标准化，避免在循环中反复做 astype/replace/filter
    df_fast = df[["表格编号", "位置", "值"]].copy()
    df_fast["表格编号"] = pd.to_numeric(df_fast["表格编号"], errors="coerce").fillna(0).astype(int)
    df_fast["位置_norm"] = df_fast["位置"].astype(str).str.strip()
    df_fast["值_norm"] = df_fast["值"].astype(str).str.strip()
    df_fast["值_spec_norm"] = df_fast["值_norm"].str.replace(r"[\r\n]+", " ", regex=True).str.strip()

    code_lookup = {}
    row_spec_lookup = defaultdict(list)

    for table_no, pos_norm, val_norm, spec_norm in df_fast[
        ["表格编号", "位置_norm", "值_norm", "值_spec_norm"]
    ].itertuples(index=False, name=None):
        # 与旧逻辑一致：编码命中时默认取第一条
        if val_norm not in code_lookup:
            code_lookup[val_norm] = (int(table_no), pos_norm)

        pos_match = POSITION_RE.match(pos_norm)
        if not pos_match:
            continue

        row_index = int(pos_match.group(2))
        row_spec_lookup[(int(table_no), row_index, spec_norm)].append(pos_norm)

    for code_raw, k3_raw, spec_raw in values[["编码", "K3型号", "规格型号"]].itertuples(index=False, name=None):
        code = str(code_raw).strip()
        spec = str(spec_raw).strip()
        k3_val = str(k3_raw).strip()

        # 跳过特殊编码
        if "3.02.02." in code:
            print(f"跳过编码 {code}（规则：包含 '3.02.02.'）")
            continue

        spec_norm = LINE_BREAK_RE.sub(" ", spec).strip()
        code_hit = code_lookup.get(code)
        if not code_hit:
            print(f"未找到编码 '{code}' 的匹配位置，跳过")
            continue

        table_no, code_pos = code_hit
        match = POSITION_RE.match(code_pos)
        if not match:
            print(f"位置格式错误: {code_pos}")
            continue

        row_index = int(match.group(2))
        row_positions = row_spec_lookup.get((table_no, row_index, spec_norm), [])
        if not row_positions:
            print(f"未在同一行找到规格型号 '{spec}'，编码 {code}")
            continue

        for position_str in row_positions:
            try:
                if write_word_by_position_stable(doc, position_str, k3_val):
                    modified_positions.add(position_str)
                    print(f"已替换 编码 {code} 的规格型号 '{spec}' → '{k3_val}'，位置: {position_str}")
            except Exception as cell_error:
                print(f"修改失败: 编码 {code}, 位置 {position_str}, 错误: {str(cell_error)}")

    return modified_positions


def write_word_by_position_stable(doc, position_str, new_value):
    """通过 'row[表格编号][行][列]' 位置标识修改 Word 表格"""
    match = POSITION_RE.match(position_str)
    if not match:
        raise ValueError(f"位置格式错误: {position_str}")

    table_index = int(match.group(1))  # 表格编号（1-based）
    row = int(match.group(2))
    col = int(match.group(3))
    return write_word_cell_stable(doc, table_index, row, col, new_value)


def write_word_cell_stable(doc, table_index, row, col, new_value, max_retries=3):
    """更稳定的Word单元格修改函数，带重试机制。table_index为1-based表格编号。"""
    for attempt in range(max_retries):
        try:
            # 首次直接写，失败后才退避等待，减少大量固定等待时间。
            if attempt > 0:
                time.sleep(0.2 * attempt)
            table = doc.Tables(table_index)  # 1-based
            cell = table.Cell(row + 1, col + 1)  # 行列0-based转1-based
            cell.Range.Text = str(new_value)
            print(f"成功修改 表格{table_index} 单元格[{row}][{col}] 为: {new_value} (尝试 {attempt + 1})")
            return True
        except Exception as e:
            print(f"修改 表格{table_index} 单元格[{row}][{col}] 尝试 {attempt + 1} 失败: {str(e)}")
            if attempt == max_retries - 1:
                print(f"单元格 [{row}][{col}] 修改失败，已达到最大重试次数")
                return False
    return False


def replace_parenthesized_number(doc):
    """
    扫描文档中所有 "(X)"（X为纯数字），如果最高频的X出现次数 >= 10，
    则全部替换为 "(X+1)"。支持正文、页眉页脚、艺术字（Shapes/VML）。
    返回 X+1 的值（int），如果不满足条件则返回 None。
    """
    wdReplaceAll = 2

    all_text = doc.Content.Text
    matches = re.findall(r"\((\d+)\)", all_text)

    if not matches:
        print("未在文档中找到任何 (X) 模式")
        return None

    counter = Counter(matches)
    most_common_x, count = counter.most_common(1)[0]

    if count < 10:
        print(f"(X) 模式出现次数不足 ({count} < 10)，跳过替换")
        return None

    x_val = int(most_common_x)
    new_x_val = x_val + 1

    replace_str = f"({new_x_val})"
    replaced_count = 0

    # 找到所有 <= x_val 的可能版本号。
    # 由于正文 Content.Text 可能无法读取到只存在于艺术字内的旧版本号（如 (2)），
    # 最稳妥的方法是直接遍历从 0 到 x_val 的所有数字进行替换。
    targets = list(range(0, x_val + 1))

    def execute_replace_on_range(rng, search_str):
        """对指定 Range 执行查找替换，使用 wdFindStop + 循环确保替换所有"""
        nonlocal replaced_count
        rng.Find.ClearFormatting()
        rng.Find.Replacement.ClearFormatting()
        while True:
            # 使用 Wrap=0 (wdFindStop) 防止循环回绕
            result = rng.Find.Execute(
                search_str, False, False, False, False, False,
                True, 0, False, replace_str, wdReplaceAll
            )
            if not result:
                break
            replaced_count += 1

    # 3. 替换 Shapes 中的艺术字（包括 VML 和 TextEffect）
    def replace_in_shapes(shapes, search_str):
        nonlocal replaced_count
        for shape in shapes:
            # 尝试 TextEffect.Text（标准艺术字 Type=15）
            try:
                te_text = shape.TextEffect.Text
                if te_text and search_str in te_text:
                    shape.TextEffect.Text = te_text.replace(search_str, replace_str)
                    replaced_count += 1
                    print(f"  已替换艺术字 TextEffect: '{te_text}' → '{shape.TextEffect.Text}'")
            except Exception:
                pass
            # 尝试 TextFrame（文本框等）
            try:
                if shape.HasTextFrame:
                    if shape.TextFrame.HasText:
                        execute_replace_on_range(shape.TextFrame.TextRange, search_str)
            except Exception:
                pass
            # 递归处理组合形状
            try:
                if shape.Type == 6:  # msoGroup
                    replace_in_shapes(shape.GroupItems, search_str)
            except Exception:
                pass

    for target_val in targets:
        search_str = f"({target_val})"
        print(f"正在全局替换: {search_str} → {replace_str} ...")

        # 1. 替换正文（doc.Content 覆盖整个主文档故事，包括表格内文本）
        execute_replace_on_range(doc.Content, search_str)

        # 2. 替换所有 StoryRanges（页眉、页脚、脚注、尾注、文本框等）
        for story in doc.StoryRanges:
            execute_replace_on_range(story, search_str)
            # 遍历链式 StoryRange（如多节页眉）
            while True:
                try:
                    next_story = story.NextStoryRange
                    if next_story is None:
                        break
                    story = next_story
                    execute_replace_on_range(story, search_str)
                except Exception:
                    break

        # 4. 主文档浮动 Shapes
        replace_in_shapes(doc.Shapes, search_str)

        # 5. InlineShapes（内嵌形状）
        for i in range(1, doc.InlineShapes.Count + 1):
            try:
                ishape = doc.InlineShapes(i)
                try:
                    te_text = ishape.TextEffect.Text
                    if te_text and search_str in te_text:
                        ishape.TextEffect.Text = te_text.replace(search_str, replace_str)
                        replaced_count += 1
                        print(f"  已替换内嵌艺术字: '{te_text}' → '{ishape.TextEffect.Text}'")
                except Exception:
                    pass
            except Exception:
                pass

        # 6. 各节页眉页脚中的 Shapes
        for sec_idx in range(1, doc.Sections.Count + 1):
            section = doc.Sections(sec_idx)
            for hf_type in (1, 2, 3):
                try:
                    replace_in_shapes(section.Headers(hf_type).Shapes, search_str)
                except Exception:
                    pass
                try:
                    replace_in_shapes(section.Footers(hf_type).Shapes, search_str)
                except Exception:
                    pass

        # 7. 遍历所有表格单元格内的 InlineShapes（VML 艺术字嵌在单元格中）
        for t_idx in range(1, doc.Tables.Count + 1):
            try:
                table = doc.Tables(t_idx)
                for r in range(1, table.Rows.Count + 1):
                    for c in range(1, table.Columns.Count + 1):
                        try:
                            cell_range = table.Cell(r, c).Range
                            for i in range(1, cell_range.InlineShapes.Count + 1):
                                try:
                                    ishape = cell_range.InlineShapes(i)
                                    te_text = ishape.TextEffect.Text
                                    if te_text and search_str in te_text:
                                        ishape.TextEffect.Text = te_text.replace(search_str, replace_str)
                                        replaced_count += 1
                                        print(f"  已替换表格{t_idx}单元格内艺术字: '{te_text}'")
                                except Exception:
                                    pass
                            # 单元格内浮动 Shapes
                            try:
                                sr = cell_range.ShapeRange
                                for i in range(1, sr.Count + 1):
                                    try:
                                        te_text = sr(i).TextEffect.Text
                                        if te_text and search_str in te_text:
                                            sr(i).TextEffect.Text = te_text.replace(search_str, replace_str)
                                            replaced_count += 1
                                            print(f"  已替换表格{t_idx}单元格内浮动艺术字: '{te_text}'")
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        except Exception:
                            pass
            except Exception:
                pass

    print(f"全局版本号替换完成: 统一替换为 {replace_str}（共执行 {replaced_count} 次替换）")
    return new_x_val


def parse_user_patterns(user_input: str):
    """
    解析用户输入的编码模式，返回编译后的正则表达式列表。
    支持完整输入 (如 5.01.01.00635) 和不完整输入 (如 5.01.01.)。
    多个模式用空格或逗号分隔。
    """
    patterns = []
    parts = re.split(r'[,，\s]+', user_input.strip())
    for part in parts:
        if not part:
            continue
        # 完整格式: X.XX.XX.XXXXX
        if re.fullmatch(r"\d+\.\d{2}\.\d{2}\.\d{5}", part):
            patterns.append(re.compile(re.escape(part)))
        # 不完整格式: X.XX.XX.
        elif re.fullmatch(r"\d+\.\d{2}\.\d{2}\.", part):
            patterns.append(re.compile(re.escape(part) + r"\d{5}"))
        else:
            print(f"警告: 输入格式不符合 'X.XX.XX.XXXXX' 规则，原样匹配: {part}")
            patterns.append(re.compile(re.escape(part)))
    return patterns


def find_matching_cells(df, patterns):
    """在 DataFrame 中按用户模式匹配单元格值（A 数据）"""
    matched_rows = []
    for _, row in df.iterrows():
        val = str(row["值"]).strip()
        for pat in patterns:
            if pat.search(val):
                matched_rows.append(row)
                break
    return matched_rows


def find_change_mark_and_fill(doc, df, table_index, circled_symbol, position_value_map=None, change_mark_cache=None):
    """
    在指定表格中查找"更改标记"，在其下方4行中找到合适的位置填写。
    填写内容: 序号符号 | 1 | D250767 | 自己 | 今天日期
    只能在这四个单元格写，如果占满，覆盖最小的序号所在的行。
    """
    t_df = None
    cm_pos = None

    if change_mark_cache is not None:
        cm_pos = change_mark_cache.get(int(table_index))

    if cm_pos is None:
        t_df = df[df["表格编号"].astype(int) == int(table_index)]
        change_mark_rows = t_df[t_df["值"].astype(str).str.contains("更改标记", na=False)]
        if change_mark_rows.empty:
            print(f"表格 {table_index} 中未找到'更改标记'")
            return False
        cm_pos = str(change_mark_rows.iloc[0]["位置"]).strip()
        if change_mark_cache is not None:
            change_mark_cache[int(table_index)] = cm_pos

    match = POSITION_RE.match(cm_pos)
    if not match:
        return False

    t_idx = int(match.group(1))
    cm_r = int(match.group(2))
    cm_c = int(match.group(3))

    # C 数据候选: 更改标记下方4行，同列
    target_cells = []
    for r in range(cm_r + 1, cm_r + 5):
        pos_str = f"row[{t_idx}][{r}][{cm_c}]"
        if t_df is None:
            t_df = df[df["表格编号"].astype(int) == int(table_index)]
        val = get_value_from_df(t_df, t_idx, pos_str, position_value_map=position_value_map)
        target_cells.append({
            "pos": pos_str,
            "r": r,
            "val": str(val).strip() if val is not None else ""
        })

    # 寻找填入目标: 1.空单元格 2.全满→覆盖最小序号
    target_r = -1
    for cell in target_cells:
        if cell["val"] == "":
            target_r = cell["r"]
            break

    if target_r == -1:
        # 全满了，寻找圈数最小的
        min_val = 999
        min_r = -1
        for cell in target_cells:
            c_val = get_circle_num_val(cell["val"])
            if 0 < c_val < min_val:
                min_val = c_val
                min_r = cell["r"]

        if min_r != -1:
            target_r = min_r
            print(f"四个单元格已满，覆盖序号最小({min_val})的行：{target_r}")
        else:
            target_r = target_cells[0]["r"]

    # 执行填充
    today_str = datetime.today().strftime("%Y.%m.%d")

    write_word_by_position_stable(doc, f"row[{t_idx}][{target_r}][{cm_c}]", circled_symbol)
    write_word_by_position_stable(doc, f"row[{t_idx}][{target_r}][{cm_c+1}]", "1")
    write_word_by_position_stable(doc, f"row[{t_idx}][{target_r}][{cm_c+2}]", "D260474")
    write_word_by_position_stable(doc, f"row[{t_idx}][{target_r}][{cm_c+3}]", "覃文涛")
    write_word_by_position_stable(doc, f"row[{t_idx}][{target_r}][{cm_c+4}]", today_str)

    print(f"已在表格 {table_index} 填写更改标记：{circled_symbol}, 1, D260474, 覃文涛, {today_str}")
    return True


def process_user_match_and_change_mark(doc, df, modified_positions, user_patterns, new_x_val):
    """
    主协调函数：A数据匹配 → 行修改检查 → B数据追加序号 → 更改标记填写。
    """
    if not user_patterns:
        return

    matched_cells = find_matching_cells(df, user_patterns)
    if not matched_cells:
        print("未匹配到任何用户输入的数据(A数据)")
        return

    modified_row_keys = set()
    for mod_pos in modified_positions:
        m_match = POSITION_RE.match(str(mod_pos))
        if m_match:
            modified_row_keys.add((int(m_match.group(1)), int(m_match.group(2))))

    position_value_map = build_position_value_map(df)
    change_mark_cache = {}

    for a_row in matched_cells:
        a_pos = str(a_row["位置"])
        a_match = POSITION_RE.match(a_pos)
        if not a_match:
            continue

        t_idx = int(a_match.group(1))
        a_r = int(a_match.group(2))
        a_c = int(a_match.group(3))

        # 检查 A 数据所在的行是否有被 write_word_by_position_stable 修改
        if (t_idx, a_r) not in modified_row_keys:
            print(f"A数据所在行未被修改，跳过。位置: {a_pos}，值: {a_row['值']}")
            continue

        # B 数据: A 数据左移2列
        b_c = a_c - 2
        if b_c < 0:
            print(f"B数据列号小于0，无法定位。A数据位置: {a_pos}")
            continue

        b_pos = f"row[{t_idx}][{a_r}][{b_c}]"

        # 生成序号符号
        if new_x_val is None:
            print("警告：未执行(X)版本替换，无法获取新版本号，跳过更改标记填写。")
            continue

        if new_x_val > 10:
            raise ValueError(f"新版本号 {new_x_val} 大于 10，无法生成序号符号！")

        circled_symbol = num_to_circled(new_x_val)

        # B 数据追加序号符号
        b_val = str(get_value_from_df(df, t_idx, b_pos, position_value_map=position_value_map) or "").strip()
        new_b_val = b_val + circled_symbol

        try:
            write_word_by_position_stable(doc, b_pos, new_b_val)
            position_value_map[b_pos] = new_b_val
            print(f"已修改 B 数据，追加符号 '{circled_symbol}'。位置: {b_pos}，内容: '{b_val}' → '{new_b_val}'")
        except Exception as e:
            print(f"修改 B 数据失败: {b_pos}, 错误: {str(e)}")
            continue

        # 填写更改标记
        find_change_mark_and_fill(
            doc, df, t_idx, circled_symbol,
            position_value_map=position_value_map,
            change_mark_cache=change_mark_cache
        )


# ===== 主程序 =====
if __name__ == "__main__":
    current_dir = os.getcwd()
    output_dir = current_dir

    # 获取用户输入（一次性，适用于所有文件）
    user_input = input(
        "请输入要匹配的编码模式 (如 5.01.01.00635 或 5.01.01.，多个用空格/逗号分隔)，"
        "如果不使用此功能直接回车：\n"
    )
    user_patterns = parse_user_patterns(user_input)

    xlsx_files = [
        name for name in os.listdir(current_dir)
        if name.endswith(".xlsx") and not name.startswith("~$")
    ]
    if not xlsx_files:
        print("当前目录未找到可处理的xlsx文件。")

    word = None
    excel = None
    try:
        pythoncom.CoInitialize()

        # Word/Excel 整个批次只创建一次，减少 COM 启动与销毁开销。
        word = win32.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False

        excel = Dispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        for filename in xlsx_files:
            file_path = os.path.join(current_dir, filename)
            print(f"\n{'='*60}")
            print(f"处理文件: {filename}")
            print(f"{'='*60}")

            doc = None
            close_with_save = True
            try:
                # 从xlsx文件中获取不匹配项
                values = read_mismatch_block_win32(file_path, excel_app=excel)

                # 推导对应的Word文件名
                new_file = filename.replace("_校对结果.xlsx", ".doc")
                print(f"对应Word文件: {new_file}")

                abs_file_path = os.path.abspath(new_file)
                if not os.path.exists(abs_file_path):
                    raise FileNotFoundError(f"文件不存在: {abs_file_path}")

                try:
                    with open(abs_file_path, "r+b"):
                        pass
                except PermissionError:
                    print(f"警告: 文件可能被其他程序占用: {abs_file_path}")

                doc = word.Documents.Open(abs_file_path)

                # ===== 步骤1: 替换 (X) 版本号，获取 X+1 =====
                new_x_val = None
                try:
                    new_x_val = replace_parenthesized_number(doc)
                except Exception as e:
                    print(f"替换 (X) 时出错: {str(e)}")

                if new_x_val is not None and new_x_val > 10:
                    print(f"错误: 文档 {new_file} 的新版本号 ({new_x_val}) 大于10，跳过此文件。")
                    close_with_save = False
                    continue

                # ===== 步骤2: 读取Word表格（三维位置）=====
                df = read_word_tables_from_doc(doc, include_page=False)

                # ===== 步骤3: 执行规格型号替换，记录修改位置 =====
                modified_positions = replace_word_with_values(doc, values, df)

                # ===== 步骤4: 处理用户匹配 + B数据 + 更改标记 =====
                if user_patterns:
                    try:
                        # 重新读取表格，因为步骤3可能改变了内容
                        df_updated = read_word_tables_from_doc(doc, include_page=False)
                        process_user_match_and_change_mark(
                            doc, df_updated, modified_positions,
                            user_patterns, new_x_val
                        )
                    except ValueError as ve:
                        print(f"错误: {str(ve)}，跳过此文件后续处理。")

                # ===== 保存文档 =====
                try:
                    doc.Save()
                    print("文档保存成功")
                except Exception as save_error:
                    print(f"保存文档时出错: {str(save_error)}")
                    try:
                        doc.Save()
                        print("重试保存成功")
                    except Exception as retry_save_error:
                        print(f"重试保存失败: {str(retry_save_error)}")
                        try:
                            _, ext = os.path.splitext(abs_file_path)
                            file_format = 12 if ext.lower() == ".docx" else 0
                            doc.SaveAs(abs_file_path, FileFormat=file_format)
                            print("文档强制保存成功")
                        except Exception as force_save_error:
                            print(f"强制保存也失败: {str(force_save_error)}")
                            try:
                                root, ext = os.path.splitext(abs_file_path)
                                backup_path = f"{root}_backup{ext}"
                                file_format = 12 if ext.lower() == ".docx" else 0
                                doc.SaveAs(backup_path, FileFormat=file_format)
                                print(f"文档已另存为备份: {backup_path}")
                            except Exception as backup_error:
                                print(f"备份保存也失败: {str(backup_error)}")

            except Exception as e:
                print(f"处理Word文档时出错: {str(e)}")
                print(f"错误类型: {type(e).__name__}")
            finally:
                if doc is not None:
                    try:
                        doc.Close(SaveChanges=close_with_save)
                        print("文档关闭成功")
                    except Exception as close_error:
                        print(f"关闭文档时出错: {str(close_error)}")
                        try:
                            doc.Close(SaveChanges=False)
                            print("文档强制关闭成功")
                        except Exception:
                            print("文档强制关闭也失败")

            print(f"{filename} 处理完成")

    finally:
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
