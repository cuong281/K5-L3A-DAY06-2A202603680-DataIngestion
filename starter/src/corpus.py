"""Single source of truth for the corpus: where it comes from and how pages map to articles.

The PDF is a compilation of 7 articles; each starts on a new page and states its own
source/author in the text. ``article_id`` is the metadata filter field. Every value
below is copied from the document itself and ``marker`` must appear on ``start_page``
(checked by ``scripts/build_manifest.py``), so filter values are never guessed.
"""
from __future__ import annotations

from pathlib import Path

STARTER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = STARTER_DIR.parent

DOCUMENT_ID = "avnuc-cds-2022"
TITLE = "Khái niệm chuyển đổi số và chuyển đổi số trong giáo dục đại học (Tài liệu tham khảo)"
PUBLISHER = "Hiệp hội các trường Đại học, Cao đẳng Việt Nam (AVNUC)"
PUBLISHED_DATE = "2022-07-28"  # cover: "Hà Nội, ngày 28 tháng 7 năm 2022"
SOURCE_URL = "https://avnuc.vn/wp-content/uploads/2022/08/Khai-niem-CDS-va-CDS-trong-GD-DT.pdf"
LOCAL_PDF = STARTER_DIR / "data" / "Khai-niem-CDS-va-CDS-trong-GD-DT.pdf"
ACCESSED_AT = "2026-11-13"
LICENSE_OR_PERMISSION = (
    "Không có giấy phép mở. Bìa ghi 'TÀI LIỆU THAM KHẢO (lưu hành nội bộ)'; tài liệu tổng hợp "
    "bài viết của nhiều bên thứ ba. Tải công khai từ avnuc.vn và chỉ xử lý cục bộ cho mục đích "
    "học tập. KHÔNG phân phối lại PDF: file bị .gitignore. Repo chứa manifest, URL, SHA-256, evidence "
    "trong benchmark và toàn văn các chunk được truy xuất/chấm trong results/ (traces, audit) để người "
    "chấm kiểm chứng, khoảng 43% nội dung chữ của tài liệu; đây là quyết định của tác giả, xem báo cáo."
)

# (article_id, start_page, end_page, title as printed, source/author as printed, marker on start page)
ARTICLES: list[dict] = [
    {"article_id": "cover", "start_page": 1, "end_page": 1,
     "title": "Bìa", "source": "Hiệp hội các trường Đại học, Cao đẳng Việt Nam",
     "marker": "lưu hành nội bộ"},
    {"article_id": "a1_fsi", "start_page": 2, "end_page": 5,
     "title": "Chuyển đổi số là gì? Định nghĩa chuyển đổi số",
     "source": "Theo FSI; Tháng Mười Hai 26, 2020", "marker": "Theo FSI"},
    {"article_id": "a2_vietnamnet_qa", "start_page": 6, "end_page": 10,
     "title": "Bộ trưởng Bộ TT&TT Nguyễn Mạnh Hùng giải đáp những câu hỏi then chốt về chuyển đổi số",
     "source": "nguồn VietNamNet", "marker": "nguồn VietNamNet"},
    {"article_id": "a3_camnang_btttt", "start_page": 11, "end_page": 20,
     "title": "Cẩm nang về chuyển đổi số",
     "source": "Nguồn: Cục tin học hoá - Bộ Thông tin và Truyền thông; Oct 2, 2020",
     "marker": "Cục tin học hoá"},
    {"article_id": "a4_tiasang", "start_page": 21, "end_page": 27,
     "title": "Chuyển đổi số trong giáo dục: những thách thức và nguy cơ",
     "source": "Nguồn: Tạp chí Tia sáng - Đỗ Thị Ngọc Quyên", "marker": "Tạp chí Tia sáng"},
    {"article_id": "a5_blake_morgan", "start_page": 28, "end_page": 30,
     "title": "12 bước để chuyển đổi số thành công",
     "source": "Blake Morgan (khách mời blogger)", "marker": "Blake Morgan"},
    {"article_id": "a6_gddh_so", "start_page": 31, "end_page": 35,
     "title": "Về mô hình giáo dục đại học số",
     "source": "TSKH. Phạm Đỗ Nhật Tiến", "marker": "Phạm Đỗ Nhật Tiến"},
    {"article_id": "a7_khung_nang_luc_eu", "start_page": 36, "end_page": 45,
     "title": "Các khung năng lực số của Liên minh châu Âu và vài gợi ý cho Việt Nam để chuyển đổi số thành công",
     "source": "Lê Trung Nghĩa, Hiệp hội các trường ĐH, CĐ Việt Nam", "marker": "Lê Trung Nghĩa"},
]


def article_for_page(page: int) -> dict:
    """Return the article that contains a physical page (raises if unmapped)."""
    for article in ARTICLES:
        if article["start_page"] <= page <= article["end_page"]:
            return article
    raise ValueError(f"Page {page} is not mapped to any article")
