# Báo cáo cá nhân — Day 6

**Học viên:** Đặng Đức Cương · **MSSV:** 2A202603680 · **Lớp:** L3A
**Thời điểm chạy:** 13/11/2026 (+07:00): dev lần 1 bắt đầu lúc 12:20:53, chọn chiến lược lúc 12:23:55, test bắt đầu lúc 12:25:58 (một lần duy nhất). Chi tiết trong `results/metrics_*.json` và `results/selection.json`.


## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang.**
  - Tài liệu: *"Khái niệm chuyển đổi số và chuyển đổi số trong giáo dục đại học"* của Hiệp hội các trường ĐH, CĐ Việt Nam (28/7/2022), tiếng Việt, tổng hợp 7 bài viết. URL: avnuc.vn, xem [data/manifest.json](../../data/manifest.json).
  - Quyền: bìa ghi *"lưu hành nội bộ"* và tài liệu gồm bài của bên thứ ba. Vì vậy **PDF không được commit**; repo chứa URL và SHA-256 (`817038a2…`) để tải lại đúng bản.
  - Để người chấm kiểm chứng kết quả mà không cần chạy lại, `results/traces_*.jsonl` và `results/audit/` giữ **toàn văn các chunk được truy xuất và chấm**: 119 đoạn trên 34/45 trang, khoảng **43% nội dung chữ** của tài liệu.
  - Tác giả chọn giữ các file này vì tài liệu đang được đăng công khai trên avnuc.vn. Nếu giảng viên yêu cầu, có thể xóa chúng khỏi repo và tạo lại bằng `python -m src.run` sau khi tải PDF theo manifest (SUBMISSION.md cho phép cách này).
  - Số trang: 45 trang vật lý, **33 trang được tính**, tổng 72.582 ký tự (không tính khoảng trắng).
  - Quy tắc tính trang (thực thi trong `scripts/build_manifest.py`): bỏ trang bìa; bỏ trang mà phần tài liệu tham khảo chiếm ≥50%; bỏ trang có dưới 1.500 ký tự sau chuẩn hóa. Theo quy tắc này, 12 trang bị loại: 1, 10, 20, 25, 27–29, 35, 40–42, 45.
- **Chuẩn hóa, lỗi và giới hạn.**
  - Đọc PDF bằng PyMuPDF 2.1, chỉ đọc lớp chữ, không OCR. Text được chuẩn hóa NFC, gộp khoảng trắng, bỏ dấu cách trước dấu câu, bỏ số trang; ranh giới đoạn (block) và dòng vẫn được giữ.
  - Tôi đã thử `pypdf` trước. Nó tách sai khoảng 0,8% token tiếng Việt (ví dụ `nghiệ p`), còn PyMuPDF không tách sai token nào (so với `pdftotext` làm mốc).
  - Không có trang nào rỗng. 10 trang có ảnh (1, 3, 25, 29, 37–42): chữ nằm trong bảng/hình là ảnh thì bị mất, và tôi đã ghi warning cho từng trang trong manifest.
  - Chunk không vượt qua ranh giới trang, nên câu nào kéo dài sang trang sau sẽ bị cắt. Điều này đúng với mọi chiến lược.
- **Embedding, vector store, metric, lệnh chạy và chi phí.**
  - Embedding: `BAAI/bge-m3` dạng dense, **1024 chiều**, revision `5617a9f6…`, chạy local trên CPU bằng sentence-transformers 6.3.0 và torch 2.15.0+cpu. Vector được chuẩn hóa L2; query không thêm instruction và được encode giống document.
  - Vector store: PostgreSQL 16.16 + pgvector 0.8.7 (Docker). Metric cosine (`<=>`), **tìm kiếm chính xác (exact search), không dùng index ANN**.
  - Lệnh chạy: xem [README.md](../../README.md), mục "Bài làm".
  - Chi phí: **0 USD**.
  - Thời gian: load model khoảng 9–11 giây; embed A (261 chunk) 89,0 giây; embed B (185 chunk) 78,4 giây; truy vấn trung bình 22–27 ms/câu (đo trên dev, đã tính cả thời gian mở kết nối).
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn.**
  - Mỗi chunk có `document_id`, `source` (URL), `page` (trang vật lý), `char_start/char_end`.
  - Trường lọc: `article_id` (chuỗi, 7 giá trị) cùng `article_title`. Giá trị được lấy từ tiêu đề và dòng nguồn/tác giả in ở trang đầu mỗi bài. `build_manifest.py` tự kiểm tra marker trên trang đó, nên không có giá trị nào do đoán.
  - Lý do chọn: nhiều chủ đề lặp lại ở nhiều bài với nội dung khác nhau (định nghĩa CĐS, CNTT so với CĐS, "thách thức lớn nhất"). Khi người dùng đã chọn bài, `article_id` giúp thu hẹp đúng phạm vi.

