# UI SPEC — SwissFlow VA (bản 2: Hypothesen)

> 15/10/2026 · Thay thế UI-SPEC bản 1 (Explore/Clusters/3D…). Đầu vào: `PRD-2.md` (US-15…US-26), `SYSTEM-DESIGN.md` §3.3–§3.4 (engine, rule sets), `BRD-2.md` (HR1–HR7).
> App: Dash + dash-bootstrap-components + Plotly. Prototype: `prototypes/*.html` (Tailwind CDN 3.4.16 + Plotly 2.35.2 qua jsDelivr, chỉ để thống nhất thiết kế; mở trực tiếp bằng trình duyệt, cần mạng). Nhãn UI **tiếng Đức**, tài liệu tiếng Việt.

## 0. Nguyên tắc thiết kế
1. **Kết luận trước, bằng chứng sau.** Mỗi trang trả lời đúng một câu hỏi: câu giả thuyết → badge kết luận → một con số chính → biểu đồ bằng chứng → điều kiện, định nghĩa, dữ liệu.
2. **Chuẩn luôn hiện, biến thể luôn được đánh dấu.** Khi người dùng đổi quy tắc, kết quả chuẩn (HR) vẫn đứng cạnh; mọi chỗ hiển thị biến thể có nhãn "Variante (nicht offiziell)" (HR6, D19).
3. **Minh bạch:** định nghĩa, n, giá trị bị loại và nguồn nằm ngay trên trang, không ẩn trong tooltip (G2).
4. **Responsive, mobile-first:** đọc được và chỉnh quy tắc được trên điện thoại 375 px; desktop ≥ 1280 px là bố cục chính để trình bày. Breakpoints như Tailwind/Bootstrap: `sm` 640 · `md` 768 · `lg` 1024 · `xl` 1280.
5. **Climate-tech theme** (sửa 23/10/2026, user chọn; thay gradient lila → đỏ cam và navy theme): bốn tông — **Linen Wash `#EAE4D9`** (nền trang, phẳng, có grain rất nhẹ bằng SVG noise ~7 %, «raw textured base»), **Deep Canopy Green `#1A4D2E`** (navbar, thẻ thông tin, modal, nút chính trên nền linen), **Inchyra Blue `#364E59`** (khối «Selbst testen», chữ phụ trên linen; bậc tối `#142026` = nền thẻ biểu đồ), **Acid Lime `#DFFF00`** (accent — chỉ dùng trên nền tối, không bao giờ trên linen vì chỉ 1.1:1). Chữ trên linen: `--ink #10291a` 12.3:1, `--ink-2 #1A4D2E` 7.7:1, `--muted #364E59` 6.9:1; nút chính trên linen = nền canopy, chữ lime 8.6:1. Trong thẻ canopy: ink `#f3efe7` 8.5:1, ink-2 `#d3dccf` 6.9:1, muted `#b4c8ba` 5.6:1, lime 8.6:1. Class `.navy-scope` giữ tên cũ (nay là token xanh canopy) để không phải đổi HTML. Tuyết rơi (`shared/snow.js`) lấy màu từ `--snow` = Inchyra trên linen. Đoạn dưới mô tả navy theme cũ (lịch sử; màu đã thay theo §4):
   Navy theme cho toàn app (sửa 20/10/2026, user chọn; ý tưởng: senseable.mit.edu/traveling-tastes; thay quyết định 15/10 "trang sáng, thẻ biểu đồ tối"). Nền trang `#0d0b25` (gradient nhẹ tới `#0a0920`); thẻ thông tin (KPI, Ergebnis, Regeln, Varianten, Robustheit, Bedingungen, Definitionen, bảng) dùng `--surface` `#171547`; thẻ biểu đồ (`VizCard`) là "màn hình" tối nhất `#0a092b` có viền lavender mờ, nên vẫn nhìn ra ngay đâu là visualisation. Accent lavender `#dcd6ff` (link `#b9b0ff`). Tiêu đề lớn dùng **Space Grotesk** (sửa 20/10/2026: thay font pixel Handjet), chữ thường **Quicksand**, số/nhãn/biểu đồ **Inconsolata** (Google Fonts; offline → system font). Phần Frage của `/hN` có **tuyết rơi**: các bông tuyết trắng rất nhỏ (bán kính 0.6–2.5 px, độ mờ 55–95 %) rơi chậm và lắc nhẹ, vẽ trên `<canvas aria-hidden>` tràn toàn chiều ngang (thay "wall of data" ngày 20/10/2026 theo yêu cầu user). Dừng khi phần Frage ra khỏi màn hình hoặc tab bị ẩn; `prefers-reduced-motion` → một khung hình tĩnh. Header của `/` và `/hypothesen` cũng có tuyết rơi (thêm 20/10/2026). Code dùng chung: `shared/snow.js` (`SFSnow(canvas)`) → Dash `assets/snow.js`.
6. **Không có Global Filter Bar** (D16). Mỗi trang có khoảng thời gian cố định theo HR1; thứ duy nhất người dùng chỉnh là quy tắc trong RuleEditor.

## 1. Sitemap

```
/            Datenüberblick KPI, Netzkarte, Trends, Quellmärkte, Kalender, Neuschnee-Muster US-27, US-28, US-29 (trang chủ)
/hypothesen  Hypothesen     5 thẻ kết luận, trạng thái dữ liệu, xuất báo cáo     US-22
/h1          H1 · PCA       Regionen nach Gästemix                                US-17
/h2          H2 · Saison    Quellmärkte Sommer/Winter                             US-18
/h3          H3 · Anomalie  Starkverspätungstage GR ↔ Neuschnee Davos             US-19
/h4          H4 · Neuschnee Bergstationen: Verspätung/Ausfälle; Logiernächte YoY  US-20
/h5          H5 · Intensität Logiernächte ↔ Verspätung (GR, Zürich, Bern)         US-21
/quality     Datenqualität  (đã có, US-04)                                        US-04
```
Trạng thái trang nằm trong URL: `/h3?snow_cm=10&heavy_mode=mean_delay` hoặc `/h3?rule_set=7` (SYSTEM-DESIGN §4). Mở lại link → đúng trạng thái.

**Khung chung (AppShell):**
- **Desktop:** top navbar: logo "SwissFlow VA" · `Daten` · `Hypothesen` · `H1 … H5` (mỗi mục có chấm trạng thái = kết luận chuẩn) · `Datenqualität`. Bên phải: "Daten bis 30.09.2026".
- **Mobile (< md):** navbar gồm logo + nút menu; danh sách trang trượt xuống. Trên trang `/hN` có thêm thanh "‹ H2 · H3 · H4 ›" để chuyển nhanh giữa các giả thuyết.
- **Section rail (desktop ≥ 1024 px, thêm 20/10/2026, ý tưởng từ senseable.mit.edu/visual-AI-book):** cột ô vuông nhỏ cố định ở mép phải, mỗi ô là một **phần trong trang** (không phải một trang). Navbar trên vẫn là điều hướng giữa các trang; rail chỉ điều hướng trong trang dài. Chi tiết: §5 `SectionRail`.

## 2. Wireframes

### 2.0 Datenüberblick `/` — trang chủ (SYSTEM-DESIGN §3.5, D22–D23, US-27/US-28/US-29/US-30)
> Kỹ thuật bổ sung đã chọn (§2.9): **D3** Netzkarte als Small Multiples (Could), **D4** Quellmärkte als Treemap (Could).

