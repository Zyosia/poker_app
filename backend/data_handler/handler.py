import json
from pathlib import Path


def save_session(date_time, session_data):
    """
    Sauvegarde une session de poker Texas Holdem.

    Parameters
    ----------
    date_time : str
        Timestamp de la session.
        Exemple : "20260512_143210"

    session_data : dict
        Dictionnaire contenant toutes les données de la session.

    Returns
    -------
    Path
        Chemin du fichier sauvegardé.
    """

    # Dossier de sauvegarde
    session_dir = Path("Poker_Project/data/session")

    # Création du dossier si nécessaire
    session_dir.mkdir(parents=True, exist_ok=True)

    # Nom du fichier
    file_name = f"pk_sess_{date_time}.dat"

    # Chemin complet
    file_path = session_dir / file_name

    # Sauvegarde des données
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(session_data, file, indent=4)

    return file_path