## Cấu hình và benchmark

- **A / B / C (tham số cụ thể; khác biệt duy nhất giữa B và C):**
  - **A:** cửa sổ cố định 500 ký tự, overlap 50, trên text phẳng của từng trang; không lọc.
  - **B:** gom nguyên đoạn đến tối đa 1.000 ký tự; heading hoặc mục đánh số (`2.`, `II.`, `B3.`) luôn mở chunk mới; đoạn dài quá giới hạn được tách theo câu; không lọc.
  - **C:** dùng **chính index của B** (cùng chunk, cùng vector) và chỉ thêm `WHERE article_id = …` khi câu hỏi có filter. B và C **chỉ khác nhau ở filter**; A và B chỉ khác nhau ở cách chunk.
  - Cả ba dùng chung corpus, model, store, metric, top-k = 3 và benchmark.
- **≥20 câu: phân chia dev/test, câu filter và cách kiểm chứng evidence.**
  - 22 câu, chia **16 dev / 6 test** trước khi chạy. Gồm 7 câu trực tiếp, 6 câu diễn đạt lại, 4 câu điều kiện và 5 câu có filter (3 dev, 2 test). Bộ câu phủ cả 7 bài.
  - Filter là input giả định do người dùng chọn trước (`filter_context`); câu hỏi không chứa tên nguồn.
  - `scripts/verify_benchmark.py` dùng cùng hàm chuẩn hóa của pipeline: 23/23 evidence nằm đúng trang gold, không evidence nào trùng ở trang khác, giá trị filter khớp với bài của trang gold.
  - Hash của `questions.json` (`6516e04d…`) được ghi lúc kiểm chứng và **được kiểm tra lại trong mỗi lần chạy** (pipeline từ chối chạy nếu hash đổi).
  - Quy ước: evidence là đoạn ngắn nhất đủ hỗ trợ toàn bộ đáp án; q16 có 2 trang gold hợp lệ.
- **Tiêu chí chọn chiến lược, chốt trước khi xem test** (trong `benchmark/README.md`, cài đặt trong `src/run.py`): (1) Hit@3 dev cao nhất; (2) các chiến lược kém tốt nhất ≤1 câu được so tiếp bằng Hit@1 dev; (3) nếu vẫn hòa: ít chunk hơn, rồi không cần filter hơn. `src.run --split test` **bị chặn cho đến khi có `results/selection.json`**.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 9/16 | 12/16 | 261 | embed 89,0 s | 0 |
| A | test | 2/6 | 4/6 | 261 | (dùng lại index) | 0 |
| B | dev | 13/16 | 15/16 | 185 | embed 78,4 s | 0 |
| B | test | 3/6 | 4/6 | 185 | (dùng lại index) | 0 |
| **C** | dev | **15/16** | **15/16** | 185 (index B) | 0 s thêm | 0 |
| **C** | test | **3/6** | **6/6** | 185 (index B) | 0 s thêm | 0 |

Thống kê chunk (`results/metrics_dev.json`):
- A: độ dài 54–500 ký tự (trung vị 500), tổng 30.650 token.
- B: độ dài 35–998 ký tự (trung vị 612), tổng 27.667 token.

Nạp lại không trùng (`results/ingest_runs.jsonl`, `results/reingest_check.json`):
- Lần chạy thứ hai embed 0 chunk, ghi/xóa 0 dòng; số dòng bằng số `chunk_id` phân biệt (261 và 185); top-3 giống hệt lần 1 ở cả 48 truy vấn.
- Khi tài liệu đổi (thử nghiệm với embedding thật): sửa 1 chunk thì chỉ chunk đó được embed lại và cập nhật; bỏ 1 chunk thì chunk cũ bị xóa.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | **0,0** (n=10; 10 nhãn 0) | 18/18 | 0/2 (A không lọc) | 0: 1 · 1: 1 · 2: 4 → **1,50**; proxy Hit@3 = 4/6 |
| B | **2,0** (n=10; 10 nhãn 2) | 18/18 | 0/2 (B không lọc) | 0: 2 · 1: 0 · 2: 4 → **1,33**; proxy Hit@3 = 4/6 |
| C | **2,0** (dùng chung chunk với B) | 18/18 | **2/2** (dev 3/3) | 0: 0 · 1: 0 · 2: 6 → **2,00**; proxy Hit@3 = 6/6 |