Mục đích: ấn tượng đầu tiên về dữ liệu (xu hướng, mùa vụ, ngày bất thường) **trước** khi xem giả thuyết. Trang khám phá, không đưa ra kết luận. Biểu đồ nằm trong VizCard (tối), KPI và bảng sáng (§0.5).
Thứ tự panel (quyết định 16/10/2026, thêm Netzkarte 20/10/2026, Kantonskarte 06/11/2026): **KPI → Netzkarte → Kantonskarte → Trends → Quellmärkte → Kalender → Auffälligkeiten → Saisonmuster (Neuschnee)**. Mặc định là chế độ **"Nur echte"**; "Vorschau" bổ sung dữ liệu mẫu cho các tháng chưa nạp, chỉ để trình bày. Sửa 23/10/2026 (yêu cầu user): bỏ dòng mô tả dưới tiêu đề («Was steckt in den Daten? …») và banner của chế độ "Nur echte" — khoảng trống dữ liệu vẫn thấy ở KPI «Datenabdeckung Ist-Daten»; banner vàng của chế độ "Vorschau" (dữ liệu mẫu) giữ nguyên.
```
┌ Daten  Hypothesen  H1… H5  Datenqualität ─────────────────────────────── Daten bis 30.09.2026 ┐
│ Datenüberblick           [Von 01/2025 ▾] [Bis 09/2026 ▾] [Region: Schweiz ▾] [Vorschau|Nur echte]│
│ ┌KPI──────────┐┌KPI─────────┐┌KPI─────────┐┌KPI──────────┐┌KPI──────────┐┌KPI───────────┐    │
│ │Ø Verspätung ││Pünktlich.  ││Ausfälle    ││Logiernächte ││Neuschneetage││Datenabdeckung│    │
│ │1.36 min     ││88.1 %      ││0.64 %      ││69.2 Mio ▼0.5││13 Tage ▲1   ││Ist-Daten 2/21│    │
│ │– kein VJ    ││– kein VJ   ││– kein VJ   ││_╱‾╲_╱‾      ││▁▃▇▅▁        ││█░░░░░░░░░█   │    │
│ └─────────────┘└────────────┘└────────────┘└─────────────┘└─────────────┘└──────────────┘    │
│ ⓪ VizCard: Netzkarte – Stationen (Grösse = Halte/Tag, Farbe = Pünktlichkeit vs. CH)  → H3·H4·H5│
│   [Verkehrsmittel: Alle ▾] [Stationen: Bahnhöfe + ab 300 Halten/Tag ▾]                       │
│   ● pünktlicher  ● ähnlich (± 2 pp)  ● unpünktlicher  ○ nicht geladen / < 50 Halte  ─ Verbindung │
│ ⓪b VizCard: Kantonskarte – Fläche = Logiernächte Region · Blase = verspätet + ausgefallen │
│   [Monat: Jan 2025 · Ist-Daten ✓ ▾]   Blasenfarbe: ● Neuschnee ● Schneedecke ● kein ○ k. M.  │
│   Klick = 1 Kanton · Lasso über Blasen = mehrere → Modal mit 3 Monatskurven      → H2·H3·H4│
│ ① VizCard: Trends pro Monat (4 Reihen, gemeinsame x-Achse) ─────────────────────── → H5      │
│ ② VizCard: Quellmärkte – Treemap Region → Top-5-Herkunftsländer + Übrige (D4) → H1·H2      │
│ ③ VizCard: Kalender Anteil ≥ 3 min, Wochen × Wochentage, ○ = |z| ≥ 3 (volle Breite) → H3    │
│ ④ Auffälligkeiten (hell, volle Breite): Datum · Wert · Basis · z · Kontext · [CSV ↓]        │
│ ⑤ VizCard: Saisonmuster Neuschneetage, 13 Regionen × Monate (sequentiell) ────── → H3·H4    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```
- **KPI:** giá trị của khoảng đã chọn + Δ so với **cùng các tháng** năm trước (tooltip liệt kê các tháng; không có tháng chung → "– kein Vorjahresvergleich"), sparkline 12 tháng có khoảng trống. Pünktlichkeit = 1 − Anteil ≥ 3 min. Ô "Datenabdeckung" có dải 21 tháng và link tới `/quality`.
- **Netzkarte (US-29, toàn chiều rộng, ngay sau KPI):** Plotly `Scattermap`, nền `carto-darkmatter` (không cần token; chú thích © OpenStreetMap, © CARTO). Chiều cao 520 px (mobile 400 px), cuộn chuột để zoom.
  - **Ga:** điểm, kích thước ∝ √(Halte/Tag) (4–16 px). Màu = Pünktlichkeit so với **CH-Schnitt của khoảng đã chọn**, chia 3 lớp: xanh `#3987e5` = pünktlicher (≥ 2 pp), xám nhạt `#c3c2b7` = ähnlich (± 2 pp), đỏ `#e66767` = unpünktlicher (≥ 2 pp). Vòng rỗng xám = không có đánh giá (Ist-Daten chưa nạp hoặc < 50 Halte có giờ thật). Đúng quy tắc ≤ 3 màu + hình dạng. Lớp thay cho thang liên tục, vì trên nền bản đồ tối màu giữa của thang diverging (`#383835`) sẽ biến mất. Tham chiếu luôn là CH, kể cả khi chọn Region: nhờ vậy một vùng kém đúng giờ hiện đỏ toàn bộ, và đó chính là thông tin cần thấy.
  - **Link:** đường xám `rgba(195,194,183,.32)`, 3 độ dày theo Fahrten/Tag (Plotly `scattermap` chỉ cho một độ dày trên mỗi trace). Không tô màu link theo độ trễ.
  - **Mật độ:** ở mức zoom cả nước mặc định là "Bahnhöfe + ab 300 Halten/Tag": khoảng 2 700 ga (đo trên dữ liệu thật: ≥ 40 Halte/Tag = 14 585 ga, ≥ 100 = 6 469, ≥ 300 = 1 432). Lựa chọn khác: "ab 100", "alle (ab 40)". Zoom ≥ 9.5 hoặc chọn Region → hiện mọi ga của khung nhìn/vùng.
  - **Tương tác:** hover → tên, vùng, độ cao, Halte/Tag, Pünktlichkeit, Ausfallquote, số ngày. Click ga → Region = vùng du lịch của ga (toast "Ort → Region: …"), bản đồ zoom vừa vùng đó. Bộ lọc Verkehrsmittel (Alle | Bahn | Bus | Tram | Zahnrad/Seilbahn | Schiff) chỉ bật khi đã có Fahrplan; trước đó nút bị tắt và có tooltip giải thích.
  - **Trạng thái:** "Nur echte" khi chưa có GTFS → chỉ ga, ghi chú "Verbindungen … noch nicht geladen, darum nur Stationen". "Vorschau" → thêm **Beispielnetz** (láng giềng gần nhất, Verkehrsmittel ước đoán), có nhãn rõ ràng. Khoảng không có tháng Ist-Daten nào → mọi ga là vòng rỗng, ghi chú "keine Interpolation".
- **Kantonskarte (US-30, toàn chiều rộng, sau Netzkarte; thêm 06/11/2026, đã implement trong `app/pages/home.py`, chưa có prototype HTML):** Plotly `Choroplethmap` + `Scattermap`, 26 kanton (swissBOUNDARIES3D, đơn giản hóa ~250 m). Chiều cao 560 px. Bộ lọc riêng **Monat** (dropdown, mới nhất trên cùng, nhãn «· Ist-Daten ✓» cho tháng có Ist-Daten); không theo Zeitraum của trang vì HESTA chỉ có theo tháng → **không có chế độ tuần**. Mặc định = tháng mới nhất có cả Ist-Daten và Logiernächte đã công bố.
  - **Mặt kanton:** Logiernächte (alle Herkunftsländer) của **vùng du lịch chính** của kanton → nhiều kanton cùng vùng có cùng màu (đó là độ phân giải của dữ liệu). Thang sequential xanh một tông (`SEQ`), colorbar «Logiernächte der Region». Chưa công bố / bị ẩn = xám `NOT_COLLECTED`, không bao giờ là 0. Viền trắng 0.8 px.
  - **Bong bóng** tại điểm bên trong kanton: diện tích ∝ Halte trễ ≥ 3 min + Halte bị hủy (tuyệt đối, history), 5–46 px. Màu = lớp tuyết của tháng: cam `CAT[1]` Neuschnee · xanh lá `CAT[2]` Schneedecke · xám đậm `INK_2` kein Schnee · xám nhạt `OTHER` keine Messung (không dùng xanh dương vì trùng thang của mặt kanton; 2 tông + 2 trung tính, đúng quy tắc ≤ 3 màu). Tháng không có Ist-Daten: mọi bong bóng cùng cỡ 9 px, mờ, banner xám «Ist-Daten für … nicht geladen — Blasen zeigen nur Schnee»; tháng thiếu ngày: «x von y Tagen geladen».
  - **Tooltip:** kanton → vùng (+ «auch: …» cho AG, BE, SG, SH, SZ), Logiernächte; bong bóng → Verspätet, Ausgefallen, Summe, Halte-Ereignisse, số ga, lớp tuyết + số ngày Neuschnee/Schneedecke + số trạm tuyết. Số dạng `1’234’567`.
  - **Tương tác:** `dragmode = lasso` (cuộn = zoom; nút pan trong modebar). Click kanton hoặc bong bóng = 1 kanton; lasso trên bong bóng = nhiều kanton → `dbc.Modal` (xl) «Kanton …» / «n Kantone: …» với 3 biểu đồ đường theo tháng, chung trục `MM.YYYY`: (1) Logiernächte (mỗi vùng tính một lần; một vùng bị ẩn → khoảng trống), (2) Verspätet ≥ 3 min (xanh, chấm tròn) + Ausgefallen (cam, chấm vuông, nét chấm), khoảng trống = nicht geladen, (3) Tage Neuschnee / Schneedecke (ohne Neuschnee) / kein Schnee (nét đứt), «keine Messung» ẩn trong legend. Ghi chú nguồn dưới mỗi phần (BR3).
  - **Theme:** bản implement hiện tại dùng theme sáng của app (`carto-positron`); khi chuyển sang VizCard tối thì dùng `carto-darkmatter` và màu bong bóng từ `--cat-*` của theme đã chọn (kiểm lại tương phản trên nền tối).
- **Trends:** 4 hàng small multiples, chung trục tháng, mỗi hàng một trục y (không trục kép). Tháng chưa nạp = dải xám có nhãn "Ist-Daten nicht geladen – keine Interpolation"; đường bị ngắt. Chấm đặc = tháng có Ist-Daten thật; chấm rỗng = giá trị mẫu (chỉ ở "Vorschau"). Nền nhạt đánh dấu mùa đông (HR1). Mobile: nhãn trục mỗi 6 tháng.
- **Quellmärkte (toàn chiều rộng) — sửa 07/11/2026 (user):** biểu đồ thanh ngang top-11 thị trường nước ngoài **đã bỏ**; thay bằng treemap **D4** (§2.9): diện tích = đêm lưu trú, vùng → top-5 nước xuất xứ + Übrige, **có cả Inland (~49 %)**, click vùng = zoom, hover = số chính xác. Mất so sánh YoY (▲▼) của từng thị trường — nếu cần thì đưa vào tooltip. Dữ liệu HESTA thật.
- **Kalender (toàn chiều rộng):** tuần × thứ (Mo–So), màu sequential theo giá trị; ngày |z| ≥ 3 có vòng sáng; xám = nicht geladen. Hover: giá trị, z, "Beispiel" nếu là dữ liệu mẫu. Click → tô sáng dòng trong Auffälligkeiten. Mobile: cuộn ngang trong thẻ.
- **Auffälligkeiten (sáng, toàn chiều rộng):** top 15 theo |z|, mỗi dòng một hàng; cột bối cảnh (ΔHS Davos, mưa CH, số ga). Ghi chú cố định: "Explorativ – nicht die H3-Definition (HR3). Feiertage werden nicht separat behandelt. Kontext ist kein Nachweis einer Ursache." Quyết định 16/10/2026: **không** thêm lịch ngày lễ, chỉ giữ ghi chú (01.01.2025 vì vậy hiện là "auffällig tief").
- **Saisonmuster – Neuschnee (thay cho độ trễ, 16/10/2026):** heatmap 13 vùng × tháng, giá trị = số ngày tuyết mới (ΔHS ≥ 5 cm), trung bình trên các trạm tuyết mà ga của vùng sử dụng. Thang sequential (tối = 0, sáng = nhiều). Dữ liệu thật cho mọi tháng. Click vùng → bộ lọc Region. Link → H3, H4.
- **Trạng thái:** ở chế độ "Nur echte", trước US-15 phần lớn panel độ trễ là khoảng trống có nhãn, KPI độ trễ không có so sánh năm trước. Quellmärkte và Saisonmuster đã đầy đủ.

### 2.1 Trang tổng quan `/hypothesen` (US-22)
> Kỹ thuật bổ sung đã chọn (§2.9): **O1** Datenstand-Streifen (Could, cũng dùng ở `/quality`).


