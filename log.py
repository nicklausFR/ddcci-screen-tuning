import logging
import os
import sys
import threading
import time

log_path = os.path.join(os.path.dirname(__file__), "app.log")

logger = logging.getLogger("MidiControllerLogger")
logger.setLevel(logging.INFO)

# Handler fichier
file_handler = logging.FileHandler(log_path, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter("%(asctime)s - %(message)s")
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Fonction de suivi du log (optionnelle)
def follow_log():
    def _tail():
        with open(log_path, "r", encoding="utf-8") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line, end="")
                else:
                    time.sleep(0.1)

    t = threading.Thread(target=_tail, daemon=True)
    t.start()
