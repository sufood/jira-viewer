# import_wsjf_fonts.py — copy WSJF's woff2 fonts into the main bundle.
# The source CSS (added in a later task) references fonts by uuid via the loader.
import json, re, bundle_resources as br
MAIN = "Insignia AI Strategy Map - Jira linked.html"
WSJF = "WSJF Studio v2.html"

def man(html):
    return json.loads(re.search(r'<script type="__bundler/manifest">(.*?)</script>', html, re.S).group(1))

def main():
    main_html = open(MAIN, encoding="utf-8").read()
    wsjf_html = open(WSJF, encoding="utf-8").read()
    mapping = {}
    for uuid, v in man(wsjf_html).items():
        if v.get("mime") == "font/woff2":
            main_html, new_uuid = br.copy_resource(main_html, wsjf_html, uuid)
            mapping[uuid] = new_uuid
    open(MAIN, "w", encoding="utf-8").write(main_html)
    # Record which WSJF font uuids were copied (uuids are preserved on copy, so
    # this doubles as the list of fonts now resident in the main bundle).
    open("app/_wsjf_font_map.json", "w", encoding="utf-8").write(
        json.dumps(sorted(mapping), indent=2))
    print("copied", len(mapping), "fonts")
if __name__ == "__main__":
    main()