Nguồn số liệu: `results/audit_summary.json`, sinh bằng `scripts/summarize_audit.py` từ các nhãn trong `results/audit/*.csv`.

- **Coherence:** tiêu chí tác giả áp dụng thống nhất là chunk **bị cắt giữa từ hoặc giữa câu ở ranh giới thì tính 0**, vì đọc riêng chunk không nắm được trọn ý. Cả 10 chunk của A đều mở đầu hoặc kết thúc giữa từ (ví dụ `"u tư…"`, `"…quy t"`, `"hứ ba,…"`), nên đều 0. Cả 10 chunk của B đều bắt đầu và kết thúc trọn câu hoặc trọn mục, nên đều 2. Đây là thang nghiêm; nếu tính "hiểu một phần" là 1 thì A sẽ ở khoảng 1/2, nhưng thứ hạng A < B không đổi.
- **Metadata:** 54/54 bản ghi đúng `source`, `page` và `article_id` khi đối chiếu với PDF; không có lỗi. Kiểm tra tự động cũng cho kết quả tương tự (text khớp trang, `article_id` khớp manifest).
  - Trường hữu ích: `page` cùng `article_id` giúp truy ngay về đúng trang và đúng bài, và cho phép lọc phạm vi trong C.
  - Hạn chế: `article_id` chỉ có ích khi người dùng biết trước bài cần hỏi. Ngoài ra `page` là trang vật lý, nên đoạn văn kéo dài sang trang sau sẽ bị tách thành hai chunk khác nhau.
- **Grounding:** chỉ đánh giá độ đủ của evidence truy xuất được, không phải câu trả lời LLM.
  - A mất điểm ở q17 (mức 0, không lấy được đoạn có 2 giai đoạn) và q22 (mức 1, chunk bị cắt ngay giữa câu định nghĩa, mất vế "vì mục đích… lợi ích người học").
  - B mất điểm ở đúng 2 câu có filter (q20, q21: mức 0, top-3 thuộc bài khác).
  - C đạt mức 2 ở cả 6 câu.

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- Trace: `results/traces_dev.jsonl` và `results/traces_test.jsonl`. Mỗi dòng có câu hỏi, filter, top-3 kèm chunk_id/text/score/metadata và các cờ đánh giá.
- Nhãn: `results/audit/`.
- Coherence: 10 vị trí được cố định **trước khi chấm**, là điểm giữa text của 10 trang được tính đầu tiên (trang 2–9, 11, 12). Với mỗi vị trí, lấy chunk của A và của B phủ vị trí đó.
- Metadata và grounding: cả 6 câu test × top-3 × 3 chiến lược.

## Phân tích và kết luận

- **So sánh A–B (đổi cách chunk).**
  - B hơn A ở dev (Hit@3 15 so với 12, Hit@1 13 so với 9) và dùng ít chunk hơn (185 so với 261, ít token hơn khoảng 10%).
  - Ở A có 3/16 câu dev bị **tách evidence**: top-3 chỉ chứa một phần evidence.
  - *Ví dụ lỗi 1, q02 (tr.3):* hai chunk của A ở rank 1 và 2 cùng nằm đúng trang 3, nhưng câu định nghĩa digitization bị chia đôi giữa hai cửa sổ 500 ký tự. B giữ nguyên đoạn đó nên trúng ở rank 1.
  - Tương tự ở q12 (tr.26) và q14 (tr.30) trên dev, và q22 (tr.34) trên test.
- **So sánh B–C (chỉ thêm filter).**
  - Ở câu không có filter, C cho kết quả trùng B. Toàn bộ khác biệt nằm ở các câu có filter: dev Hit@1 tăng từ 13 lên 15, test Hit@3 tăng từ 4 lên 6.
  - *Ví dụ lỗi 2, q20 (test, filter `a4_tiasang`):* B xếp hạng 1 đoạn "Khó khăn và thách thức lớn nhất…" của **Cẩm nang Bộ TT&TT (tr.13)**. Đoạn này cùng chủ đề nhưng khác bài và khác đáp án, nên B trượt top-3. C lọc theo bài Tia Sáng và tìm được evidence ở tr.26 (rank 2).
  - q21 cũng vậy: B kéo về các đoạn giáo dục trực tuyến của bài Tia Sáng và bài GDĐH số, còn C lấy đúng tr.15 của Cẩm nang.
