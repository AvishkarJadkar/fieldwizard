import re
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


sources = [
    ("mixkit", "https://mixkit.co/free-stock-video/soccer/", r'https://assets\.mixkit\.co/videos/[^"\'\s]+\.mp4'),
    ("pexels", "https://www.pexels.com/search/videos/soccer%20match/", r'https://videos\.pexels\.com/[^"\'\s]+\.mp4'),
    ("coverr", "https://coverr.co/s?q=soccer", r'https://[^"\'\s]+\.mp4'),
]

for name, url, pat in sources:
    try:
        html = get(url)
        hits = list(dict.fromkeys(re.findall(pat, html)))
        print(name, len(hits))
        for h in hits[:10]:
            print("  ", h)
    except Exception as e:
        print(name, "ERR", e)
