"""Preparazione comune ai test.

I moduli di Samaritan importano `config`, che esce con errore se mancano le
chiavi obbligatorie. Qui mettiamo valori finti PRIMA che i test importino
qualsiasi cosa: i test non toccano la rete, quindi non servono chiavi vere.
"""
import os
import sys

os.environ.setdefault("GROQ_API_KEY", "test-non-usata")
os.environ.setdefault("PEXELS_API_KEY", "test-non-usata")

# La radice del progetto deve stare nel path: i moduli sono a livello singolo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
