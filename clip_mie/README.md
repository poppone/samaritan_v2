# Le clip girate in casa

Qui dentro va il materiale girato da popponetv: e' l'unico pezzo dei video
che non arriva da uno store. Trailer e screenshot Steam li pubblica l'editore
e finiscono identici su mille altri canali; due mani vere su un volante vero
non ce le ha nessun altro, ed e' esattamente la differenza che YouTube guarda
quando decide se un canale e' "prodotto in serie".

Una sottocartella per categoria. Una categoria puo' essere un genere
oppure un gioco solo:

    clip_mie/guida/       giochi di guida (Assetto Corsa, Forza, F1, ...)
    clip_mie/fortnite/    Fortnite

Samaritan monta queste clip **solo nei video di quella categoria**: la
categoria si ricava dal genere dichiarato da Steam, e quando il gioco su Steam
non c'e' ancora (le notizie parlano spesso di giochi appena annunciati, e
Fortnite su Steam non c'e' proprio) dal nome del gioco. Vedi
`categoria_clip_mie()` in `gameplay.py`.

## Come aggiungerne

Un file per clip, in `clip_mie/<categoria>/`, con queste caratteristiche:

- verticale, 720x1280 o piu' grande;
- dai 4 ai 10 secondi: il montaggio ne usa due o tre secondi per stacco;
- **senza audio**: la traccia viene comunque scartata, ma un file muto pesa
  meno e non rischia rivendicazioni Content ID;
- sotto il mega, cosi' il repository non si gonfia.

Da un video piu' lungo si ricavano cosi', con ffmpeg:

    ffmpeg -ss 8 -i registrazione.mp4 -t 6 -an \
           -c:v libx264 -crf 26 -preset veryfast -pix_fmt yuv420p \
           clip_mie/guida/volante_4.mp4

Per aprire una categoria nuova serve anche aggiungerla a `PAROLE_CLIP_MIE`
(e, se Steam la dichiara, a `GENERI_CLIP_MIE`) in `gameplay.py`: una cartella
che nessuna regola nomina resta li' senza che nessun video la usi mai.

Quante ne entrano in uno Short lo decide `MAX_CLIP_MIE` (due, di default).
