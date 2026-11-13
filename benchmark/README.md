# Benchmark: 22 câu hỏi trên corpus AVNUC CĐS

> **Trạng thái: ĐÃ DUYỆT.** Bộ câu hỏi do AI soạn nháp, script kiểm tra tự động; tác giả (Đặng Đức Cương) đã đọc lại.
>
> **Mốc thời gian (13/11/2026, +07:00):**
> - 12:17:34: chốt bộ câu hỏi, ghi `questions_sha256 = 6516e04d…` trong `results/benchmark_verification.json`.
> - 12:20:53: chạy retrieval lần đầu (dev). Mỗi lần chạy đều kiểm tra lại hash này và từ chối chạy nếu hash khác.
> - 12:23:55: chọn chiến lược trên dev.
> - 12:25:58: chạy test (một lần).
> - Sau đó: tác giả đọc lại bộ câu hỏi, **không sửa câu nào**. Hash hiện tại vẫn là `6516e04d…`.
>
> Repo được commit một lần vào cuối, nên mốc "chốt trước khi chạy" được chứng minh bằng hash và timestamp nói trên, không bằng commit riêng.

## Tệp

| Tệp | Nội dung |
|---|---|
| [questions.json](questions.json) | 22 câu: `id, split, type, question, expected_answer, gold_source_id, gold_page, evidence_quote, filter`; câu có filter thêm `filter_context`; `alternatives` liệt kê các trang/evidence hợp lệ khác |
| [../results/benchmark_verification.json](../results/benchmark_verification.json) | Kết quả `python -m scripts.verify_benchmark` (chạy từ `starter/`) |

## Thành phần

- **16 dev / 6 test**. Tối thiểu theo đề là 15/5; thêm 1 câu mỗi tập làm dự phòng.
- Loại câu: 7 trực tiếp, 6 diễn đạt lại, 4 điều kiện/ngoại lệ, 5 có metadata filter (3 dev, 2 test).
- Phủ cả 7 bài trong corpus. Gold page là số trang vật lý của PDF (khớp `page` trong manifest và metadata chunk).

## Cách kiểm chứng evidence

`scripts/verify_benchmark.py` chuẩn hóa cả evidence lẫn text trang bằng **cùng hàm** `normalize_text` của pipeline (NFC, gộp khoảng trắng), sau đó so khớp không phân biệt xuống dòng. Script xác nhận:

- mỗi evidence, kể cả evidence thay thế, nằm trên đúng trang gold;
- không evidence nào xuất hiện ở trang khác;
- giá trị filter tồn tại trong metadata, và trang gold thuộc đúng bài được lọc.

Lần chạy đầu: **23/23 evidence OK, 0 lỗi**. Evidence được chép nguyên văn, giữ cả lỗi in của nguồn, ví dụ `công nghệ số,vì`.

## Metadata filter (cấu hình C)

- Trường lọc: `article_id`, gồm 7 giá trị lấy từ tiêu đề và dòng nguồn in trong tài liệu (xem `data/manifest.json`).
- Filter là **input giả định do người dùng cung cấp trước khi truy xuất**, mô tả trong `filter_context`, ví dụ "người dùng chọn phạm vi Cẩm nang của Bộ TT&TT". Văn bản câu hỏi không chứa tên nguồn hay số trang.
- Câu filter được chọn ở các chủ đề **xuất hiện trong nhiều bài với nội dung khác nhau**, nên filter thực sự có tác dụng phân biệt:
  - định nghĩa CĐS: FSI (q16), Bộ TT&TT (q09);
  - CNTT so với CĐS (q10);
  - "thách thức lớn nhất" (q20, Tia Sáng; Cẩm nang có câu trả lời khác ở tr.13);
  - học trực tuyến trong giáo dục (q21).
- Với câu không có filter, cấu hình C chạy **không lọc**, giống B.

## Gold có nhiều đáp án hợp lệ

q16 có hai trang hợp lệ trong cùng bài FSI (tr.2 và tr.4). Bất kỳ trang nào trong `gold_page` hoặc `alternatives` đều được tính là hit.

## Quy ước ground truth

- `evidence_quote` là đoạn **ngắn nhất** trên trang gold đủ hỗ trợ toàn bộ `expected_answer`.
- `expected_answer` không chứa ý nào nằm ngoài evidence. Nếu ý đó cốt lõi thì nối thêm câu kế tiếp vào evidence (q10); nếu không thì cắt khỏi đáp án (q07, q08, q16).
- Với câu nhiều ý (q04, q05, q12, q18), evidence phủ đủ mọi ý của đáp án, kể cả điều kiện và ngoại lệ.

## Phạm vi: những gì cố ý không đưa vào

Sau một vòng góp ý, tôi quyết định **không** đưa các nội dung sau vào benchmark chính:

- **Câu không có đáp án (đo khả năng từ chối).** GUIDE §2 và BENCHMARK quy định không dùng câu không có đáp án trong nguồn cho chỉ số bắt buộc. Muốn đo khả năng từ chối thì cần một agent sinh câu trả lời, mà lab không yêu cầu xây chatbot.
- **Câu multi-hop / tổng hợp nhiều trang.** Định nghĩa Hit (GUIDE §4.1) yêu cầu một chunk trên trang gold chứa đủ evidence; câu nhiều trang không đo được theo định nghĩa này. GUIDE chỉ cho phép đánh giá ghép bằng chứng từ nhiều chunk như phân tích bổ sung.
- **Chỉ số cấp câu trả lời** (answer correctness, faithfulness, abstention). Pipeline không sinh câu trả lời; grounding ở đây chỉ đánh giá độ đủ của evidence truy xuất được (BENCHMARK). Phần "citation accuracy" đã nằm trong khía cạnh *metadata usefulness* (kiểm tra `source`/`page` của top-3). Phần "retrieval recall" chính là Evidence Hit@3.

## Tiêu chí chọn chiến lược (chốt trước khi xem test)

Chọn chiến lược **chỉ dựa trên dev**, theo thứ tự ưu tiên:

1. Evidence Hit@3 trên dev, cao hơn là tốt hơn.
2. Nếu chênh lệch ≤ 1 câu: Hit@1 trên dev.
3. Nếu vẫn hòa: chiến lược đơn giản hơn hoặc ít tài nguyên hơn (ít chunk hơn, ingest nhanh hơn).

Sau khi chọn, cố định cấu hình rồi mới chạy test một lần. Test chỉ dùng để báo cáo, không dùng để chỉnh tham số. Nếu buộc phải sửa sau khi đã xem test, sẽ ghi rõ trong báo cáo và không gọi đó là holdout độc lập.

## Rủi ro và giới hạn đã biết

- **Rò rỉ dev/test.** Không có huấn luyện nên rủi ro thấp. Tuy vậy, q09 (dev) và q21 (test) cùng lọc theo `a3_camnang_btttt`, và q16/q09 cùng mẫu câu "định nghĩa CĐS". Nhận xét về filter có thể bị ảnh hưởng nhẹ bởi việc đã thấy dev.
- **Mẫu nhỏ.** Test chỉ có 6 câu, nên mỗi câu tương đương 16,7 điểm %. Không suy rộng kết luận ra ngoài corpus.
- **Tác giả tự soạn và tự chấm**, nên có nguy cơ thiên lệch. Câu hỏi được chọn theo nội dung, trước khi có bất kỳ kết quả truy xuất nào.
- **Nội dung trong ảnh** (bảng, hình ở tr.25, 29, 37–42) không trích xuất được, nên không có câu hỏi nào dựa vào phần đó.
