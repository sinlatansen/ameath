import os
import sys
import random
import pygame


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
        self.volume = 1.0  # 0.0 to 2.0

        # 初始化 pygame mixer
        self._mixer_initialized = False
        try:
            pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
            pygame.mixer.init()
            self._mixer_initialized = True
        except Exception as e:
            print(f"pygame 初始化失败: {e}")
            self._mixer_initialized = False

        # 加载语音文件
        voice_dir = resource_path("sound/voice")
        if os.path.exists(voice_dir):
            for file in os.listdir(voice_dir):
                if file.lower().endswith('.wav'):
                    self.voice_files.append(os.path.join(voice_dir, file))

    def set_volume(self, volume_percent):
        """设置音量百分比 (0-200)"""
        if volume_percent < 0:
            volume_percent = 0
        elif volume_percent > 200:
            volume_percent = 200
        self.volume = volume_percent / 100.0

    def play_random_voice(self):
        if not self._mixer_initialized or not self.voice_files:
            return

        try:
            # 选择语音文件
            if len(self.voice_files) == 1:
                random_voice = self.voice_files[0]
            else:
                if self.consecutive_count >= 2 and self.last_voice is not None:
                    other_voices = [f for f in self.voice_files if f != self.last_voice]
                    random_voice = random.choice(other_voices) if other_voices else self.voice_files[0]
                else:
                    random_voice = random.choice(self.voice_files)

            # 更新计数器
            if random_voice == self.last_voice:
                self.consecutive_count += 1
            else:
                self.last_voice = random_voice
                self.consecutive_count = 0

            # 播放声音
            sound = pygame.mixer.Sound(random_voice)
            actual_volume = min(self.volume, 1.0)  # pygame 最大音量为 1.0
            sound.set_volume(actual_volume)
            sound.play()

        except Exception as e:
            print(f"pygame 播放失败: {e}")
