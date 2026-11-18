# Evaluation results

42 labelled files · average 65 ms per file · correct overall verdict on 41/42 files

| Check | TP | FP | FN | TN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| pages | 2 | 0 | 0 | 40 | 1.00 | 1.00 |
| size | 3 | 0 | 0 | 39 | 1.00 | 1.00 |
| bleed | 6 | 0 | 0 | 36 | 1.00 | 1.00 |
| dpi | 4 | 0 | 0 | 38 | 1.00 | 1.00 |
| colour | 5 | 0 | 1 | 36 | 1.00 | 0.83 |
| safezone | 4 | 0 | 0 | 38 | 1.00 | 1.00 |
| fonts | 3 | 0 | 0 | 39 | 1.00 | 1.00 |
| text | 6 | 0 | 1 | 35 | 1.00 | 0.86 |
| **all** | 33 | 0 | 2 | 301 | **1.00** | **0.94** |

## Misses (expected problem not reported)

- `limit_rgb_vector_background.pdf` — colour
- `limit_typo_inside_image.png` — text

## False alarms (problem reported on a fine file)

None.
