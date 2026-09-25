# Synthetic fixtures

Generated from scratch by `benchmarks/synthetic.py`. No file here is derived from a real
drawing, a customer file or any third-party dataset.

```
python benchmarks/synthetic.py --seed 20260925 --cases 3 --out tests/fixtures/synthetic
```

Each `synthetic_NNN.json` holds one case in four parts: `spec` (validates against
`mozaik_automation.models.CabinetSpec`), `extraction` (the compact form the comparator
reads), `analysis` (what a correct image analyser would report for a correct build) and
`extraction_notes`. Each `synthetic_NNN.png` is a plan view drawn from `spec` alone.

`MANIFEST.json` records the seed, the generator version, the Pillow version used for the
drawings and a SHA-256 for every file. `tests/test_synthetic_benchmark.py` regenerates the
JSON and requires it to match exactly. The PNGs are not compared byte for byte, because
font rendering can differ between Pillow versions.
