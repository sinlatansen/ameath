# ameath/vioce.py
import os
import sys
import random

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class VoicePlayer:
    def __init__(self):
        self.voice_files = []
        voice_dir = resource_path("sound/vioce")
        if os.path.exists(voice_dir):
            for file in os.listdir(voice_dir):
                if file.lower().endswith('.wav'):
                    self.voice_files.append(os.path.join(voice_dir, file))

    def play_random_voice(self):
        try:
            import winsound
            if self.voice_files:
                random_voice = random.choice(self.voice_files)
                winsound.PlaySound(random_voice, winsound.SND_ASYNC | winsound.SND_FILENAME)
        except ImportError:
            pass
