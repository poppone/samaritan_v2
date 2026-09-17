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
from brain import genera_script_samaritan, aggiorna_ultimo_video_id
from maker import assembla_video_finale
from uploader import carica_short
import notifier

# Tag: contano poco per il ranking, ma aiutano la categorizzazione del canale
TAG_BASE = ["gaming", "videogiochi", "gameplay", "shorts", "curiosita gaming"]


def costruisci_descrizione(dati):
    """Descrizione unica per ogni video.

    Prima era un blocco di testo identico su ogni upload: e' esattamente il
    pattern che identifica i canali automatizzati. Ora la genera il modello,
    con la fonte reale citata quando esiste.
    """
    parti = [dati.get("descrizione") or dati["titolo"]]

    if dati.get("fonte"):
        parti.append(f"\nFonte della notizia: {dati['fonte']}")

    parti.append(
        f"\nNuovi Shorts gaming ogni giorno su {config.NOME_CANALE}. "
        "Iscriviti per non perderli."
    )
    parti.append("\n#Shorts #Gaming #Videogiochi #Gameplay")
    return "\n".join(parti)


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
    print(f"QUERY   : {dati['query_video']}")
    print(f"FONTE   : {dati['fonte'] or '(evergreen)'}")
    print("-" * 62)
    print(dati["script"])
    print("-" * 62)

    # -------------------------------------------------- FASE 2: Montaggio
    print("\n[FASE 2/3] Voce, montaggio e sottotitoli...")
    video_path = assembla_video_finale(
        testo_per_audio=dati["script"],
        query_video=dati["query_video"],
        titolo=dati["titolo"],
        tema=tema or "Gaming",
    )

    if not video_path or not os.path.exists(video_path):
        print("\n[Errore Pipeline] Rendering non completato.")
        notifier.notifica_errore("Rendering del video fallito.")
        return None

    # ----------------------------------------------------- FASE 3: Upload
    print("\n[FASE 3/3] Caricamento su YouTube...")
    video_id = carica_short(
        filepath=video_path,
        titolo=dati["titolo"],
        descrizione=costruisci_descrizione(dati),
        tag=TAG_BASE,
        privacy=config.PRIVACY_STATUS,
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
