#!/usr/bin/env python3
"""Decompose the single-file app bundle into inspectable source parts, so the
bundle becomes a *generated* artifact instead of a checked-in 1.5 MB "mystery
binary" you hand-patch with `apply`.

Writes, under --engine-dir (default src/engine/):
  skeleton.html   the bundle shell + manifest scaffold, with every resource blob
                  replaced by an "@@uuid@@" placeholder and the app-source template
                  block blanked to @@TEMPLATE@@ — so the app source lives ONLY in
                  src/strategy-map.src.html (grep it: no renderVals here).
  vendor/<uuid>   each manifest resource's raw bytes (woff2 fonts, gzipped JS runtime).

build_bundle.py reverses this. assemble(decompose(bundle)) is byte-identical to the
original bundle when src/strategy-map.src.html matches the source baked into it
(verified: apply() is byte-idempotent).

This is a maintenance/one-time step — re-run only when the upstream engine (runtime
or fonts) changes, not for ordinary app edits.

    python decompose_bundle.py [--bundle PATH] [--engine-dir src/engine]
"""
import argparse
import base64
import json
import os
import re

MANI = re.compile(r'(<script type="__bundler/manifest">)(.*?)(</script>)', re.S)
TMPL = re.compile(r'(<script type="__bundler/template">)(.*?)(</script>)', re.S)


def decompose(html):
    """Return (skeleton_html, {uuid: raw_bytes})."""
    mani_m = MANI.search(html)
    if not mani_m:
        raise ValueError("no __bundler/manifest block found — not an app bundle?")
    manifest = json.loads(mani_m.group(2).strip())
    blobs, skel_mani = {}, mani_m.group(2)
    for uuid, v in manifest.items():
        data = v["data"]
        blobs[uuid] = base64.b64decode(data)
        # Replace the exact base64 value with a placeholder (leaves all JSON
        # punctuation/order intact → reassembly is byte-identical).
        skel_mani = skel_mani.replace('"' + data + '"', '"@@' + uuid + '@@"', 1)
    skeleton = html[:mani_m.start(2)] + skel_mani + html[mani_m.end(2):]
    # Blank the app-source template block: strategy-map.src.html is the source.
    tm = TMPL.search(skeleton)
    if not tm:
        raise ValueError("no __bundler/template block found")
    skeleton = skeleton[:tm.start(2)] + "@@TEMPLATE@@" + skeleton[tm.end(2):]
    return skeleton, blobs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", default="Insignia AI Strategy Map - Jira linked.html")
    ap.add_argument("--engine-dir", default="src/engine")
    a = ap.parse_args()

    html = open(a.bundle, encoding="utf-8").read()
    skeleton, blobs = decompose(html)

    vendor = os.path.join(a.engine_dir, "vendor")
    os.makedirs(vendor, exist_ok=True)
    with open(os.path.join(a.engine_dir, "skeleton.html"), "w", encoding="utf-8") as f:
        f.write(skeleton)
    for uuid, raw in blobs.items():
        with open(os.path.join(vendor, uuid), "wb") as f:
            f.write(raw)
    print(f"decomposed {a.bundle!r}")
    print(f"  -> {a.engine_dir}/skeleton.html ({len(skeleton):,} bytes)")
    print(f"  -> {a.engine_dir}/vendor/ ({len(blobs)} resource blobs)")


if __name__ == "__main__":
    main()
