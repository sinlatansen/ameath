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
        self.last_voice = None
        self.consecutive_count = 0
        voice_dir = resource_path("sound/vioce")
        if os.path.exists(voice_dir):
            for file in os.listdir(voice_dir):
                if file.lower().endswith('.wav'):
                    self.voice_files.append(os.path.join(voice_dir, file))

    def play_random_voice(self):
        try:
            import winsound
            if not self.voice_files:
                return

            # 如果只有一种语音文件，直接播放
            if len(self.voice_files) == 1:
                random_voice = self.voice_files[0]
            else:
                # 避免连续播放同一语音超过三次
                if self.consecutive_count >= 2 and self.last_voice is not None:
                    # 从其他文件中选择（排除上次播放的）
                    other_voices = [f for f in self.voice_files if f != self.last_voice]
                    random_voice = random.choice(other_voices)
                else:
                    # 正常随机选择
                    random_voice = random.choice(self.voice_files)

            # 更新计数器
            if random_voice == self.last_voice:
                self.consecutive_count += 1
            else:
                self.last_voice = random_voice
                self.consecutive_count = 0

            winsound.PlaySound(random_voice, winsound.SND_ASYNC | winsound.SND_FILENAME)
        except ImportError:
            pass
