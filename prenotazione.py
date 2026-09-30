"""La notizia scelta si prenota subito, non a video finito.

Il 30 settembre 2026 sul canale notizie due lavorazioni lanciate a mano a
cinquanta secondi di distanza (le uscite delle 14:00 e delle 18:00) hanno
scelto la stessa notizia, Sanremo condotto da De Martino. Ciascuna ha letto
la memoria del repository com'era alla partenza e l'ha salvata solo dieci
minuti dopo, a video caricato: nessuna delle due poteva sapere dell'altra.

Adesso la lavorazione, prima di scegliere, riprende la memoria salvata nel
frattempo da altre (riallinea_cronologia), e appena ha lo script salva la sua
riga sul repository (prenota), prima di montare il video. Chi sceglie dopo la
trova e la notizia gli risulta gia' usata. Resta scoperto solo il caso di due
lavorazioni che scelgono nello stesso minuto.

Gira solo nel workflow (SAMARITAN_PRENOTA=1): in locale e nei test non tocca
git. Ogni errore si stampa e si ignora: una prenotazione mancata non deve
fermare un video.
"""
import json
import os
import subprocess

import config
from unisci_memoria import unisci_cronologie

TENTATIVI = 3


def attiva():
    return os.environ.get("SAMARITAN_PRENOTA", "").strip() == "1"


def _ramo():
    return os.environ.get("GITHUB_REF_NAME", "").strip() or "main"


def _git(*argomenti, env=None):
    return subprocess.run(["git", *argomenti], capture_output=True, text=True,
                          timeout=60, cwd=config.DIR_PROGETTO,
                          env={**os.environ, **(env or {})})


def _nel_repo():
    """Il percorso della cronologia come lo vuole git, relativo al repo."""
    return os.path.relpath(config.FILE_CRONOLOGIA, config.DIR_PROGETTO)


def _cronologia_remota():
    """La cronologia sul repository adesso, o None se non si legge."""
    ramo = _ramo()
    if _git("fetch", "-q", "origin", ramo).returncode != 0:
        return None
    letto = _git("show", f"origin/{ramo}:{_nel_repo()}")
    if letto.returncode != 0:
        return []          # il file non c'e' ancora: prima lavorazione
    try:
        dati = json.loads(letto.stdout)
    except ValueError:
        return None
    return dati if isinstance(dati, list) else None


def _leggi_locale():
    try:
        with open(config.FILE_CRONOLOGIA, encoding="utf-8") as f:
            dati = json.load(f)
        return dati if isinstance(dati, list) else []
    except (OSError, ValueError):
        return []


def _scrivi_locale(cronologia):
    with open(config.FILE_CRONOLOGIA, "w", encoding="utf-8") as f:
        json.dump(cronologia, f, ensure_ascii=False, indent=2)


def riallinea_cronologia():
    """Aggiunge alla cronologia locale le righe salvate da altre lavorazioni."""
    if not attiva():
        return False
    try:
        remota = _cronologia_remota()
        if remota is None:
            print("[Prenotazione] Memoria remota non leggibile, proseguo con la mia.")
            return False
        _scrivi_locale(unisci_cronologie(remota, _leggi_locale()))
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[Prenotazione] Riallineo non riuscito: {e}")
        return False


def _commit_sul_remoto(ramo, testo):
    """Un commit sopra origin/ramo che cambia solo la cronologia.

    Si costruisce con un indice a parte e non si tocca il ramo locale: il
    passo finale del workflow salva il resto della memoria come ha sempre
    fatto, e se trova il remoto avanti unisce con unisci_memoria.py.
    """
    indice = os.path.join(config.DIR_PROGETTO, ".git", "indice-prenotazione")
    env = {"GIT_INDEX_FILE": indice,
           "GIT_AUTHOR_NAME": "Samaritan Bot",
           "GIT_AUTHOR_EMAIL": "bot@samaritan.local",
           "GIT_COMMITTER_NAME": "Samaritan Bot",
           "GIT_COMMITTER_EMAIL": "bot@samaritan.local"}
    try:
        blob = _git("hash-object", "-w", "--", _nel_repo())
        if blob.returncode != 0:
            return None
        passi = [
            ("read-tree", f"origin/{ramo}"),
            ("update-index", "--add", "--cacheinfo",
             f"100644,{blob.stdout.strip()},{_nel_repo()}"),
        ]
        for passo in passi:
            if _git(*passo, env=env).returncode != 0:
                return None
        albero = _git("write-tree", env=env)
        if albero.returncode != 0:
            return None
        commit = _git("commit-tree", albero.stdout.strip(), "-p", f"origin/{ramo}",
                      "-m", testo, env=env)
        return commit.stdout.strip() if commit.returncode == 0 else None
    finally:
        if os.path.exists(indice):
            os.remove(indice)


def prenota(titolo=""):
    """Salva sul repository la cronologia con la riga appena scritta."""
    if not attiva():
        return False
    try:
        ramo = _ramo()
        nostra = _leggi_locale()
        for _ in range(TENTATIVI):
            remota = _cronologia_remota()
            if remota is None:
                break
            _scrivi_locale(unisci_cronologie(remota, nostra))
            commit = _commit_sul_remoto(ramo, "Prenotazione notizia Samaritan [skip ci]")
            if not commit:
                break
            if _git("push", "-q", "origin", f"{commit}:refs/heads/{ramo}").returncode == 0:
                print(f"[Prenotazione] Notizia prenotata: {titolo}")
                return True
        print("[Prenotazione] Non riuscita, la memoria si salva a fine lavorazione.")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[Prenotazione] Non riuscita: {e}")
        return False