> **Sửa 20/10/2026 — bố cục chương (ý tưởng: senseable.mit.edu/traveling-tastes), thay lưới 5 thẻ bên dưới:** header (tiêu đề Space Grotesk, StatusSummary + Datenstand, nút Bericht; không có wall of data) → **mỗi giả thuyết một chương toàn chiều ngang**: **trái** (5/12) = mã H (Space Grotesk 44–72 px, màu accent; câu hỏi 17–20 px, key metric 15 px — giảm 20/10/2026), "i / 5 · chủ đề", câu hỏi (`question` như trên `/hN`), badge kết luận, key metric hoặc "Fehlt: …", "Hypothese im Wortlaut" (thu gọn), nút "Hn ansehen →" + số biến thể; **phải** (7/12) = biểu đồ trong VizCard, cao 380 px (mobile 280 px, xếp dưới phần chữ), cùng nội dung mini chart cũ. Chương cao ≥ 82 % màn hình trên desktop, hiện dần khi cuộn tới (reduced motion → hiện ngay). Section rail: Übersicht · H1 … H5. Prototype: `00-hypothesen.html` (vòng 3, chờ duyệt). Wireframe lưới thẻ bên dưới là phiên bản cũ.
```
┌ SwissFlow VA   Hypothesen  H1● H2● H3○ H4○ H5○  Datenqualität ─────── Daten bis 30.09.2026 ┐
│ Hypothesen                                                         [Bericht exportieren .md]│
│ Wetter, Tourismus und ÖV-Verspätungen in der Schweiz – 5 Hypothesen, Standard-Regeln (HR)   │
│ ┌ Status ────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 1 gestützt · 1 nicht gestützt · 3 unzureichende Daten   │ Ist-Daten fehlt: 2025-02…2026-08│ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ H1 · Dimensionsreduktion ──┐ ┌ H2 · Verteilung ───────────┐ ┌ H3 · Anomalie ─────────────┐│
│ │ "Werden die Tourismus-…"   │ │ "Gäste aus China …"         │ │ "Die Mehrheit der Tage …"  ││
│ │ ✕ nicht gestützt           │ │ ✓ gestützt                  │ │ ? unzureichende Daten      ││
│ │ 5 / 6 Regionen auf der     │ │ 3 / 3 Bedingungen erfüllt   │ │ Ist-Daten 11/2025–04/2026  ││
│ │ erwarteten PC1-Seite       │ │                              │ │ fehlt → Datenqualität ↗   ││
│ │ 2 Varianten · 1 gestützt   │ │ 0 Varianten                 │ │                             ││
│ │                 Ansehen →  │ │                Ansehen →    │ │               Ansehen →    ││
│ └────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────────┘│
│ ┌ H4 … ┐ ┌ H5 … ┐                                                                            │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```
- **Thẻ "màn hình tối" (quyết định 15/10/2026, review vòng 1):** trang vẫn sáng, nhưng mỗi thẻ có nền gần đen (`--screen-bg #141413`), giống một màn hình nhỏ ở dark mode. Mỗi thẻ có **một mini chart** (cao 150 px, nền `#0d0d0c`), tạo cảm giác "visual analytics" ngay từ trang đầu:
  | H | Mini chart | Khi chưa đủ dữ liệu |
  |---|---|---|
  | H1 | Scatter PC1 × PC2 của 13 vùng; nhóm = màu + hình; nhãn trực tiếp cho 6 vùng được nêu tên | — |
  | H2 | Lollipop 6 Standortquotient (3 cặp vùng "oder"), đường tham chiếu LQ = 1 | — |
  | H3 | Cột ΔHS Davos theo ngày (đường 5 cm) | Phần đã có (tuyết); chú thích "Verspätungen fehlen noch" |
  | H4 | Dải 21 tháng: Ist-Daten đã nạp / thiếu, nền đánh dấu mùa đông 25/26 | Đây chính là nội dung chart |
  | H5 | Số đêm lưu trú/tháng của GR, Zürich, Bern, **index Ø = 100** (một trục, không trục kép) | Phần đã có; chú thích "Verspätungen fehlen noch" |
  Mini chart có tooltip khi hover, không có thanh công cụ. Chú giải nằm trong caption (không đặt nhãn đè lên dữ liệu). Chart được vẽ sau khi layout xong và resize theo thẻ.
- Lưới thẻ: 1 cột (< md) · 2 cột (md) · 3 cột (xl). Thứ tự luôn H1→H5, không sắp theo kết luận.
- Thẻ: mã + chủ đề VA, câu giả thuyết rút gọn (2 dòng, có tooltip/expand cho câu đầy đủ), `VerdictBadge`, key metric (1 câu), dòng "x Varianten geprüft · y gestützt" (D18), link. Thẻ *unzureichende Daten* liệt kê `missing_data` và link tới `/quality`.
- "Bericht exportieren" → `GET /hypotheses/report` (US-22 AC3).

### 2.2 Khung trang giả thuyết `/h1` … `/h5` (dùng chung) — dạng câu chuyện (sửa 20/10/2026)
Ý tưởng: senseable.mit.edu/global-interiors (câu hỏi được gõ vào ô tìm kiếm, sau đó cuộn qua từng biểu đồ). Thay cho bố cục cũ (Ergebnis ở trên, bằng chứng bên trái, Regeln/Varianten/Robustheit ở cột phải). Lý do: người xem đọc **câu hỏi → câu trả lời → bằng chứng** theo đúng thứ tự (nguyên tắc §0.1); phần user-in-the-loop trở thành **lời mời ở cuối trang**, không chiếm chỗ bên cạnh biểu đồ.
```
① FRAGE (cao 1 màn hình)            H3 · WETTER / ANOMALIE
                      ┌──────────────────────────────────────────────────────┐
                      │ 🔍 Hatten die stärksten Verspätungstage in Graubünden │ [↓]
                      │    im Winter 2025/26 Neuschnee in Davos?▌             │
                      └──────────────────────────────────────────────────────┘
                      HYPOTHESE H3 · «Die Mehrheit der Tage, … Neuschnee auf.»
                      [Beispieldaten · …]                      Antwort ↓
② ANTWORT            ANTWORT NACH DEN STANDARDREGELN (HR)
                      ✓ gestützt  (badge lớn)
                      9 / 10 Starkverspätungstage mit Neuschnee (90 %)
③ EVIDENZ 1 / n …    mỗi khối trong evidenceHtml = một bước, hiện dần khi cuộn tới (§2.3–2.7)
④ WARUM DIESES URTEIL?   Bedingungen (Standard | Variante)
⑤ SO HABEN WIR GEMESSEN  Definitionen · Datenbasis · [CSV ↓] [Bericht ↓]
⑥ JETZT DU — «Hält das Urteil, wenn du die Regeln änderst?»
   ┌ Regeln (RuleEditor) ┐ ┌ Ergebnis Standard / Variante ─────────────────┐
   │ … [↺ Standard]       │ │ Robustheit (SweepStrip)                        │
   │ [Als Variante …]     │ │ Varianten (VariantList)                        │
   └──────────────────────┘ └────────────────────────────────────────────────┘
khi có biến thể: thanh cố định góc dưới trái  [Variante aktiv] Diagramme zeigen die Variante · Regeln ↓ · ↺ Standard
Section rail (§5) bên phải: Frage · Antwort · <nhãn từng bước Evidenz> · Urteil · Definitionen · Selbst testen
mobile < lg: cùng thứ tự; RuleEditor là accordion (mở sẵn); rail ẩn
```
- **Frage:** mỗi trang có `question` (câu hỏi ngắn, tiếng Đức, kiểu câu tìm kiếm) bên cạnh `statement` (câu giả thuyết gốc, hiện dưới ô tìm kiếm). Câu hỏi được gõ từng ký tự khi tải trang (~30 ms/ký tự, tối đa 2.6 s), có con trỏ nhấp nháy; nút ↓ chuyển sang màu accent khi gõ xong. Enter / nút ↓ / "Antwort ↓" → cuộn tới Antwort. Câu đầy đủ luôn có trong `<h1 class="sr-only">`; phần gõ là `aria-hidden`. Không gõ (hiện ngay) khi `prefers-reduced-motion` hoặc khi URL có tham số biến thể (link chia sẻ).
  - Khác với bản gốc MIT (gõ theo vị trí cuộn): ở đây gõ theo thời gian. Lý do: không cần một đoạn cuộn "trống" dài, link mở thẳng một biến thể vẫn đọc được ngay, và hoạt động như nhau trên mobile.
- **Antwort** luôn là **kết luận chuẩn** (HR6). Khi có biến thể: thêm một dòng "Variante aktiv – Die Diagramme unten zeigen die Variante: <badge>" và thanh `Variante aktiv` cố định, để người xem cuộn lên vẫn biết biểu đồ đang vẽ theo biến thể.
- **Evidenz:** mọi khối cấp cao nhất trong `evidenceHtml` của trang được bọc thành một bước có nhãn "Evidenz i / n" và nhãn ngắn cho rail (`data-rail` trên khối, nếu thiếu thì lấy `h2` đầu tiên). Mỗi bước hiện dần (opacity + dịch 28 px, 0.7 s) khi vào màn hình; không có JS hoặc reduced motion → hiện ngay. Biểu đồ vẫn vẽ theo **quy tắc đang chọn** và đường chuẩn được vẽ làm tham chiếu như trước.
- **Selbst testen** ở cuối trang: tiêu đề mời gọi + giải thích ngắn (Standard là chính thức, biến thể chỉ để thử). **Giao diện (sửa 23/10/2026):** khối là một **dải Inchyra Blue `#364E59` tràn toàn chiều ngang** (thay accent cam trên nền đỏ cam) để đánh dấu vùng người dùng tự thử; thẻ bên trong là canopy như mọi nơi, accent lime (RuleEditor, chip, tag biến thể, slider, nút). Chữ trên dải: ink `#f3efe7` 7.7:1, ink-2 `#dbe3e6` 6.8:1, muted `#c3d0d5` 5.6:1, lime 7.7:1. (Bản 20/10: nền đỏ cam, accent cam `#ffb067` — đã thay.)
- Khi engine đang tính: Ergebnis hiện skeleton + "wird berechnet…", biểu đồ giữ trạng thái cũ, mờ 50 %.
- **Dash:** cùng component như §5 (không có component mới ngoài `QuestionBar`, `StoryStep`, `VariantBar`); hiệu ứng gõ và hiện dần là JS thuần trong `assets/story.js`, không cần callback.

