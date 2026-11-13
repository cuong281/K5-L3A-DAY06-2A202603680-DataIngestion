# Day 06 · Data Ingestion Engineering

## Bài làm: Đặng Đức Cương (2A202603680): cách chạy lại

**Corpus:** tài liệu AVNUC *"Khái niệm chuyển đổi số và CĐS trong GDĐH"*, 45 trang, 33 trang được tính.
**Embedding:** `BAAI/bge-m3`, chạy CPU. **Vector store:** PostgreSQL 16 + pgvector 0.8.7, cosine.
**Chiến lược:** A fixed 500/50 · B theo đoạn ≤1000 · C = B + filter `article_id` (chiến lược được chọn).
Báo cáo: [report/individual/2A202603680_DangDucCuong.md](report/individual/2A202603680_DangDucCuong.md).

```powershell
cd starter
python -m venv .venv; .venv\Scripts\Activate.ps1
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu   # torch 2.15.0+cpu
python -m pip install -r requirements.txt
Copy-Item .env.example .env          # rồi đặt EMBEDDING_MODEL=BAAI/bge-m3
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py

# PDF KHÔNG có trong repo (bìa ghi "lưu hành nội bộ"). Tải về starter/data/ theo URL trong data/manifest.json,
# sau đó kiểm tra SHA-256 khớp với manifest (pipeline cũng tự kiểm tra và từ chối chạy nếu lệch).
python -m scripts.build_manifest      # -> data/manifest.json (đếm trang, kiểm tra 7 bài)
python -m scripts.verify_benchmark    # -> results/benchmark_verification.json (evidence + hash benchmark)
python -m src.run --split dev         # ingest A/B, chạy dev, chọn chiến lược theo luật đã chốt
python -m src.run --split test        # chỉ chạy được sau khi đã có results/selection.json
python -m scripts.check_reingest      # chứng minh nạp lại không trùng + xử lý tài liệu đổi
python -m scripts.make_audit_sheets   # tạo các bảng chấm tay trong results/audit/
python -m scripts.summarize_audit     # sau khi đã chấm tay -> results/audit_summary.json
```

| Thư mục / tệp | Nội dung |
|---|---|
| `data/manifest.json` | Nguồn, quyền, SHA-256, số ký tự từng trang, quy tắc tính trang, 7 giá trị `article_id` |
| `benchmark/` | 22 câu hỏi (16 dev / 6 test), gold evidence, tiêu chí chọn chiến lược |
| `starter/src/` | `ingestion`, `chunking`, `embeddings`, `store`, `evaluation`, `run`, `corpus` |
| `results/` | Metrics, trace top-3, lịch sử ingest, selection, kiểm tra nạp lại, nhãn audit, log |
| `artifacts/experiment_log.csv` | Cấu hình, giả thuyết và Hit@1/Hit@3 của A/B/C |

---

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
