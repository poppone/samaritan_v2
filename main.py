"""
Orchestratore della pipeline Samaritan.

  FASE 0  Analisi   -> cosa ha funzionato finora (feedback loop)
  FASE 1  Scrittura -> formato pesato + script ancorato a notizie vere
  FASE 2  Montaggio -> voce neurale, stacchi rapidi, sottotitoli
  FASE 3  Upload    -> YouTube + notifica Telegram

Escono due cose diverse dallo stesso percorso: lo Short verticale da mezzo
minuto (tre al giorno) e il video lungo 16:9 da otto minuti (uno al giorno,
VIDEO_LUNGO=1). Cambiano la FASE 1 e l'inizio della FASE 2; il resto e'
identico, e il perche' dei due formati sta in lungo.py e nel README.

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
    carica_cronologia,
    costruisci_descrizione,
    costruisci_tag,
)
from maker import assembla_video_finale
from uploader import carica_short, token_youtube_scaduto
import autoprofilo
import notifier
import orari

def prepara_uscita():
    """Decide se questa lavorazione deve partire, e per quale uscita.

    Torna True se si va avanti, False se non c'e' niente da fare.

    Le lavorazioni schedulate arrivano in ritardo, a volte di ore, e il 21
    settembre 2026 una non e' proprio partita. Da qui due comportamenti che si
    tengono per mano: ogni lavorazione dichiara quale uscita sta coprendo e si
    ferma se qualcun altro l'ha gia' coperta, e una lavorazione di riserva a
    fine giornata recupera l'uscita rimasta scoperta. Senza il primo pezzo il
    secondo farebbe doppioni.
    """
    # Il workflow lo scarta gia' prima di installare qualunque cosa (job
    # 'uscita'), quindi qui si arriva solo lanciando main.py a mano con
    # USCITA_CRON: in quel caso l'avviso su Telegram non disturba nessuno.
    if config.NESSUNA_USCITA:
        print("[Slot] Questa partenza non ha un'uscita nel profilo del canale: "
              "non faccio niente.")
        notifier.notifica_salto("Questa partenza notturna non ha un'uscita nel "
                                "profilo del canale: non c'e' niente da fare.")
        return False

    if config.RECUPERO:
        scelta = orari.slot_da_recuperare(carica_cronologia())
        if not scelta:
            print("[Recupero] Le uscite di oggi sono tutte a posto: non faccio niente.")
            notifier.notifica_salto("Riserva delle 22:30: le uscite di oggi sono "
                                    "tutte a posto, non serve recuperare niente.")
            return False
        slot, lingua, formato = scelta
        config.SLOT = slot
        config.USCITA = orari.uscita_da_coprire(slot, recupero=True)
        config.LINGUA = lingua
        config.VOCE_TTS = config.VOCE_TTS_EN if lingua == "en" else config.VOCE_TTS_IT
        # Il formato va riapplicato PRIMA di qualunque conto: la riserva non
        # sa in partenza se le tocchera' uno Short verticale o il video lungo
        # orizzontale, e le misure calcolate all'import sono quelle dell'altro.
        config.applica_formato(formato == "lungo")
        # Niente ORARIO_USCITA: l'ora e' passata da un pezzo, il video esce
        # appena e' pronto.
        print(f"[Recupero] Manca l'uscita delle {slot} ({lingua}, {formato}): "
              f"la rifaccio adesso.")
        return True

    if config.SLOT and orari.gia_pubblicato(config.SLOT, carica_cronologia()):
        print(f"[Slot] L'uscita delle {config.SLOT} e' gia' coperta da un video: "
              f"mi fermo qui invece di farne un secondo uguale.")
        notifier.notifica_salto(f"L'uscita delle {config.SLOT} e' gia' coperta da "
                                f"un video: questa lavorazione non ne fa un secondo.")
        return False
    config.USCITA = orari.uscita_da_coprire(config.SLOT)
    return True


def _scrivi_e_monta(tema):
    """FASE 1 e 2. Ritorna (dati, percorso_video, materiale, capitoli).

    I capitoli esistono solo sul video lungo: sullo Short sono una stringa
    vuota, e costruisci_descrizione non scrive la sezione.
    """
    if config.VIDEO_LUNGO:
        import lungo

        print("\n[FASE 1/3] Scrittura del video lungo, sezione per sezione...")
        dati = lungo.genera_video_lungo(tema)
        _stampa_scheda(dati)

        print("\n[FASE 2/3] Voce, gameplay, montaggio e sottotitoli...")
        # La voce si genera qui e non dentro il montaggio: una sezione per
        # volta, per sapere quanto dura ciascuna e ricavarne i capitoli veri.
        audio, capitoli = lungo.produci_audio_e_capitoli(dati["sezioni"])
        materiale = {}
        video = assembla_video_finale(
            testo_per_audio=dati["script"],
            query_video=dati["query_video"],
            titolo=dati["titolo"],
            gioco=dati.get("gioco", ""),
            tema=tema or "Gaming",
            resoconto=materiale,
            audio_pronto=audio,
        )
        return dati, video, materiale, lungo.formatta_capitoli(capitoli)

    print("\n[FASE 1/3] Generazione contenuto...")
    dati = genera_script_samaritan(tema)
    _stampa_scheda(dati)

    print("\n[FASE 2/3] Gameplay, voce, montaggio e sottotitoli...")
    # Il montaggio riempie questo dizionario con cosa e' finito davvero nel
    # video: serve alla descrizione, che altrimenti dichiara materiale
    # ufficiale dell'editore anche sui video fatti di clip d'archivio.
    materiale = {}
    video = assembla_video_finale(
        testo_per_audio=dati["script"],
        query_video=dati["query_video"],
        titolo=dati["titolo"],
        gioco=dati.get("gioco", ""),
        tema=tema or "Gaming",
        resoconto=materiale,
        fonte=dati.get("fonte", ""),
    )
    return dati, video, materiale, ""


def _stampa_scheda(dati):
    print("-" * 62)
    print(f"TITOLO  : {dati['titolo']}")
    print(f"FORMATO : {dati['stile']}")
    print(f"GIOCO   : {dati.get('gioco') or '(non specifico)'}")
    print(f"QUERY   : {dati['query_video']}")
    print(f"FONTE   : {dati['fonte'] or '(evergreen)'}")
    print("-" * 62)
    print(dati["script"])
    print("-" * 62)


def esegui_pipeline_samaritan(tema=None):
    if not prepara_uscita():
        return None

    # Un canale nato dal solo argomento ("Altro" nella pagina) si scrive da
    # solo soggetto, ricerche e il resto, e ogni due settimane si ritara sui
    # suoi numeri (autoprofilo.py). Un argomento che YouTube non ammette
    # ferma tutto qui.
    try:
        autoprofilo.aggiorna_se_serve()
    except autoprofilo.ArgomentoNonAmmesso as e:
        print(f"[Autoprofilo] {e}")
        notifier.notifica_errore(str(e))
        return None

    che_cosa = "VIDEO LUNGO" if config.VIDEO_LUNGO else "SHORT"
    print("=" * 62)
    print(f"SAMARITAN ONLINE | {config.NOME_CANALE} | {che_cosa} | "
          f"privacy={config.PRIVACY_STATUS}")
    print("=" * 62)

    # ---------------------------------------------------- FASE 0: Analisi
    print("\n[FASE 0/3] Aggiornamento dati di performance...")
    try:
        from analyst import aggiorna_performance
        aggiorna_performance()
    except Exception as e:
        print(f"[Analyst] Salto l'analisi ({e}).")

    # Senza un token valido il video non puo' uscire: meglio saperlo adesso
    # che dopo aver scritto, prenotato la notizia e montato (vedi
    # uploader.token_youtube_scaduto).
    if token_youtube_scaduto():
        print("\n[Errore Pipeline] Token YouTube scaduto (invalid_grant): mi fermo.")
        notifier.notifica_token_scaduto()
        sys.exit(1)

    # -------------------------------------- FASE 1 e 2: scrittura e montaggio
    dati, video_path, materiale, capitoli = _scrivi_e_monta(tema)

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

    # L'ora a cui il video deve comparire sul canale. None = adesso.
    uscita = orari.uscita_programmata()

    video_id = carica_short(
        filepath=video_path,
        titolo=dati["titolo"],
        descrizione=costruisci_descrizione(dati, materiale, capitoli),
        tag=costruisci_tag(dati),
        privacy=config.PRIVACY_STATUS,
        miniatura=miniatura,
        pubblica_alle=uscita,
    )

    if video_id:
        # Collega il video alla memoria: senza questo il feedback loop e' cieco
        aggiorna_ultimo_video_id(video_id)

    notifier.notifica_pubblicazione(dati, video_id, video_path)

    print("=" * 62)
    if video_id:
        indirizzo = (f"https://youtu.be/{video_id}" if config.VIDEO_LUNGO
                     else f"https://youtube.com/shorts/{video_id}")
        if uscita:
            print(f"PIPELINE COMPLETATA -> {indirizzo} (esce alle {uscita:%H:%M})")
        else:
            print(f"PIPELINE COMPLETATA -> {indirizzo}")
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