- **Lỗi còn lại.**
  - q13 (dev; B và C): chunk giới thiệu "12 bước…" xếp trên chunk chứa bước 1. Đây là lỗi xếp hạng, không phải lỗi chunk.
  - q17 (test; A): cửa sổ trúng đúng trang 39 nhưng không chứa đoạn "2 giai đoạn đầu".
- **Nhãn thủ công củng cố kết quả tự động.**
  - Coherence: A 0,0/2, B 2,0/2. Chunk cố định cắt ngang từ và câu ở mọi ranh giới, đúng với nguyên nhân các lỗi tách evidence.
  - Grounding: C 2,00 > A 1,50 > B 1,33. Grounding của B thấp hơn A trên test vì 2 câu filter, nơi B (không lọc) bị kéo sang bài khác. Thứ tự này dựa trên 6 câu, nên chênh lệch giữa A và B chỉ tương đương khoảng 1 câu.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng.**
  - Chọn **C**. Luật đã chốt chạy tự động trên dev: B và C cùng Hit@3 15/16, C có Hit@1 cao hơn (15 so với 13).
  - Đánh đổi: C chỉ có lợi khi người dùng **thực sự cung cấp phạm vi bài**. Nếu filter sai thì C sẽ loại mất evidence đúng. Không có filter thì C giống hệt B.
  - Chunk theo đoạn phụ thuộc vào cấu trúc block của PDF; với PDF dàn trang kém (bảng hai cột, đoạn bị gộp) thì lợi thế của B sẽ giảm.
- **Hạn chế về dữ liệu, nhãn, test nhỏ và đo thời gian/chi phí.**
  - Test chỉ có 6 câu, mỗi câu tương đương 16,7 điểm %. Chênh 4/6 so với 6/6 đến từ 2 câu filter, nên **không suy rộng ra ngoài corpus này**.
  - Benchmark và nhãn do tác giả tự soạn và tự chấm (có nguy cơ thiên lệch). Câu filter được thiết kế ở các chủ đề trùng lặp nên có lợi cho C; điều này đã được nêu rõ trong `benchmark/README.md`.
  - Thời gian đo trên một máy CPU (AMD, Windows) trong một lần chạy, chưa lặp lại nhiều lần.
  - Nội dung trong ảnh bị bỏ qua.
- **Nếu làm lại hoặc mở rộng:**
  - Cho chunk B nối được qua ranh giới trang, ghi `page_start/page_end`.
  - Thử hybrid BM25 + dense (giữ nguyên chunk và filter), chọn tham số trên dev.
  - Mở rộng test lên 15–20 câu, có thêm câu filter ở các bài khác.
  - OCR các trang có bảng/hình ảnh.
  - Nhờ một người thứ hai chấm độc lập để đo mức độ đồng thuận giữa hai người chấm.

## Công cụ AI và cách kiểm tra

- Dùng Claude Code (Anthropic) để phân tích đề, viết code pipeline, soạn nháp benchmark và báo cáo.
- Cách kiểm tra:
  - Mọi số liệu trong báo cáo được đọc từ file kết quả của các lần chạy thật.
  - Evidence được kiểm tra tự động với text đã chuẩn hóa; tác giả đọc lại từng câu hỏi với PDF.
  - Nạp lại/tài liệu đổi được kiểm tra bằng `scripts/check_reingest.py`.
- Nhãn coherence, metadata và grounding (`results/audit/`): **tác giả chấm và quyết định từng nhãn**. Công cụ AI đã:
  - tạo file mẫu và các cột kiểm tra tự động;
  - giải thích thang 0/1/2, kèm một bảng nhãn tham khảo. Nhãn cuối cùng khác bảng này ở 9/38 nhãn coherence và grounding, tất cả nằm ở coherence của A (tác giả dùng thang nghiêm hơn);
  - kiểm tra chéo lý do của từng nhãn với nội dung chunk. Lần kiểm tra này phát hiện 1 lý do không khớp dữ liệu (A q22: chunk bị cắt nên sửa từ 2 thành 1) và 2 lý do diễn đạt sai bản chất (B q20, q21: "bộ lọc không hoạt động" được sửa thành "B không dùng filter theo thiết kế"). Tác giả đã sửa cả 3 chỗ.
- Người chấm là tác giả, nên có nguy cơ thiên lệch.
