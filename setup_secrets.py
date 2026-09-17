"""
Genera i valori da incollare nei GitHub Secrets.

Da eseguire UNA VOLTA in locale, dopo esserti autenticato con YouTube:

    python setup_secrets.py

Stampa i blocchi base64 di client_secret.json e token.pickle, che vanno
incollati in:  GitHub -> Settings -> Secrets and variables -> Actions
"""
import base64
import os
import sys

FILE_SEGRETI = {
    "CLIENT_SECRET_B64": "client_secret.json",
    "YOUTUBE_TOKEN_B64": "token.pickle",
}


def main():
    mancanti = [p for p in FILE_SEGRETI.values() if not os.path.exists(p)]
    if mancanti:
        print(f"File mancanti: {', '.join(mancanti)}")
        if "token.pickle" in mancanti:
            print("\nPer generare token.pickle esegui prima:")
            print("    python -c \"from uploader import ottieni_credenziali; "
                  "ottieni_credenziali()\"")
            print("Si aprira' il browser per autorizzare il canale YouTube.")
        sys.exit(1)

    print("=" * 70)
    print("Incolla questi valori in GitHub > Settings > Secrets > Actions")
    print("=" * 70)
    for nome_secret, percorso in FILE_SEGRETI.items():
        with open(percorso, "rb") as f:
            codificato = base64.b64encode(f.read()).decode()
        print(f"\n--- {nome_secret} ---")
        print(codificato)

    print("\n" + "=" * 70)
    print("Ricorda anche i secret: GROQ_API_KEY, PEXELS_API_KEY")
    print("Opzionali: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
    print("=" * 70)


if __name__ == "__main__":
    main()
