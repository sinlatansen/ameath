import os
import sys
import random
import struct
import threading
import numpy as np
import sounddevice as sd


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def read_wav_file(filepath):
    """读取WAV文件，支持PCM和IEEE Float格式"""
    with open(filepath, "rb") as f:
        # 读取RIFF头
        riff = f.read(4)
        if riff != b"RIFF":
            raise ValueError("不是有效的WAV文件")

        # 文件大小（跳过）
        f.read(4)

        # WAVE标识
        wave_id = f.read(4)
        if wave_id != b"WAVE":
            raise ValueError("不是有效的WAVE格式")

        # 查找fmt chunk
        while True:
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                raise ValueError("找不到fmt chunk")

            chunk_size = struct.unpack("<I", f.read(4))[0]

            if chunk_id == b"fmt ":
                # 读取fmt数据
                fmt_data = f.read(chunk_size)
                audio_format = struct.unpack("<H", fmt_data[0:2])[0]
                channels = struct.unpack("<H", fmt_data[2:4])[0]
                sample_rate = struct.unpack("<I", fmt_data[4:8])[0]
                bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]
                break
            else:
                # 跳过其他chunk
                f.seek(chunk_size, 1)

        # 查找data chunk
        while True:
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                raise ValueError("找不到data chunk")

            chunk_size = struct.unpack("<I", f.read(4))[0]

            if chunk_id == b"data":
                raw_data = f.read(chunk_size)
                break
            else:
                f.seek(chunk_size, 1)

        # 解析音频数据
        if audio_format == 1:  # PCM
            if bits_per_sample == 8:
                data = np.frombuffer(raw_data, dtype=np.uint8)
                data = data.astype(np.float32) / 128.0 - 1.0
            elif bits_per_sample == 16:
                data = np.frombuffer(raw_data, dtype=np.int16)
                data = data.astype(np.float32) / 32768.0
            elif bits_per_sample == 24:
                # 24-bit PCM需要特殊处理
                n_samples = len(raw_data) // 3
                data = np.zeros(n_samples, dtype=np.float32)
                for i in range(n_samples):
                    sample = raw_data[i * 3 : (i + 1) * 3]
                    value = struct.unpack(
                        "<i", sample + (b"\x00" if sample[2] < 128 else b"\xff")
                    )[0]
                    data[i] = value / 8388608.0
            elif bits_per_sample == 32:
                data = np.frombuffer(raw_data, dtype=np.int32)
                data = data.astype(np.float32) / 2147483648.0
            else:
                raise ValueError(f"不支持的PCM位深: {bits_per_sample}")

        elif audio_format == 3:  # IEEE Float
            if bits_per_sample == 32:
                data = np.frombuffer(raw_data, dtype=np.float32)
            elif bits_per_sample == 64:
                data = np.frombuffer(raw_data, dtype=np.float64)
                data = data.astype(np.float32)
            else:
                raise ValueError(f"不支持的Float位深: {bits_per_sample}")
        else:
            raise ValueError(f"不支持的音频格式: {audio_format}")

        # 如果是立体声，reshape
        if channels == 2:
            data = data.reshape(-1, 2)

        return data, sample_rate, channels


class VoicePlayer:
    def __init__(self):
        self.voice_files = []
        self.last_voice = None
        self.consecutive_count = 0
        self.volume = 1.0  # 0.0-1.0
        self.enabled = True  # 语音开关
        self._current_stream = None
        self._play_thread = None
        self._stop_event = threading.Event()

        # 加载语音文件
        voice_dir = resource_path("sound/voice")
        if os.path.exists(voice_dir):
            for file in os.listdir(voice_dir):
                if file.lower().endswith(".wav"):
                    self.voice_files.append(os.path.join(voice_dir, file))

    def set_enabled(self, enabled):
        """设置语音开关"""
        self.enabled = enabled
        if not enabled:
            self.stop()

    def set_volume(self, volume_percent):
        """设置音量百分比 (0-150)"""
        if volume_percent < 0:
            volume_percent = 0
        elif volume_percent > 150:
            volume_percent = 150
        self.volume = volume_percent / 100.0

    def _load_wav(self, filepath):
        """加载WAV文件为numpy数组"""
        try:
            data, sample_rate, channels = read_wav_file(filepath)

            # 应用音量
            data = data * self.volume

            return data, sample_rate
        except Exception as e:
            print(f"加载WAV文件失败: {e}")
            return None, None

    def _play_audio(self, audio_data, sample_rate):
        """在后台线程中播放音频"""
        try:
            # 确定通道数
            if len(audio_data.shape) == 1:
                channels = 1
            else:
                channels = audio_data.shape[1]

            # 创建输出流
            stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype=np.float32,
                blocksize=1024,
            )

            with stream:
                # 分块写入音频数据
                chunk_size = 1024
                for i in range(0, len(audio_data), chunk_size):
                    if self._stop_event.is_set():
                        break
                    chunk = audio_data[i : i + chunk_size]
                    stream.write(chunk)

        except Exception as e:
            print(f"播放音频失败: {e}")

    def play_random_voice(self):
        """播放随机语音（如果启用）"""
        if not self.enabled or not self.voice_files:
            return

        try:
            # 选择语音文件
            if len(self.voice_files) == 1:
                voice_file = self.voice_files[0]
            else:
                # 避免连续播放同一语音超过三次
                if self.consecutive_count >= 2 and self.last_voice is not None:
                    other_voices = [f for f in self.voice_files if f != self.last_voice]
                    voice_file = (
                        random.choice(other_voices)
                        if other_voices
                        else self.voice_files[0]
                    )
                else:
                    voice_file = random.choice(self.voice_files)

            # 更新计数器
            if voice_file == self.last_voice:
                self.consecutive_count += 1
            else:
                self.last_voice = voice_file
                self.consecutive_count = 0

            # 加载音频
            audio_data, sample_rate = self._load_wav(voice_file)
            if audio_data is None:
                return

            # 停止之前的播放
            self.stop()
            self._stop_event.clear()

            # 在新线程中播放
            self._play_thread = threading.Thread(
                target=self._play_audio, args=(audio_data, sample_rate), daemon=True
            )
            self._play_thread.start()

        except Exception as e:
            print(f"播放语音失败: {e}")

    def stop(self):
        """停止当前播放"""
        self._stop_event.set()
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=0.5)
        self._play_thread = None
