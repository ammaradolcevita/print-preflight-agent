# Real-world style set: results
**20/20 correct · 0 crashes**

| File | Expected | Verdict | OK | Check ms | Fix | Note |
|---|---|---|:-:|---:|---|---|
| `rw_canva_print_bleed.pdf` | pass | pass | ✅ | 272 | – | Canva PDF Print with bleed |
| `rw_canva_print_no_bleed.pdf` | fail | fail | ✅ | 16 | fail → pass | Canva PDF Print without bleed, colour to the edge |
| `rw_crop_marks_trimbox.pdf` | pass | pass | ✅ | 15 | – | bleed + crop marks + TrimBox |
| `rw_crop_marks_no_boxes.pdf` | pass | pass | ✅ | 15 | – | bleed + crop marks, no TrimBox |
| `rw_crop_marks_no_boxes_no_bleed.pdf` | fail | fail | ✅ | 14 | fail → pass | crop marks, no TrimBox, design stops at the cut line |
| `rw_trimbox_but_no_bleed_content.pdf` | fail | fail | ✅ | 15 | fail → pass | TrimBox says bleed, but the background stops at the cut line |
| `rw_illustrator_offset_mediabox.pdf` | pass | pass | ✅ | 15 | – | MediaBox not at 0,0; TrimBox + BleedBox |
| `rw_rotated_page.pdf` | pass | pass | ✅ | 14 | – | /Rotate 90 with TrimBox |
| `rw_word_a4.pdf` | fail | fail | ✅ | 12 | – | card drawn on an A4 page |
| `rw_two_sided.pdf` | pass | pass | ✅ | 16 | – | front + back |
| `rw_vector_only.pdf` | pass | pass | ✅ | 3 | – | no pictures at all |
| `rw_spot_colour.pdf` | warn | warn | ✅ | 21 | – | spot colour background: must not be silently 'print-ready' |
| `rw_password.pdf` | cant | fail | ✅ | 22 | – | says it cannot check |
| `rw_owner_password_only.pdf` | pass | pass | ✅ | 69 | – | opens, but permissions restricted |
| `rw_png_export.png` | fail | fail | ✅ | 6 | fail → pass | Canva PNG, RGB, no bleed |
| `rw_phone_photo.jpg` | cant | fail | ✅ | 19 | – | says it cannot check |
| `rw_square_card.pdf` | fail | fail | ✅ | 2 | – | square card for 85x55 |
| `rw_card_90x50.pdf` | fail | fail | ✅ | 1 | – | 90x50 card for 85x55 |
| `rw_large_photo.pdf` | warn | warn | ✅ | 198 | warn → pass | 10 MB uncompressed RGB photo |
| `rw_not_a_pdf.pdf` | cant | fail | ✅ | 1 | – | says it cannot check |
