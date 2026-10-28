import json
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def commons_category(cat, limit=50):
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "list": "categorymembers",
        "cmtitle": f"Category:{cat}", "cmtype": "file", "cmlimit": limit,
    })
    d = json.load(urllib.request.urlopen(urllib.request.Request(
        "https://commons.wikimedia.org/w/api.php?" + q, headers={"User-Agent": UA}), timeout=30))
    return [m["title"] for m in d.get("query", {}).get("categorymembers", [])]


def commons_info(titles):
    if not titles:
        return []
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": "|".join(titles),
        "prop": "imageinfo", "iiprop": "url|size|mime",
    })
    d = json.load(urllib.request.urlopen(urllib.request.Request(
        "https://commons.wikimedia.org/w/api.php?" + q, headers={"User-Agent": UA}), timeout=30))
    out = []
    for p in d.get("query", {}).get("pages", {}).values():
        ii = p.get("imageinfo", [{}])[0]
        if ii.get("mime", "").startswith("video"):
            out.append((p["title"], ii.get("width"), ii.get("height"),
                        round(ii.get("size", 0) / 1e6, 1), ii.get("url")))
    return out


for cat in ["Videos of association football", "Association football videos",
            "Football matches", "Amateur association football"]:
    try:
        titles = commons_category(cat)
        print(f"== {cat}: {len(titles)}")
        for t in titles[:12]:
            print("   ", t)
    except Exception as e:
        print(cat, "ERR", e)

print("\n== pixabay")
try:
    html = get("https://pixabay.com/videos/search/soccer/")
    hits = list(dict.fromkeys(re.findall(r'https://cdn\.pixabay\.com/video/[^"\'\s]+\.mp4', html)))
    print(len(hits))
    for h in hits[:12]:
        print("   ", h)
except Exception as e:
    print("pixabay ERR", e)
