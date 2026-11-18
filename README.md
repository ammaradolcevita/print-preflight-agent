# Print Preflight Agent

> Work in progress. Unofficial prototype, not affiliated with or endorsed by HelloPrint.

Checks print artwork (PDF, PNG, JPG) against a product's print specs and explains every problem in plain language.

```bash
pip install -e ".[dev]"
python -m preflight --list                         # products
python -m preflight my_card.pdf --product business-card
pytest -q
```

Checks so far: file, pages, size, bleed, effective dpi, colour mode.
All numbers live in `specs/print_specs.yaml`, each with its source.
