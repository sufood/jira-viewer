"""Put the toolkit source (src/) on sys.path so tests can `import apply_source`,
`import bundle_resources`, etc. The scripts live in src/; data/config stay in
the repo root, which the tests reference relative to their own location."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
