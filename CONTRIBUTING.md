# Contributing

Thanks for your interest in RXCluster.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running the tests

```bash
pytest              # all tests
pytest -q           # quiet
```

The tests are asynchronous (`pytest-asyncio`, `asyncio_mode = auto`) and cover
parsing, band/mode resolution, filters, dedup, validation, tag rendering and an
end-to-end telnet integration.

## Linting

```bash
ruff check rxcluster tests
ruff check --fix rxcluster tests
```

Style: line length 100, import sorting, `py311` target. Do not add comments to
code unless they explain non-obvious intent; keep docstrings in English.

## Project layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for the module map. In short:

- Add a new source under `rxcluster/sources/` by subclassing `SourceConnector`
  and implementing `_stream_once`.
- Add a new filter category by touching
  `rxcluster/filters/model.py`, `compiled.py` and `parser.py`.
- Add a new enrichment under `rxcluster/enrich/`.

## Guidelines

- Keep the hot path (pipeline + filter evaluation) allocation-light and free of
  blocking I/O.
- Never block the pipeline on a client; use the queue/drop-oldest model.
- Add tests for new behaviour.
- Update the relevant documentation file(s) in the same change.
- All documentation and code comments must be in English.

## Commit messages

Use short, imperative subjects (e.g. `Add patt3ch validation`). Group related
changes and avoid unrelated reformatting.

## License

By contributing you agree that your contributions are licensed under the
project's [MIT License](LICENSE).