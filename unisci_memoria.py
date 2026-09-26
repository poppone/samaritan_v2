"""Unisce la memoria di questa lavorazione a quella gia' salvata da un'altra.

Due lavorazioni che finiscono vicine scrivono entrambe cronologia_trend.json
partendo dalla stessa versione. Il 26 settembre 2026 la seconda ha fatto
`git pull --rebase`, git ha trovato le due aggiunte in conflitto nello stesso
punto del file e la memoria della seconda e' andata persa: un video caricato
su YouTube senza la riga che lo ricorda, quindi invisibile al freno
anti-doppioni, alla riserva e alle regole anti-ripetizione.

Qui l'unione si fa sul contenuto invece che sulle righe del file: la
cronologia gia' salvata, piu' le voci di questa lavorazione che mancano, e per
una voce presente in entrambe i campi che questa lavorazione ha riempito dopo
(il video_id arriva solo a caricamento finito).

Uso, dal workflow, con i file del repository gia' riallineati al remoto:
    python unisci_memoria.py <nostra cronologia> [<nostra performance>]
"""
import json
import os
import sys

MASSIMO_VOCI = 200      # lo stesso tetto di brain.salva_in_cronologia


def _chiave(voce):
    if isinstance(voce, dict):
        return ("voce", voce.get("timestamp"), voce.get("titolo"))
    return ("testo", voce)


def unisci_cronologie(salvata, nostra):
    unita = list(salvata or [])
    posizioni = {_chiave(v): i for i, v in enumerate(unita)}
    for voce in nostra or []:
        chiave = _chiave(voce)
        if chiave not in posizioni:
            posizioni[chiave] = len(unita)
            unita.append(voce)
        elif isinstance(voce, dict):
            esistente = dict(unita[posizioni[chiave]])
            esistente.update({k: v for k, v in voce.items() if v not in (None, "")})
            unita[posizioni[chiave]] = esistente
    # Stabile: le vecchie voci di solo testo, senza orario, restano in testa.
    unita.sort(key=lambda v: (v.get("timestamp") or 0) if isinstance(v, dict) else 0)
    return unita[-MASSIMO_VOCI:]


def performance_piu_recente(salvata, nostra):
    """Analytics e' una fotografia intera: vince la piu' recente, non si unisce."""
    if not nostra:
        return salvata
    if not salvata:
        return nostra
    return nostra if str(nostra.get("aggiornato", "")) >= str(salvata.get("aggiornato", "")) else salvata


def _leggi(percorso):
    try:
        with open(percorso, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _scrivi(percorso, dati):
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)


def main(argv):
    nostra_cronologia = _leggi(argv[1]) if len(argv) > 1 else None
    nostra_performance = _leggi(argv[2]) if len(argv) > 2 else None

    if nostra_cronologia is not None:
        salvata = _leggi("cronologia_trend.json") or []
        _scrivi("cronologia_trend.json", unisci_cronologie(salvata, nostra_cronologia))

    if nostra_performance is not None:
        salvata = _leggi("performance.json") if os.path.exists("performance.json") else None
        _scrivi("performance.json", performance_piu_recente(salvata, nostra_performance))


if __name__ == "__main__":
    main(sys.argv)
