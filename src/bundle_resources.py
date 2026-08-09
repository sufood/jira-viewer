# bundle_resources.py — move resources between app bundles by manifest uuid.
import json, re
MANI_RE = re.compile(r'(<script type="__bundler/manifest">)(.*?)(</script>)', re.S)

def _man(html):
    m = MANI_RE.search(html); return m, json.loads(m.group(2).strip())

def _write(html, m, manifest):
    return html[:m.start(2)] + json.dumps(manifest, separators=(",", ":")) + html[m.end(2):]

def copy_resource(dst_html, src_html, src_uuid, new_uuid=None):
    _, src = _man(src_html)
    m, dst = _man(dst_html)
    new_uuid = new_uuid or src_uuid
    dst[new_uuid] = src[src_uuid]
    return _write(dst_html, m, dst), new_uuid

def remove_resource(html, uuid):
    m, man = _man(html)
    man.pop(uuid, None)
    return _write(html, m, man)
