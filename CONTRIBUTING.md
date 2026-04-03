# Contributing to OrangeD

Thank you for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/bianzichu-rgb/orangeD.git
cd orangeD
pip install -e ".[all]"
pip install pytest
```

## Running Tests

```bash
pytest tests/ -v
```

## How to Contribute

### Bug Reports

Open an issue with:
- What you did (PDF type, command used)
- What you expected
- What actually happened
- Your environment (OS, Python version, PyMuPDF version)

### Adding OCR/VLM Adapters

1. Subclass `BaseAdapter` in `oranged/adapters/`
2. Implement `recognize()`, `is_available()`, and optionally `recognize_table()`
3. Add tests in `tests/`
4. Update README adapter table

### Improving Extraction Quality

If you find a PDF where extraction quality is poor:
1. Run `oranged route your.pdf -v` to see routing decisions
2. Run `oranged judge output.md` to identify which dimensions score low
3. Open an issue or PR with the specific dimension and a fix

### Adding Document Types

The 9-category taxonomy in `oranged/analyse.py` is currently tuned for appliance manuals. To add support for new document types (e.g., academic papers, legal documents):
1. Add keywords to `CATEGORIES` in `analyse.py`
2. Consider new categories if needed
3. Add partition weights in `judge.py` `PARTITION_WEIGHTS`

## Code Style

- Follow existing patterns in the codebase
- Keep imports minimal — core modules should only depend on `pymupdf` and stdlib
- Type hints encouraged but not mandatory

## Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes
3. Run `pytest tests/ -v` and ensure all tests pass
4. Submit a PR with a clear description of what and why

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
