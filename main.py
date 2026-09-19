"""
Orchestratore della pipeline Samaritan.

  FASE 0  Analisi   -> cosa ha funzionato finora (feedback loop)
  FASE 1  Scrittura -> formato pesato + script ancorato a notizie vere
  FASE 2  Montaggio -> voce neurale, stacchi rapidi, sottotitoli
  FASE 3  Upload    -> YouTube + notifica Telegram

Uso:
    python main.py                         # tema libero
    python main.py "easter egg nascosti"   # tema specifico
"""
import sys
import os
import traceback

import config
from brain import (
    genera_script_samaritan,
    aggiorna_ultimo_video_id,
    costruisci_descrizione,
    costruisci_tag,
)
from maker import assembla_video_finale
from uploader import carica_short
import notifier

def esegui_pipeline_samaritan(tema=None):
    print("=" * 62)
    print(f"SAMARITAN ONLINE | {config.NOME_CANALE} | privacy={config.PRIVACY_STATUS}")
    print("=" * 62)

    # ---------------------------------------------------- FASE 0: Analisi
    print("\n[FASE 0/3] Aggiornamento dati di performance...")
    try:
        from analyst import aggiorna_performance
        aggiorna_performance()
    except Exception as e:
        print(f"[Analyst] Salto l'analisi ({e}).")

    # -------------------------------------------------- FASE 1: Scrittura
    print("\n[FASE 1/3] Generazione contenuto...")
    dati = genera_script_samaritan(tema)

    print("-" * 62)
    print(f"TITOLO  : {dati['titolo']}")
    print(f"FORMATO : {dati['stile']}")
    print(f"GIOCO   : {dati.get('gioco') or '(non specifico)'}")
    print(f"QUERY   : {dati['query_video']}")
    print(f"FONTE   : {dati['fonte'] or '(evergreen)'}")
    print("-" * 62)
    print(dati["script"])
    print("-" * 62)

    # -------------------------------------------------- FASE 2: Montaggio
    print("\n[FASE 2/3] Gameplay, voce, montaggio e sottotitoli...")
    # Il montaggio riempie questo dizionario con cosa e' finito davvero nel
    # video: serve alla descrizione, che altrimenti dichiara materiale
    # ufficiale dell'editore anche sui video fatti di clip d'archivio.
    materiale = {}
    video_path = assembla_video_finale(
        testo_per_audio=dati["script"],
        query_video=dati["query_video"],
        titolo=dati["titolo"],
        gioco=dati.get("gioco", ""),
        tema=tema or "Gaming",
        resoconto=materiale,
    )

    if not video_path or not os.path.exists(video_path):
        print("\n[Errore Pipeline] Rendering non completato.")
        notifier.notifica_errore("Rendering del video fallito.")
        return None

    # ----------------------------------------------------- FASE 3: Upload
    print("\n[FASE 3/3] Caricamento su YouTube...")
    # La miniatura la produce il maker insieme al video. Se manca (font
    # assente, rendering parziale) si carica lo stesso: YouTube ripiega su un
    # fotogramma automatico, che e' quello che faceva prima sempre.
    miniatura = (config.FILE_MINIATURA
                 if os.path.exists(config.FILE_MINIATURA) else None)

    video_id = carica_short(
        filepath=video_path,
        titolo=dati["titolo"],
        descrizione=costruisci_descrizione(dati, materiale),
        tag=costruisci_tag(dati),
        privacy=config.PRIVACY_STATUS,
        miniatura=miniatura,
    )

    if video_id:
        # Collega il video alla memoria: senza questo il feedback loop e' cieco
        aggiorna_ultimo_video_id(video_id)

    notifier.notifica_pubblicazione(dati, video_id, video_path)

    print("=" * 62)
    if video_id:
        print(f"PIPELINE COMPLETATA -> https://youtube.com/shorts/{video_id}")
    else:
        print("PIPELINE COMPLETATA MA UPLOAD FALLITO (il video e' in output_videos/)")
    print("=" * 62)
    return video_id


if __name__ == "__main__":
    tema_video = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        esegui_pipeline_samaritan(tema=tema_video)
    except Exception:
        traccia = traceback.format_exc()
        print(traccia)
        notifier.notifica_errore(traccia)
        sys.exit(1)
