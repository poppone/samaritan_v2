# TEMPORANEO, vedi .github/workflows/sonda-rockstar.yml
import re, json, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

def get(url, dati=None, extra=None):
    h = dict(UA); h.update(extra or {})
    req = urllib.request.Request(url, data=dati, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            corpo = r.read()
            print(f"== {url} -> {r.status} {r.headers.get('content-type')} {len(corpo)} byte")
            return corpo.decode("utf-8", "replace")
    except Exception as e:
        print(f"== {url} -> ERRORE {e}")
        return ""

pagine = [
    "https://www.rockstargames.com/VI",
    "https://www.rockstargames.com/VI/downloads",
    "https://www.rockstargames.com/videos",
    "https://www.rockstargames.com/newswire/tags/702",
    "https://www.rockstargames.com/videos/game/GTAVI",
]
tutto = ""
for p in pagine:
    t = get(p)
    tutto += t
    print("   titolo:", re.findall(r"<title>(.*?)</title>", t)[:1])
    for pat in [r"https?://[^\"'\s<>\\]+\.(?:mp4|m3u8|webm)[^\"'\s<>\\]*",
                r"https?://[^\"'\s<>\\]*(?:akamaized|rsg\.sc|rockstargames)[^\"'\s<>\\]*\.(?:jpg|jpeg|png|webp)",
                r"https?://graph\.rockstargames\.com[^\"'\s<>\\]*",
                r"/videos/[A-Za-z0-9]+",
                r"videoplayer[^\"'\s<>\\]*",
                r"sha256Hash[^,}]{0,90}",
                r"operationName[^,}]{0,80}"]:
        trovati = sorted(set(re.findall(pat, t)))
        if trovati:
            print(f"   [{pat[:30]}] {len(trovati)}:")
            for x in trovati[:25]:
                print("     ", x[:220])
    # script js del sito: spesso i dati stanno nei bundle
    js = sorted(set(re.findall(r"https?://[^\"'\s<>]+\.js", t)))[:8]
    print("   js:", js)

# vecchia API del lettore video
for u in ["https://www.rockstargames.com/videoplayer/videos/get-video.json?id=6178&locale=en_us",
          "https://www.rockstargames.com/videoplayer/videos/get-video.json?id=6179&locale=en_us"]:
    print(get(u)[:600])