### 2.3 H1 — PCA (US-17)
```
┌ Biplot PC1 × PC2 ─────────────────────────────┐ ┌ Erklärte Varianz ────┐
│      ▲ Genf     · Basel                        │ │ PC1 ▇▇▇▇▇▇▇▇▇ 47 %   │
│  ◆ Zürich  ◆ Luzern       ● Graubünden         │ │ PC2 ▇▇▇▇ 22 %        │
│        → USA, Kanada   ← Schweiz   ● Ostschweiz│ └──────────────────────┘
│   (mũi tên = 6 loading lớn nhất)               │ ┌ Ladungen PC1 ─────────┐
│  ● Schweiz-dominiert ◆ international · übrige  │ │ Schweiz     ▕▇▇▇▇ +.35│
└────────────────────────────────────────────────┘ │ Kanada  ▇▇▇▇▏    −.35 │
┌ Stabilität: 15 Läufe (2025, 2026, je 1 Region weg) ●●●●○●●●●●●○●●● 13/15 ┐
```
- Điểm: nhóm giả thuyết = màu + hình (`--cat-1` tròn, `--cat-2` thoi, `--other` chấm nhỏ). Nhãn trực tiếp cho 6 vùng được nêu tên; các vùng khác chỉ có tooltip.
- Trục PC1 có chú thích hai phía: "← international · Schweiz-dominiert →".
- Loadings: thanh ngang có dấu, sắp xếp, có Übrige. Màu (quyết định 16/10/2026): **dương = xanh** (`#3987e5`, hướng Schweiz-dominiert), **âm = đỏ** (`#e66767`, hướng international).
- **Rule editor H1:** Zeitraum (Monatsbereich), Anzahl Herkunftsländer (`top_n`), Skalierung, **Gruppenzuordnung**: mỗi vùng một segmented control 3 nút [CH | Int. | –]. Đây là thao tác user-in-the-loop chính của H1: chuyển Wallis sang "–" và xem kết luận thay đổi.

### 2.4 H2 — Saisonale Verteilung (US-18)
> Kỹ thuật bổ sung đã chọn (§2.9): **S1** LQ-Kachelkarten 3 Länder × 2 Saisons (Should), **S2** Gästeflüsse: Parallel Edge Splatting + Interleaving (Could).

```
┌ LQ-Heatmap: Region (hàng) × [China · Deutschland · GB] × [Sommer 2025 | Winter 2025/26] ┐
│ ô = LQ, diverging quanh 1 (log): xanh < 1 · xám = 1 · đỏ > 1; ô được nêu trong H2 có viền │
└───────────────────────────────────────────────────────────────────────────────────────────┘
┌ Logiernächte pro Monat (small multiples 4 Regionen × 3 Länder, nền xám = Winter) ────────┐
```
- Thang màu (quyết định 16/10/2026): **chỉ một tông xanh**, từ xanh nhạt (`#cde2fb`, LQ thấp) đến xanh đậm (`#0d366b`, LQ cao), trên log2(LQ) trong khoảng 0.35–2.8; colorbar có mốc 0.5 / 1 / 2. Vì không còn điểm giữa diverging, mốc LQ = 1 được ghi trong chú thích và trong biểu đồ cột bên dưới. Ngoại lệ có chủ ý với quy tắc "giá trị thấp chìm vào nền tối": ô nhạt nổi trên VizCard tối.
- Giá trị chỉ hiện trong 6 ô được nêu tên: chữ tối trên ô nhạt, chữ sáng trên ô đậm; viền vàng (`#eda100`) đánh dấu các ô đó.
- ~~Biểu đồ cột nhóm~~ — **đã bỏ 07/11/2026 (user)**: cùng dữ liệu với heatmap; vai trò so sánh theo vùng nay do kachel map **S1** đảm nhận (§2.9).
- **Biểu đồ đường theo tháng:** 4 vùng dùng **chung một thang y** (0 đến max của cả 4 vùng), để so được độ lớn giữa các vùng.
- Mùa thiếu dữ liệu: tiêu đề cột thêm "(unvollständig)".
- **Rule editor H2:** Saisonmodell (BFS | meteorologisch), Zeitraum, LQ-Schwelle.

### 2.5 H3 — Anomalie (US-19) · *prototype: `03-h3.html`*
> Kỹ thuật bổ sung đã chọn (§2.9): **A1** Pixel-Matrix GR-Stationen × Wintertage + ΔHS Davos (Should), **A2** Overview + Detail mit Range-Slider (Could).

```
┌ KPIs ───────────────────────────────────────────────────────────────────────────┐
│ 14 / 22  Starkverspätungstage mit Neuschnee   │ 31 %  Basisrate: Neuschnee an allen │
│          (64 %)                               │       Wintertagen                    │
├ Anteil Stationen mit Starkverspätung (GR), täglich, 01.11.2025–30.04.2026 ──────┤
│ ──╮╭─╮──────────╭╮─── · · · · · 50 % ─ ─ ─ ─ (Schwelle)   ● = Starkverspätungstag │
├ Neuschnee Davos (ΔHS, cm), gleiche x-Achse ──────────────────────────────────────┤
│ ▁ ▇ ▁ ▁ ▃ ▇▇ ▁ … ─ ─ 5 cm      ▮ = Neuschneetag (inkl. Vortag)                     │
├ Kreuztabelle 2×2 ───────────────┬ Tag gewählt: 14.01.2026 ───────────────────────┤
│           Neuschnee  kein  unbek.│ Top-10 Stationen (Ankünfte ≥ 3 min) · Ausfälle │
│ stark        14       8     0    │ HS/HN Davos                                     │
│ normal       42     117     0    │                                                 │
└──────────────────────────────────┴─────────────────────────────────────────────────┘
```
- **Ereignis-Ausrichtung (mới 16/10/2026, VizCard ngay dưới timeline):** cho thấy thời điểm tuyết rơi và ngày trễ nhiều, kể cả độ trễ (lag).
  - *Raster sự kiện:* mỗi dòng = một sự kiện tuyết mới (ngày đầu tiên có ΔHS ≥ ngưỡng; các ngày tuyết liên tiếp gộp thành một sự kiện), mỗi cột = ngày −3 … +5. Ô sáng = ngày trễ nhiều. Khung chấm = các ngày mà quy tắc "Vortage zählen mit" tính là ngày tuyết mới (0 … +lag).
  - ~~*Biểu đồ cột* tỷ lệ ngày trễ nhiều theo ngày tương đối~~ — **đã bỏ 07/11/2026 (user)**. Raster sự kiện giữ nguyên; tỷ lệ cao nhất và basis rate chỉ còn trong dòng tóm tắt.
  - Dòng tóm tắt: số sự kiện, ngày có tỷ lệ cao nhất, basis rate. Biểu đồ cập nhật theo RuleEditor (ngưỡng tuyết, lag, định nghĩa ngày trễ nhiều).
- Hai biểu đồ xếp chồng, **cùng trục x**, không dùng trục kép. Hover/crosshair được đồng bộ giữa hai biểu đồ. Click vào một ngày → panel "Tag gewählt".
- Ngày trễ nhiều: chấm `--accent` trên đường. Ngày tuyết mới: cột `--seq-500`; ngày không phải: `--seq-200`; "unbekannt": gạch chéo xám.
- **Rule editor H3:** Schneestation (DAV…), Neuschnee ab (cm), Vortag zählt (0/1/2 Tage), **Definition Starkverspätung** (radio 3 mode, chỉ hiện tham số của mode đang chọn), Mehrheit (%), Basisrate muss übertroffen werden (toggle), Mindestanzahl Tage.

### 2.6 H4 — Neuschnee & Bergstationen (US-20)
> Kỹ thuật bổ sung đã chọn (§2.9): **N1** Small Multiples je Bergstation (Should), **N2** Linking Box-Plot ↔ Karte (Could).

```
┌ (a) Bergstationen > 1000 m · Wintertage: Neuschnee vs. kein Neuschnee ─────────────────┐
│ Ø Verspätung (min)      │ Anteil ≥ 3 min        │ Ausfallquote                          │
│  ├─[▇▇|▇]─┤ Neuschnee   │  ├─[▇|▇▇]─┤           │  ├[▇|▇]┤                               │
│  ├─[▇|▇]─┤  kein        │  ├─[▇|▇]─┤            │  ├[|▇]┤                                │
│ Δ Median +0.4 [0.2, 0.6]│ Δ +3.1 pp [1.8, 4.2]  │ Δ +0.6 pp [0.1, 1.0]                  │
├ (b) Region × Monat: Δ Neuschneetage (x) vs. Δ % Logiernächte YoY (y), r = 0.12, n = 21 ┤
└ Ausgeschlossen: 41 Stationen ohne Schneestation · Distanz zur Schneestation (Histogramm) ┘
```
- **Thứ tự Evidenz (sửa 07/11/2026, user):** 1 = **N2** Linking Box-Plot ↔ Karte · 2 = **N1** Small Multiples je Bergstation · 3 = (b) Neuschneetage vs. Logiernächte YoY + Ausgeschlossen (**luôn là bước cuối**). Bước (a) «Bergstationen Neuschnee vs. kein Neuschnee» (3 box plot) **đã bỏ** (07/11/2026, user); các hiệu ứng (Δ median + KI) vẫn được tính và hiện trong «Ergebnis»/điều kiện của Urteil — wireframe (a) bên dưới chỉ còn là lịch sử.
- Box plot vẽ từ quantile (p5/p25/p50/p75/p95, D17). Ba panel cùng bố cục, mỗi panel một trục riêng.
- Câu bắt buộc dưới (b): "Kein Rückgang beobachtet ≠ kein Effekt (kleines n)".
- **Rule editor H4:** Höhe ab (m), Neuschnee ab (cm), Vortag zählt, max. Distanz zur Schneestation, r-Schwelle.

### 2.7 H5 — Intensität (US-21, US-25)
> Kỹ thuật bổ sung đã chọn (§2.9): **I1** SPLOM Monat × Einheit (Should), **I3** Alle Einheiten, sortiert nach Logiernächten (Could).

