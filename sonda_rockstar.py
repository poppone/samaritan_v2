# TEMPORANEO, vedi .github/workflows/sonda-rockstar.yml
import os, subprocess, time
os.environ.setdefault("GROQ_API_KEY", "x")
os.environ.setdefault("PEXELS_API_KEY", "x")
import config, gameplay

print("Trailer in pagina:", gameplay.trailer_dalla_pagina_ufficiale("gta6"))
for salto in (0, 5):
    config.FILE_CRONOLOGIA = "cronologia_trend.json"
    t = time.time()
    percorsi = gameplay.scarica_trailer_ufficiali("gta6", config.STEAM_MAX_TRAILER, salto)
    print(f"salto {salto}: {len(percorsi)} file in {time.time()-t:.0f}s")
    for p in percorsi:
        info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                               "-show_entries", "stream=codec_name,width,height,r_frame_rate:format=duration,size",
                               "-of", "compact", p], capture_output=True, text=True).stdout
        print("  ", os.path.basename(p), info.replace("\n", " | "))
print("video_gia_fatti GTA 6:", gameplay.video_gia_fatti("GTA 6"))
