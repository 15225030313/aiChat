"""
RAG 第一步：把文档变成纯文本（对应学习路线第 6 周周一/周三）

整个 RAG 的源头就是把「一份文件」变成「一串干净的字符串」，
本文件目前只实现 PDF 提取 + 清洗；Word/TXT 在周二补，分片在周四写。
"""

import pymupdf


def extract_pdf_text(file_path: str) -> str:
    """提取 PDF 全部文字：逐页取文本后用换行拼接"""
    parts: list[str] = []
    with pymupdf.open(file_path) as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n".join(parts)


def clean_text(raw: str) -> str:
    """基础清洗：统一换行符、去掉多余空行和行尾空格"""
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned = [line.strip() for line in lines]
    # 连续空行压成一个
    result: list[str] = []
    for line in cleaned:
        if line or (result and result[-1]):
            result.append(line)
    return "\n".join(result).strip()


def parse_file(file_path: str) -> str:
    """统一入口：按后缀分发（目前只支持 PDF，Word/TXT 随后补充）"""
    suffix = file_path.rsplit(".", 1)[-1].lower()
    if suffix == "pdf":
        return clean_text(extract_pdf_text(file_path))
    raise ValueError(f"暂不支持的格式: .{suffix}（周二/周三的任务）")


# ===== 分片（第 6 周周四任务：RAG 检索效果的第一决定因素）=====

CHUNK_SIZE = 500   # 每片目标长度（字符）
CHUNK_OVERLAP = 100  # 相邻片重叠长度：防止关键内容恰好被切断


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    滑动窗口分片：每片 chunk_size 字，下一片往回退 overlap 字再切。

    例：全文 [0..1500]，chunk_size=500, overlap=100 →
    片1=[0,500) 片2=[400,900) 片3=[800,1300) 片4=[1200,1500]
    边界处的句子在两片里都完整存在，检索时至少一片可用。
    """
    text = text.strip()
    if not text:
        return []

    step = chunk_size - overlap  # 每片实际向前推进的距离
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start += step
    return chunks


if __name__ == "__main__":
    text = parse_file("test_data/公司报销制度.pdf")
    print(f"=== 提取完成，共 {len(text)} 个字符 ===\n")
    print(text[:300], "\n...")
    print("\n=== 清洗检查：空行数 =", text.count("\n\n"), "（应为 0 或极少） ===")