```
┌ Graubünden ────────┐ ┌ Zürich (Gemeinde) ─┐ ┌ Bern (Gemeinde) ───┐  x = Logiernächte/Monat
│  · ·  ·/·          │ │ · · · ·            │ │ ·  · · ·           │  y = Ø Verspätung (min)
│ r = 0.62           │ │ r = 0.21           │ │ r = 0.08           │  ● Winter ◆ Sommer
└────────────────────┘ └────────────────────┘ └────────────────────┘
┌ Forest plot: r ± 95 %-KI  GR ●──┤  Zürich ├─●─┤  Bern ├●──┤   (+ Zeile "bereinigt" nếu adjust ≠ none)
```
- **Pixel-Matrix Kanton × Verspätung (mới 07/11/2026, user; Evidenz 1; sửa trục cùng ngày):** **trục y = 24 kanton** (sắp theo tổng Logiernächte, lớn nhất ở trên; GR, ZH, BE in đậm = HR5), **trục x = Verspätung** (tỷ lệ Halte ≥ 3 min, lớp 1 điểm %), **màu = Logiernächte** của tháng. Mỗi tháng 01/2025–07/2026 đặt một pixel trong dòng kanton của nó tại lớp độ trễ của tháng đó; nhiều tháng cùng pixel → màu = trung bình, hover liệt kê tháng + số đêm. Nút «Logiernächte absolut» (mặc định, thang sequential log) / «relativ zum Kantonsmittel» (diverging xanh ÷ ↔ đỏ ×, log2 so với trung bình của kanton → thấy mùa trong một dòng). Nếu H5 đúng: pixel sáng/đỏ nằm bên phải trong dòng. Pixel có độ trễ thật (01/2025) viền `--accent`; Spearman r chỉ trên giá trị thật (n = 24, sơ bộ r = 0.08). Đêm lưu trú thật (HESTA Gemeinde, cộng theo kanton); độ trễ các tháng khác là **mẫu** (hồ sơ mùa của mạng × liên hệ du lịch vừa phải) cho tới US-15 — **xu hướng đỏ-bên-phải ở chế độ «relativ» là do mô hình mẫu, không phải kết quả**. GE và SH bị loại (< 50 % Halte có giờ thật). Dữ liệu: `shared/make_canton_lq.py` → `canton_lq.js` (`monthly`).
- **Standortquotient je Kanton (mới 07/11/2026, user; nay Evidenz 4, trước I1/I3):** dumbbell, một dòng mỗi kanton (26, sắp theo LQ Logiernächte), trục x log với đường 1 = trung bình CH. **Xanh (`cat-1`, tròn) = Verspätung**: tỷ lệ Halte ≥ 3 min của kanton ÷ tỷ lệ CH (cơ sở = Halte có giờ thật). **Cam (`cat-2`, thoi) = Logiernächte**: tỷ phần đêm lưu trú ÷ tỷ phần Halte, tức cường độ du lịch so với khối lượng giao thông. Chú thích là «Verspätung / Logiernächte» (không phải Sommer/Winter — màu ở đây là biến, không phải mùa). Vòng rỗng = < 50 % Halte có giờ thật (GE 2 %, SH 6 % ở 01/2025) → không tính vào Spearman r; GR, ZH, BE in đậm (HR5). Dữ liệu thật tháng 01/2025: Ist-Daten history + HESTA Gemeinde (_101, chỉ các xã có trong bảng → cận dưới). Kết quả sơ bộ: r = 0.08 (n = 24). Prototype tạo dữ liệu bằng `shared/make_canton_lq.py` → `shared/canton_lq.js`; trong app sẽ thành service riêng (cùng nguồn với bản đồ kanton US-30).
- Mỗi panel có trục x riêng (thang số đêm khác nhau rất nhiều), trục y chung để so được độ trễ.
- Ghi chú "Saisonaler Störfaktor" + toggle `adjust` (keine | Neuschnee herausgerechnet | saisonbereinigt).
- **Rule editor H5:** Städte (multi-select tối đa 5 xã), Verspätungsmass (Ø | Anteil ≥ 3 min), Bereinigung, KI-Trennung verlangt.

### 2.8 RuleEditor · VariantList · SweepStrip (user-in-the-loop, SYSTEM-DESIGN §3.4)
```
┌ Regeln ─────────────────────────── 2 geändert ┐
│ REGEL                                          │
│ Neuschnee ab        [ 10 ] cm  ●━━━━━○──── (Standard 5)   ← giá trị khác chuẩn: chấm ● accent
│ Vortag zählt        [✓]                         │            + "(Standard 5)" + nút ↺ từng dòng
│ Starkverspätung     (•) Anteil Stationen        │
│                     ( ) Ø Verspätung            │
│                     ( ) Anteil Halte ≥ 3 min    │
│   > Ankünfte ≥ 3 min [ 5 ] · Anteil > [50] %    │  ← tham số phụ thuộc mode, thụt lề
│ ENTSCHEIDUNG                                    │
│ Mehrheit            [ 50 ] %                    │
│ [↺ Standard]                [Als Variante speichern…]│
└─────────────────────────────────────────────────┘
┌ Varianten (3) ──────────────────────────────────┐
│ ● Standard (HR)                  ✓ gestützt     │
│ ★ Neuschnee ≥ 10 cm  · Mai · 15.10.  ✕         │  [Laden] [★] [⋯ Umbenennen / Löschen]
│   Ø Verspätung > 3 min · Lukas      ✓           │
│   ↳ abgeleitet von "Neuschnee ≥ 10 cm"          │
└─────────────────────────────────────────────────┘
┌ Robustheit: [Neuschnee ab ▾]  3 ✓ · 5 ✓ · 10 ✕ · 20 ✕   (Standard = 5, viền) ┐
```
- Control được sinh từ `GET /hypotheses/{code}/parameters` (D20): `integer/number` → ô số + slider (min/max/step), `boolean` → switch, `enum` → radio (≤ 3 lựa chọn) hoặc select, `month` → hai select tháng, `multi_select` → chips. Nhóm theo `group`: Daten · Regel · Entscheidung. `visible_when` → ẩn hoặc hiện theo mode.
- Đổi giá trị → debounce 400 ms → URL cập nhật → kết quả được tính lại. Giá trị không hợp lệ → viền `--critical` + thông báo dưới ô; không gửi request.
- **Speichern…** mở modal: Name (bắt buộc, ≤ 80), Notiz, Autor (chỉ khi local), ★. 409 trùng tham số → "Diese Regeln sind bereits als «…» gespeichert" + nút "Laden".
- **VariantList:** Standard luôn đứng đầu và không xóa được. Biến thể "veraltet" bị làm mờ và chỉ đọc được. "Laden" đặt `?rule_set=id`. Chỉnh một biến thể đã lưu rồi lưu lại → tạo bản mới (hiện "↳ abgeleitet von").
- **SweepStrip:** chọn một tham số `sweepable`. Hiện một hàng chip theo giá trị, mỗi chip có icon kết luận; chip chuẩn có viền. Click chip → áp giá trị đó vào RuleEditor.

### 2.9 Kỹ thuật trực quan hóa đã chọn (user chọn 06/11/2026 từ `prototypes/10-vis-optionen.html`)
Bổ sung cho các wireframe ở trên; **không thay thế** biểu đồ đã có (✓ trong ma trận của `10-vis-optionen.html`). Chương = Kap. 3 của slide (3.1 Coordinated Views · 3.2 Small Multiples · 3.3 Pixel · 3.4 Kompakt / platzfüllend · 3.5 Interleaving). Ưu tiên: **Should** làm trong Sprint B; **Could** chỉ làm khi còn thời gian (có thể cắt, không ảnh hưởng kết luận H1–H5).

| ID | Trang | Kỹ thuật | Ưu tiên | Biểu đồ | Nội dung (theo thẻ prototype) | Rủi ro / điều kiện |
|---|---|---|---|---|---|---|
| D3 | `/` Datenüberblick | 3.2 | Could | Netzkarte als Small Multiples | 6 bản đồ nhỏ, cùng 3 lớp Pünktlichkeit như Netzkarte (US-29); so sánh Winter ↔ Sommer cạnh nhau thay cho animation | Cần các tháng của US-15; không có bản đồ nền |
| D4 | `/` Datenüberblick | 3.4 | Could | Quellmärkte als Treemap | Diện tích = Logiernächte, Region → top 5 Herkunftsländer + Übrige; cho thấy phần Inland (~49 %) mà biểu đồ thanh bỏ đi; click vùng = zoom | Diện tích khó so sánh chính xác → chỉ **bổ sung** cho biểu đồ thanh Quellmärkte (US-28 AC2) |
| S1 | `/h2` | 3.2 | **Should** | LQ-Kachelkarten 3 Länder × 2 Saisons | Tile map LQ: CN · DE · GB × Sommer · Winter; các vùng mà H2 nêu được viền + ghi nhãn (CN Sommer ở LU/BE, DE/GB Winter ở GR/VS) | Bổ sung cho LQ-Heatmap (§2.4), không thay thế |
| S2 | `/h2` | 3.5 | Could | Gästeflüsse: Parallel Edge Splatting + Interleaving | Mỗi tháng một dải bipartite Herkunftsland → Region, độ dày/độ đậm = tỷ lệ khách của nước đó vào vùng trong tháng (< 3 % ẩn); nút «Nebeneinander / Interleaved» | Chỗ duy nhất trong dự án có đồ thị có trọng số thay đổi theo thời gian; ghi rõ là khám phá |
| A1 | `/h3` | 3.3 + 3.1 | **Should** | Pixel-Matrix: GR-Stationen × Wintertage + ΔHS Davos | Hàng trên: Neuschnee thật ở Davos, ▼ = Starkverspätungstag (HR3); bên dưới: mỗi ga GR (sắp theo độ cao) × ngày. Trả lời: ngày trễ nặng ảnh hưởng cả vùng hay chỉ vài ga núi? Click ngày = Detail (liên kết với bảng chi tiết ngày §2.5) | Cần Ist-Daten 11/2025–04/2026 (US-15) |
| A2 | `/h3` | 3.1 | Could | Overview + Detail mit Range-Slider | Cả mùa đông ở dưới làm overview, phía trên là cửa sổ đã chọn; từng ngày đọc được cả trên điện thoại | Plotly `rangeslider`, công sức thấp |
| N1 | `/h4` | 3.2 + 3.4 | **Should** | Small Multiples je Bergstation | 12 ga > 1000 m được phục vụ nhiều nhất, sắp theo độ cao, **chung trục y**: hiệu ứng có ở mọi ga hay vài ga kéo trung bình? | Ít ngày Neuschnee mỗi ga → luôn hiện `n` |
| N2 | `/h4` | 3.1 | Could | Linking: Box-Plot ↔ Karte | Click một box → tô sáng tứ phân vị trên của nó trên bản đồ: ga nào trễ nhiều nhất nằm ở đâu? | Thêm bản đồ thứ hai trên trang (dùng lại bản đồ ngữ cảnh US-26) |
| I1 | `/h5` | 3.1 | **Should** | SPLOM: Monat × Einheit | Logiernächte, Verspätung, Neuschneetage, Ausfälle từng cặp; màu + hình dạng = mùa. Cho thấy yếu tố gây nhiễu theo mùa → lý do của công tắc «Bereinigung» (US-25) | Đầy đủ chỉ trên desktop; mobile = chọn một cặp. Plotly `splom` cần WebGL → nếu cần thì vẽ SVG như prototype |
| I3 | `/h5` | 3.2 | Could | Alle Einheiten, sortiert nach Logiernächten | Small multiples «ordered by a quantitative variable»: đặt «GR stärker als Städte» vào bối cảnh; chỉ GR, Zürich, Bern tính cho HR5 (được đánh dấu) | Ngoài HR5 → gắn nhãn **explorativ** |
| O1 | `/hypothesen` · `/quality` | 3.3 + 3.4 | Could | Datenstand-Streifen | Nguồn × tháng trong một dải hẹp (vd. trong mỗi chương của `/hypothesen`): sáng = đã nạp, xanh = một phần, đỏ = thiếu, xám = chưa công bố (cùng ngữ nghĩa với US-04) | — |

