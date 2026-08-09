# extract_source.py  — dump the app's editable template source to app/strategy-map.src.html
import json, re, os
BUNDLE = "Insignia AI Strategy Map - Jira linked.html"
OUT = "app/strategy-map.src.html"
def main():
    html = open(BUNDLE, encoding="utf-8").read()
    m = re.search(r'<script type="__bundler/template">(.*?)</script>', html, re.S)
    tmpl = json.loads(m.group(1).strip())
    os.makedirs("app", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(tmpl)
    print("wrote", OUT, len(tmpl), "bytes")
if __name__ == "__main__":
    main()
