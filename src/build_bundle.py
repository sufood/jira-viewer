#!/usr/bin/env python3
"""Assemble the single-file app bundle from source: the engine skeleton + vendored
resource blobs (src/engine/) + the editable app source (src/strategy-map.src.html).

This makes the bundle a *generated* build artifact — `make clean` can delete it and
this rebuilds it — so there is no separate `apply` step and no checked-in 1.5 MB
mystery file. The app source is authoritative: the skeleton carries an @@TEMPLATE@@
placeholder that this fills from strategy-map.src.html (and syncs the __PRISTINE_HTML
copy), reusing apply_source's transform.

assemble(decompose(bundle)) is byte-identical to the original bundle when --src
matches the source baked into it.

    python build_bundle.py [--engine-dir src/engine] [--src src/strategy-map.src.html]
                           [--out "Insignia AI Strategy Map - Jira linked.html"]
"""
import argparse
import base64
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_source

# Only matches the quoted resource placeholders ("@@<uuid>@@"), never the bare
# @@TEMPLATE@@ marker (which apply() fills).
PLACEHOLDER = re.compile(r'"@@([0-9a-fA-F-]{36})@@"')


def assemble(skeleton, vendor_dir, src_text):
    def _sub(m):
        uuid = m.group(1)
        with open(os.path.join(vendor_dir, uuid), "rb") as f:
            raw = f.read()
        return '"' + base64.b64encode(raw).decode() + '"'
    html = PLACEHOLDER.sub(_sub, skeleton)
    # The template block is now @@TEMPLATE@@; apply() replaces it with the source
    # and rewrites the authoring __PRISTINE_HTML copy from the same source.
    return apply_source.apply(html, src_text)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine-dir", default="src/engine")
    ap.add_argument("--src", default="src/strategy-map.src.html")
    ap.add_argument("--out", default="Insignia AI Strategy Map - Jira linked.html")
    a = ap.parse_args()

    skel_path = os.path.join(a.engine_dir, "skeleton.html")
    if not os.path.exists(skel_path):
        sys.exit(f"ERROR: {skel_path} missing — run decompose_bundle.py once to "
                 f"create the engine parts (see README).")
    skeleton = open(skel_path, encoding="utf-8").read()
    src_text = open(a.src, encoding="utf-8").read()
    html = assemble(skeleton, os.path.join(a.engine_dir, "vendor"), src_text)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"assembled {a.out!r} ({len(html):,} bytes) "
          f"from {a.engine_dir}/ + {a.src}")


if __name__ == "__main__":
    main()