**Prototype (07/11/2026):** cả 11 biểu đồ đã được đưa vào các trang prototype, mỗi biểu đồ là một VizCard riêng có nhãn «Beispiel» khi dữ liệu là mẫu (nhãn `ID · chương · Should/Could` đã bỏ 07/11/2026 — xem quy tắc bên dưới): `00-daten.html` (D3 ngay sau Netzkarte, D4 ngay sau Quellmärkte), `00-hypothesen.html` (O1 dưới thẻ Datenstand ở đầu trang — **một** dải cho cả trang, không lặp lại ở từng chương), `02-h2.html` (S1, S2 có nút «Nebeneinander / Interleaved»), `03-h3.html` (A1 với click ngày → ga mạnh nhất, A2), `04-h4.html` (N1, N2), `05-h5.html` (I1, I3) — ở trang giả thuyết chúng là các bước Evidenz cuối cùng (sau biểu đồ có sẵn, trước Urteil). `/quality` chưa có prototype → O1 ở đó chỉ trong spec. Mã vẽ dùng chung: `shared/vis.js` (`VIS.drawXX`, `VIS.sections(specs)`, `VIS.mount(specs)`), cùng nguồn với `10-vis-optionen.html`.
**Quy tắc nội dung hiển thị (07/11/2026, user):** prototype và app **không** hiện mã nội bộ cho người dùng — không US-xx, không MoSCoW (Must/Should/Could/Won't), không mã quy tắc/quyết định (HR1–HR7, BR1–BR6, Dxx), không ID biểu đồ (D3, S1 …), không tên bảng/script (`dim_station`, `make_canton_lq.py`) và không tham chiếu tài liệu (UI-SPEC §…). Định nghĩa vẫn được nêu bằng lời («Neuschnee = ΔHS ≥ 5 cm»), mã chỉ còn trong tài liệu và comment code. Ngoại lệ: `10-vis-optionen.html` (bảng quyết định, giữ Should/Could và số slide).
**Không chọn** (giữ trong `10-vis-optionen.html` làm hồ sơ, không implement): D1, D2, D5, P1–P3, S3, I2, O2 và phần Won't (Hilbert ↔ Kalender).
**Quy tắc chung khi implement:** dữ liệu từ `registry.compute` / service, không tính trong callback (SYSTEM-DESIGN §3.3); chú thích nguồn + đơn vị (BR3); ≤ 3 màu + hình dạng trên bản đồ; `source = history` cho độ trễ (BR6); thẻ prototype dùng dữ liệu mẫu cho độ trễ theo ngày → trong app chỉ dữ liệu thật, khoảng trống = "nicht geladen".

## 3. Tương tác chuẩn
| Thao tác | Hiệu ứng |
|---|---|
| Đổi tham số trong RuleEditor | URL query cập nhật; Ergebnis có thêm dòng "Variante"; biểu đồ vẽ lại theo biến thể + đường tham chiếu chuẩn; Bedingungen có cột Variante; chip "n geändert" |
| ↺ ở một dòng / "↺ Standard" | Trả tham số đó / tất cả về chuẩn; khi hết khác biệt thì dòng Variante biến mất |
| Als Variante speichern | `POST …/rule-sets`; toast "Gespeichert"; mục mới ở đầu VariantList (sau Standard) |
| Laden (VariantList) | `?rule_set=id`; RuleEditor lấy giá trị của biến thể |
| ★ / Umbenennen / Löschen | `PATCH` / `PATCH` / `DELETE` (soft); Löschen có xác nhận và nút "Rückgängig" trong toast 5 s |
| Click chip Robustheit | Áp giá trị vào RuleEditor (như tự nhập) |
| Hover điểm/ô/ngày | Tooltip: giá trị + đơn vị + (với H3) ngày, HN, tỷ lệ; nhắc nguồn ở chân biểu đồ |
| Click ngày (H3) | Panel "Tag gewählt" (`tables/top_stations?date=`) |
| Click vùng trên biplot (H1) | Highlight vùng đó trong heatmap loadings/bảng; mở segmented control của vùng trong RuleEditor |
| CSV ↓ | `GET …/tables/{table}?format=csv` với cùng tham số |
| PNG | Nút trên thanh công cụ Plotly; tên file `H<n>_<view>_<YYYY-MM-DD>.png`, scale 2 |
| Thẻ trên `/hypothesen` | Mở `/hN` với quy tắc chuẩn |
| `/`: đổi Zeitraum/Region | URL cập nhật; KPI + Trends tính lại; Kalender/Auffälligkeiten theo Zeitraum |
| `/`: click ngày trong Kalender | Dòng tương ứng trong Auffälligkeiten được tô sáng và cuộn tới |
| `/`: click vùng trong Saisonmuster (Neuschnee) | Đặt bộ lọc Region = vùng đó |
| `/`: click ga trên Netzkarte | Đặt bộ lọc Region = vùng du lịch của ga; bản đồ zoom vừa vùng; toast |
| `/`: zoom Netzkarte ≥ 9.5 | Hiện mọi ga (không còn ngưỡng Halte/Tag) |
| Cuộn trang (desktop) | Ô của phần đang xem trên Section rail chuyển sang màu accent và lớn hơn; các phần đã qua tối, các phần sau nhạt |
| Hover / focus ô trên Section rail | Hiện nhãn của phần (thẻ sáng bên trái ô) |
| Click / Enter ô trên Section rail | Cuộn tới phần đó (smooth, trừ khi `prefers-reduced-motion`); tiêu đề không bị navbar che (`scroll-margin-top` 72 px) |
| `/`: link "→ Hn" ở góc panel | Mở `/hN` với quy tắc chuẩn |

## 4. Design tokens (`assets/tokens.css`, prototype: `prototypes/shared/styles.css`)

**Theme có thể đổi (23/10/2026, prototype):** mọi màu nằm trong `prototypes/shared/themes/<id>.css`; `styles.css` chỉ dùng token (không có mã màu), biểu đồ Plotly đọc màu từ token CSS (`SF.C`/`SF.D` trong `app.js`: `--chart-*`, `--cat-*`, `--seq-*`). `shared/theme.js` (nạp ngay sau `styles.css` trên mọi trang) chọn theme theo `?theme=<id>` hoặc lựa chọn đã lưu trong trình duyệt; navbar có ô «Farbschema» để so sánh (chỉ trong prototype). Theme mới = sao chép `canopy-citron.css`, đổi giá trị, thêm vào `THEMES` trong `theme.js`, chạy lại palette validator trên nền biểu đồ mới. Theme đã lưu: **`carbon-mint` — «Carbon Mint»** (mặc định từ 23/10/2026) và hai lựa chọn thay thế: **`canopy-citron` — «Canopy & Citron»**, **`peach-indigo` — «Peach & Indigo»**.

**Peach & Indigo (23/10/2026, nguồn sự thật: `prototypes/shared/themes/peach-indigo.css`):** human-centric. Nền trang Cream `#FFF8F0` (chuyển rất nhẹ sang lavender `#f3effa` ở cuối trang), chữ trên nền Deep Indigo `#2B2D42` 12.8:1 (ink-2 `#4a4c6a` 7.9:1, muted `#5d5f7e` 5.9:1). Navbar, thẻ thông tin, modal = Deep Indigo `#2B2D42` (`--surface-2 #383a55`); thẻ biểu đồ "screen" indigo sâu hơn `#1d1e2e` (mini `#181926`). **Soft Peach `#FF9E7D`** = accent chỉ trên nền tối (6.7:1 trên indigo; trên cream chỉ 1.9:1 → nút chính trên cream = nền indigo, chữ peach). **Dusty Lavender `#B8B5D6`** = chữ phụ (muted) trong thẻ indigo (6.8:1) và dải «Selbst testen» (chữ indigo 6.8:1, thẻ bên trong indigo + peach). Tuyết rơi màu lavender `#a9a6c9`. 8 màu categorical giữ nguyên, validator trên `#1d1e2e` và `#181926`: ALL PASS (mọi màu ≥ 3:1; trên `#2B2D42` thì `#008300` chỉ 2.73:1 → biểu đồ luôn nằm trong thẻ biểu đồ, không trên thẻ thông tin); other `#6f7088`.

**Carbon Mint (23/10/2026, nguồn sự thật: `prototypes/shared/themes/carbon-mint.css`):** dark tech UI. Nền trang Carbon Anthracite `#1A1D20` (vầng sáng violet/mint rất nhẹ ở đầu trang), thẻ thông tin/navbar/modal Slate Navy `#2C353F` (`--surface-2 #36414c`), thẻ biểu đồ "screen" tối hơn `#14171a` (mini `#101214`), chữ Warm Off-White `#F4F6F8`. **Digital Mint `#00FFC2`** = accent/highlight (mục nav hiện tại, chip đang chọn, biến thể, accent biểu đồ, ô H2 được nêu), chữ trên mint `#1A1D20` 13:1. **Electric Pulse Violet `#635BFF`** = điều khiển tương tác dạng nền (nút chính, switch, slider, segmented control; chữ trắng 4.7:1, có glow nhẹ); link dùng bậc sáng `#a9a4ff` vì violet gốc làm chữ chỉ 2.7:1 trên thẻ. Tương phản trên `#2C353F`: ink 11.5:1, ink-2 `#c3cbd3` 7.6:1, muted `#a8b2bd` 5.8:1 (4.8:1 trên surface-2), mint 9.5:1, link 5.6:1. Khối «Selbst testen» = dải `#25233f` (carbon pha violet). 8 màu categorical giữ nguyên, validator trên `#14171a`, `#101214`, `#1A1D20`: ALL PASS (mọi màu ≥ 3:1); other `#6f7a86`. Glow tĩnh (không animation) trên nav hiện tại, rail, nút hỏi, mã chương.

**Canopy & Citron (23/10/2026, nguồn sự thật: `prototypes/shared/themes/canopy-citron.css`):** nền trang linen `#EAE4D9` (token sáng trên `body`: `--ink #10291a` · `--ink-2 #1A4D2E` · `--muted #364E59` · `--accent #1A4D2E`, chữ trên accent `#DFFF00`). Thẻ tối (`:root`, `.navy-scope`, `.card`): `--surface #1A4D2E` · `--surface-2 #235c39` · `--ink #f3efe7` · `--ink-2 #d3dccf` · `--muted #b4c8ba` · `--grid #2c6343` · `--axis #4d7f61` · `--border rgba(234,228,217,.16)` · `--accent/--link/--focus #DFFF00` (chữ trên accent `#1A4D2E`) · `--v-rejected #ffb3b3`. **Biểu đồ** (`.viz-card`, `.screen-card`, `SF.C`/`SF.D`): nền `#142026` (Inchyra tối; nền "screen" mini `#0f191e`), surface-2/hover `#22323a`, grid `#24343c`, axis `#3b525d`, ink `#f3efe7`, ink-2 `#c9d3d6`, muted `#9fb1b8`, other `#6b7f88`, accent biểu đồ (biến thể, ngày nổi bật, viền ô H2) `#DFFF00`. 8 màu categorical giữ nguyên; validator chạy lại trên `#142026` và `#0f191e`: ALL PASS (CVD tệ nhất ΔE 8.4, normal ΔE 19.3, mọi màu ≥ 3:1). Không đặt biểu đồ trực tiếp lên nền canopy (5/8 màu < 3:1). Đoạn dưới là navy theme cũ (lịch sử):

**Navy theme (20/10/2026, đã thay 23/10/2026):** `--page #0d0b25` · `--surface #171547` · `--surface-2 #221f5c` · `--chart #0a092b` · `--ink #f4f3ff` · `--ink-2 #c9c6ea` · `--muted #9b97c9` · `--grid #2e2a52` · `--axis #4a4685` · `--border rgba(220,214,255,.14)` · `--accent #dcd6ff` (chữ trên accent `#0d0b25`) · `--link #b9b0ff` · status `--good #7ee07e` `--warning #f5c451` `--critical #ff9b9b` (nền badge 14 % alpha). Tương phản WCAG đã đo: ink 15.5:1, ink-2 10.3:1, muted 6.2:1 trên `--surface` (5.4:1 trên `--surface-2`); mọi màu chữ ≥ 4.5:1. **Biểu đồ:** 8 màu categorical dark giữ nguyên (`#3987e5 #d95926 #199e70 #c98500 #d55181 #008300 #9085e9 #e66767`), validator chạy lại trên `#0a092b` và `#171547`: ALL PASS (CVD tệ nhất ΔE 8.4, normal ΔE 19.3, mọi màu ≥ 3:1). Khung biểu đồ: nền `#0a092b`, grid `#24214f`, axis `#3d3970`, hover `#1d1a52`, other `#6e6a99`, accent biểu đồ (biến thể, ngày nổi bật) `#b9b0ff`; sequential/diverging không đổi (giá trị thấp chìm vào nền; midpoint diverging xám trung tính). Phần dưới đây là bảng token cũ (light, 30/09 + bản 2) để tham khảo; tên token giữ nguyên.

Giữ nguyên bảng màu đã chốt 30/09/2026 (đã kiểm bằng palette validator). Bản sao cho Plotly: `app/components/palette.py`. Bổ sung cho bản 2:

```css
:root {
  /* (giữ nguyên) --page --surface --surface-2 --ink --ink-2 --muted --grid --axis --border --focus
     --accent --brand · --cat-1…8 --other · --seq-100…700 · --div-neg/mid/pos
     --good --warning --serious --critical · font, spacing, radius, shadow */

  /* Kết luận (HR7) — status: luôn có icon + chữ */
  --v-supported: var(--good);        /* ✓ gestützt */
  --v-rejected:  var(--critical);    /* ✕ nicht gestützt */
  --v-unknown:   var(--muted);       /* ? unzureichende Daten */
  --v-supported-bg: #e7f6e7; --v-rejected-bg: #fbeaea; --v-unknown-bg: #f1f0ec;

  /* Chuẩn vs biến thể — KHÔNG phải status */
  --rule-standard: var(--ink-2);     /* đường/ngưỡng chuẩn: 1 px, nét đứt (ngưỡng) */
  --rule-variant:  var(--accent);    /* giá trị khác chuẩn, đường ngưỡng biến thể: 2 px */

  /* Ngữ nghĩa dữ liệu */
  --season-winter-bg: #eef3fa;       /* dải nền tháng mùa đông (HR1) */
  --h1-swiss: var(--cat-1); --h1-intl: var(--cat-2); --h1-other: var(--other);

  /* Thẻ "màn hình tối" trên trang tổng quan — dark steps, đã kiểm bằng validator trên #141413 (PASS) */
  --screen-bg: #141413; --screen-plot: #0d0d0c; --screen-ink: #f0efec; --screen-ink-2: #c3c2b7;
  --screen-muted: #9a998f; --screen-grid: #2c2c2a; --screen-axis: #383835; --screen-link: #86b6ef;
  --screen-cat-1: #3987e5; --screen-cat-2: #d95926; --screen-cat-3: #199e70; --screen-other: #6b6a65;
  /* badge trên nền tối: chữ #7ee07e / #ff9b9b trên nền status 18–22 % alpha */

  /* VizCard (thẻ biểu đồ trên mọi trang) — token được định nghĩa lại TRONG thẻ, nên chữ/component tự đổi màu */
  .viz-card { --surface: #141413; --surface-2: #232321; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #9a998f;
              --grid: #2c2c2a; --axis: #383835; --accent: #86b6ef; --v-supported: #6fdc6f; --v-rejected-text: #ff9b9b; }
  /* Plotly trong VizCard (palette.py → DARK): nền #141413, categorical #3987e5 #d95926 #199e70 #c98500 #d55181 #008300 #9085e9 #e66767,
     other #6b6a65; sequential đảo chiều (#0d366b thấp → #cde2fb cao, giá trị nhỏ chìm vào nền);
     diverging #3987e5 ↔ #383835 ↔ #e66767; mùa đông rgba(57,135,229,.14); hover nền #232321 */
  --snow-day: var(--seq-500); --snow-none: var(--seq-200);
  --heavy-day: var(--accent);
}
```
**Quy tắc màu:**
- Kết luận dùng status token (✓/✕/?) cho badge, thẻ và chấm trên nav. Status token không được dùng cho series.
- Nhóm và series dùng categorical theo thứ tự cố định: H1 nhóm CH = slot 1, Int. = slot 2, còn lại = `--other`; H5 mùa: Winter/Sommer = hình dạng + slot 1/2.
- LQ (H2) dùng diverging quanh 1. Snow/số đêm dùng sequential.
- Không dùng trục kép (H3 dùng hai biểu đồ cùng trục x).
- Biểu đồ luôn nằm trong `VizCard` và dùng bộ màu tối (đã kiểm bằng validator trên #141413).
- Mỗi biểu đồ có tiêu đề, đơn vị và dòng nguồn (BR3). Độ trễ luôn ghi "Quelle: Ist-Daten (history), opentransportdata.swiss" (BR6).

**Typography (sửa 20/10/2026):** Google Fonts `Space Grotesk` (700, letter-spacing −0.02em; tiêu đề trang 36–48 px, logo, mã H trên trang `/hN` 48–60 px, tiêu đề «Selbst testen» 28–42 px; thay Handjet ngày 20/10/2026 vì font pixel khó đọc với tiêu đề dài), `Quicksand` (400–700; thân 15 px, weight 500), `Inconsolata` (400–700; class `.num`, số KPI, bảng số, nhãn section/eyebrow, chú thích nguồn, ô câu hỏi, mọi chữ trong Plotly). Fallback system font khi offline. Câu giả thuyết `--fs-lg` 18 px in nghiêng; key metric 32–40 px; chú thích 12 px. ~~Chỉ dùng system font~~ (quyết định cũ, thay 20/10/2026).

## 5. Component (Dash, `app/components/`)
| Component | Loại | Dùng ở | Ghi chú |
|---|---|---|---|
| `AppShell` (NavBar có chấm kết luận, mobile menu, H-switcher) | layout | tất cả | |
| `SectionRail` | navigation | `/`, `/h1`…`/h5` | Đọc mọi phần có `data-rail="Nhãn"` (≥ 3 phần mới hiện). `position: fixed`, phải 20 px, giữa chiều cao. Ô 10 px (bo 3 px): đã qua `--ink-2`, hiện tại `--accent` 16 px, phía sau `--axis`; hover: chỉ còn viền. Nhãn: thẻ sáng (`--surface`, border, shadow, 13 px đậm) bên trái ô, đọc được cả trên VizCard tối. Phần hiện tại = phần cuối cùng có mép trên đã qua 35 % chiều cao màn hình (cuối trang → phần cuối). Chỉ ≥ 1024 px; viewport < 1400 px thì `main` có `padding-right` 56 px để rail không đè lên thẻ. Dash: `assets/rail.js` (JS thuần, không cần callback) + thuộc tính `data-rail` trên section; không có trạng thái server. |
| `HypothesisCard` (dark screen) + `MiniChart` | card | `/` | badge, mini chart, key metric, missing data, số biến thể; `MiniChart` dùng `palette.DARK` (thêm vào `palette.py`) |
| `StatusSummary`, `ReportButton` | panel | `/` | |
| `MonthRangeFilter`, `RegionSelect` (chỉ trong `/`) | control | `/` | trạng thái trong URL, không ảnh hưởng `/hN` (D16) |
| `KpiTile` + `Sparkline` (Δ YoY, tháng so sánh trong tooltip) | atom | `/` | sparkline có khoảng trống |
| `TrendSmallMultiples`, `CalendarHeatmap`, `RegionMonthHeatmap`, `MarketBars` | chart (VizCard) | `/` | |
| `AnomalyTable` (top 15, CSV) | table | `/` | ghi chú "explorativ – nicht HR3" |
| `NetworkMap` (US-29) | chart (VizCard) | `/` | `Scattermap` + `carto-darkmatter`; dữ liệu từ `services/overview.network()`; 3 lớp màu + vòng rỗng; link 3 độ dày |
| `HypothesisHeader` (mã, chủ đề, câu giả thuyết) | layout | `/hN` | thay bằng `QuestionBar` (20/10/2026) |
| `QuestionBar` (ô tìm kiếm, câu hỏi gõ từng ký tự, nút ↓) · `StoryStep` (eyebrow "Evidenz i / n", hiện dần) · `VariantBar` (cố định, khi có biến thể) | layout | `/hN` | §2.2; JS `assets/story.js` |
| `VizCard` (thẻ tối bọc mọi biểu đồ: tiêu đề, chú thích, legend, chart, nguồn) | layout | `/hN`, `/` | dùng `palette.DARK` cho Plotly; chỉ biểu đồ nằm trong VizCard |
| `ResultCompare` (Standard / Variante) | panel | `/hN` | `aria-live="polite"` khi kết luận đổi |
| `VerdictBadge` | atom | mọi nơi | icon + chữ; size sm/md |
| `KeyMetric` / `KpiTile` | atom | `/hN`, `/` | `KpiTile` đã có (US-04) |
| `RuleEditor` + controls `NumberField`, `Switch`, `RadioGroup`, `MonthRange`, `ChipSelect`, `SegmentedGroup` (H1) | form | `/hN` | sinh từ descriptors (D20) |
| `ChangedChip` ("2 geändert"), `ResetButton` | atom | RuleEditor, mobile accordion | |
| `SaveVariantModal`, `VariantList`, `SweepStrip` | panel/modal | `/hN` | |
| `ConditionTable` (Standard / Variante) | table | `/hN` | ✓/✕/– cùng giá trị |
| `DefinitionsBox`, `DataBasis`, `SourceFootnote` | text | `/hN` | `SourceFootnote` đã có |
| `ExportBar` (CSV, Bericht) | atom | `/hN` | PNG qua modebar Plotly |
| `MissingDataNotice` | panel | `/`, `/hN` | thay biểu đồ khi `unzureichende_daten` |
| Biểu đồ H1: `PcaBiplot`, `VarianceBars`, `LoadingsBars`, `StabilityStrip` | chart | `/h1` | |
| Biểu đồ H2: `LqHeatmap`, `MonthlySmallMultiples` | chart | `/h2` | |
| Biểu đồ H3: `DayShareTimeline`, `SnowBars` (trục x chung), `Crosstab2x2`, `DayDetail` | chart/table | `/h3` | |
| Biểu đồ H4: `QuantileBoxes` ×3, `EffectTable`, `YoYScatter`, `DistanceHistogram` | chart | `/h4` | |
| Biểu đồ H5: `UnitScatterGrid`, `ForestPlot` | chart | `/h5` | |
| `EmptyState`, `LoadingOverlay`, `ErrorToast`, `Toast` (Undo) | tiện ích | tất cả | |

**Trạng thái bắt buộc:**
- **loading:** skeleton cho Ergebnis; biểu đồ giữ dữ liệu cũ và mờ đi.
- **unzureichende Daten:** `MissingDataNotice` liệt kê dữ liệu còn thiếu + link `/quality`; RuleEditor vẫn dùng được.
- **error:** toast + nút "Erneut versuchen".
- **biến thể veraltet:** chỉ đọc.
- **validation:** lỗi hiện ngay dưới ô.

## 6. Accessibility
- Kết luận không bao giờ chỉ được thể hiện bằng màu: luôn có icon + chữ.
- Nhóm trên scatter có cả hình dạng và màu.
- Mọi control dùng được bằng bàn phím, focus ring `--focus` 2 px. Slider luôn đi kèm ô số.
- Section rail: `<nav aria-label="Abschnitte">` với `<button aria-label="Zu «…»">`, ô hiện tại có `aria-current="true"`, nhãn hiện cả khi focus bằng bàn phím, vùng bấm 22 px. Rail chỉ là lối tắt: mọi phần vẫn tới được bằng cuộn, và trang không phụ thuộc vào rail.
- Mỗi biểu đồ có thể xem dưới dạng bảng (CSV / nút "Tabelle"). Tooltip không phải là nơi duy nhất chứa thông tin.
- Độ tương phản của chữ ≥ 4.5:1 trên `--surface`.

## 7. Prototype (`prototypes/`)
| File | Nội dung | Trạng thái |
|---|---|---|
| `index.html` | Danh mục prototype | ✅ |
| `00-daten.html` | **Trang chủ `/` Datenüberblick** (US-27/28/29): KPI + sparkline + Δ YoY, **Netzkarte**, Trends 4 hàng, Kalender + Auffälligkeiten (D23), Saisonmuster, Quellmärkte. Nút chuyển "Vorschau" (bổ sung dữ liệu mẫu) / "Nur echte" (trạng thái thật: 2/21 tháng) | ✅ vòng 3 · Netzkarte vòng 1 (20/10/2026, chờ duyệt) |
| `shared/net.js` (tạo bằng `make_net_data.py`) | Netzkarte. **Dữ liệu thật:** 14 585 ga CH có ≥ 40 Halte/Tag (vị trí, vùng, độ cao từ `dim_station`), Halte, Pünktlichkeit, hủy chuyến theo tháng đã nạp (Ist-Daten history). **Dữ liệu mẫu:** link + Verkehrsmittel (láng giềng gần nhất; "giống ga tàu" = 850xxxx và tên không có dấu phẩy), chỉ hiện ở "Vorschau" | ✅ |
| `00-hypothesen.html` (trước đây `00-overview.html`) | Tổng quan Hypothesen `/hypothesen` với thẻ "màn hình tối" + mini chart | ✅ vòng 2 |
| `01-h1.html` | H1: biplot, varianz, loadings, ổn định; PCA tính lại trong trình duyệt từ dữ liệu HESTA thật | ✅ vòng 2 |
| `02-h2.html` | H2: heatmap LQ, small multiples theo tháng; LQ tính lại từ HESTA thật | ✅ vòng 2 |
| `03-h3.html` | H3: Ergebnis, timeline + tuyết, bảng chéo, chi tiết ngày | ✅ vòng 1, chuyển sang `hpage.js` ở vòng 2 |
| `04-h4.html` | H4: 3 box plot từ quantile + CI, scatter YoY (HESTA thật), loại trừ + histogram khoảng cách | ✅ vòng 2 |
| `05-h5.html` | H5: scatter từng đơn vị (chung trục y), forest plot, chọn thành phố, điều chỉnh mùa/tuyết | ✅ vòng 2 |
| `shared/hpage.js` | Khung chung của trang giả thuyết, **dạng câu chuyện** (§2.2, 20/10/2026): Frage (gõ vào ô tìm kiếm) → Antwort → Evidenz-Schritte → Urteil → Definitionen → Selbst testen (RuleEditor sinh từ descriptor, Ergebnis, Robustheit, Varianten), URL state, VariantBar. Tương ứng 1–1 với component Dash ở §5 | ✅ vòng 3 (chờ duyệt) |
| `shared/rail.js` + CSS `.rail` trong `shared/styles.css` | `SectionRail` (§5). Đang dùng ở `00-daten.html` (7 phần: Kennzahlen, Netzkarte, Trends, Quellmärkte, Kalender, Auffälligkeiten, Saisonmuster) và `01-h1` … `05-h5` (Frage · Antwort · từng bước Evidenz · Urteil · Definitionen · Selbst testen) | ✅ vòng 1 (20/10/2026, user duyệt cho `/`) |
| `10-vis-optionen.html` | **Bảng quyết định kỹ thuật trực quan hóa** (24/10/2026, từ `docs/VIS-TECHNIKEN.md`, Kap. 3 của slide): ma trận Technik × Seite (đã có ✓ / đề xuất), 20 thẻ D1–D5, P1–P3, S1–S3, A1–A2, N1–N2, I1–I3, O1–O2, mỗi thẻ một biểu đồ chạy được (HESTA, ΔHS Davos, danh sách ga + Ist-Daten 01/2025 · 09/2026 là thật; độ trễ theo ngày là mẫu, có nhãn), lọc theo chương 3.1–3.5 / «nur Should», chọn + «Liste kopieren» (localStorage), phần Won't với sơ đồ Hilbert ↔ Kalender. SPLOM vẽ bằng SVG (Plotly `splom` cần WebGL). Chưa phải thiết kế trang — chỉ để chọn | ✅ vòng 1 · **user đã chọn 06/11/2026** (11 thẻ: D3, D4, S1, S2, A1, A2, N1, N2, I1, I3, O1 → §2.9) |
| `shared/vis.js` | **Biểu đồ của các kỹ thuật đã chọn** (07/11/2026, §2.9): mã vẽ của 20 thẻ (trích từ `10-vis-optionen.html`, IIFE → `window.VIS`), cộng `VIS.sections(specs)` (VizCard + nhãn kỹ thuật + nút chuyển) và `VIS.mount(specs)` (vẽ, nút chuyển, vẽ lại khi đổi chiều rộng). Trang giả thuyết: `evidenceHtml: … + VIS.sections(VIS_Hx)`, `afterInit: () => VIS.mount(VIS_Hx)`. Cần `data.js`, `stats.js`, Plotly; `net.js` cho D3, A1, N1, N2 (nên `03-h3`, `04-h4` giờ cũng nạp `net.js`) | ✅ |
| `shared/stats.js` | RNG có seed, Spearman, bootstrap CI, quantile, PCA (power iteration). Chỉ dùng cho prototype | ✅ |
| `shared/styles.css`, `shared/app.js`, `shared/components.html` | Token (gồm dark screen), cấu hình Tailwind, nav, badge, layout Plotly sáng/tối, thư viện component | ✅ |
| `shared/data.js` (tạo bằng `make_proto_data.py`) | **Dữ liệu thật:** HESTA (H1, H2, đêm lưu trú H4b/H5 cho 8 đơn vị), MeteoSwiss DAV (H3, ngày tuyết H4), ledger Ist-Daten (thẻ H4). **Dữ liệu mẫu:** mọi độ trễ/hủy chuyến | ✅ |

Kết luận H1/H2 trong prototype được tính bằng script nhanh, **không phải engine** (US-16/17/18). Chúng chỉ để minh họa và có nhãn "vorläufig". Kết quả sơ bộ với quy tắc chuẩn: **H1 nicht gestützt** (Wallis nằm phía "international" của PC1; PC1 giải thích 47 %), **H2 gestützt** sau khi sửa sang "oder" (15/10: CN Luzern 1.58 / Bern 1.92, DE GR 1.56, GB VS 1.41; trước đó với "und" là nicht gestützt vì DE/VS 0.68 và GB/GR 0.85). Engine phải xác nhận lại.
Mỗi trang mô phỏng engine bằng một hàm JavaScript `compute(p)` (cùng hợp đồng với `HypothesisResult`: `verdict`, `metricText`, `conds`), lưu biến thể trong `localStorage` thay cho `/rule-sets`, và giữ trạng thái trong URL (vd. `01-h1.html?groups=1:s,2:s,4:i,10:i,3:i` = bỏ Wallis khỏi nhóm CH → H1 thành *gestützt*).

**Bài học cho Dash từ prototype:** (1) biểu đồ phải vẽ/resize sau khi layout ổn định (`ResizeObserver`); (2) `<fieldset>` cần `min-width: 0`, nếu không panel quy tắc tràn trên mobile; (3) chip robustness của tham số enum cần nhãn ngắn (`chip` trong descriptor → thêm `short_label` vào `ParameterDescriptor.options`).
