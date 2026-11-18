"""Optional offline TTS and offline Vosk push-to-talk recognition.
The simulation and manual controls work with no external packages.
"""
import json
import importlib.util
import os
import queue
import re
import threading


def recognize_phrase(text, language):
    """Map Chinese/English recognizer output to one of six fixed phrases."""
    clean = re.sub(r'[\s,.!?;:，。！？、]+', '', (text or '').strip().lower())
    if language == 'zh':
        clean = clean.replace('这', '這').replace('苹', '蘋').replace('谢', '謝')
        # Some Mandarin recognition models emit these phonetic variants.
        mapping = {
            '這是蘋果': 'intro_apple', '這是香蕉': 'intro_banana',
            '蘋果': 'apple', '香蕉': 'banana',
            '什麼': 'what', '什么': 'what', '謝謝': 'thanks',
        }
    else:
        mapping = {
            'thisisanapple': 'intro_apple', 'thisisapple': 'intro_apple',
            'thisisabanana': 'intro_banana', 'thisisbanana': 'intro_banana',
            'apple': 'apple', 'banana': 'banana',
            'what': 'what', 'thanks': 'thanks', 'thankyou': 'thanks',
        }
    return mapping.get(clean)


class Speaker:
    def __init__(self, enabled=True, rate=150):
        self.available = importlib.util.find_spec("pyttsx3") is not None
        self.enabled = bool(enabled and self.available)
        self.rate = int(rate)
        self.items = queue.Queue()
        self.worker = None
        if self.available:
            self.worker = threading.Thread(target=self._work, daemon=True)
            self.worker.start()

    def say(self, text, language='zh'):
        if self.enabled:
            self.items.put((text, language, self.rate))

    def close(self):
        self.items.put(None)

    def _work(self):
        # SAPI5 on Windows runs in a COM apartment; initialize it on this worker.
        try:
            if os.name == "nt":
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except ImportError:
                    pass
            import pyttsx3
            engine = pyttsx3.init()
        except Exception:
            return
        # Default system voice is used, unless a matching language voice exists.
        voices = engine.getProperty('voices') or []
        def pick_voice(lang):
            for item in voices:
                parts = str(item.name).lower() + ' ' + str(item.id).lower()
                for val in getattr(item, 'languages', []) or []:
                    parts += ' ' + str(val).lower()
                if lang == 'zh' and any(k in parts for k in ('chinese','mandarin','zh-','zh_','zh_tw','zh-cn')):
                    return item.id
                if lang == 'en' and any(k in parts for k in ('english', 'en-us', 'en_gb')):
                    return item.id
            return None
        while True:
            item = self.items.get()
            if item is None:
                return
            text, lang, rate = item
            try:
                engine.setProperty('rate', rate)
                voice_id = pick_voice(lang)
                if voice_id:
                    engine.setProperty('voice', voice_id)
                engine.say(text)
                engine.runAndWait()
            except Exception:
                # Do not crash event processing if TTS engine or voice fails.
                pass


class PushToTalk:
    """Vosk local model required at models/zh or models/en.

    start recording on button/key down, stop and decode on release.
    All Tk callbacks are dispatched with root.after on the main thread.
    """
    def __init__(self, root, model_dir='models'):
        self.root = root
        self.model_dir = model_dir
        self.stream = None
        self.chunks = []
        self.model_cache = {}
        self.active_lang = None

    def available(self, language):
        if not os.path.isdir(os.path.join(self.model_dir, language)):
            return False
        try:
            import vosk  # noqa: F401
            import sounddevice  # noqa: F401
        except ImportError:
            return False
        return True

    def start(self, language):
        if self.stream is not None:
            return False, 'already-recording'
        if not self.available(language):
            return False, 'no-model-or-package'
        try:
            import sounddevice as sd
            self.chunks = []
            self.active_lang = language
            def callback(indata, frames, time_info, status):
                self.chunks.append(bytes(indata))
            self.stream = sd.RawInputStream(samplerate=16000, blocksize=8000,
                                            channels=1, dtype='int16', callback=callback)
            self.stream.start()
        except Exception as exc:
            self.stream = None
            return False, str(exc)
        return True, 'recording'

    def stop(self, on_result):
        if self.stream is None:
            return
        stream = self.stream
        self.stream = None
        stream.stop()
        stream.close()
        samples = b''.join(self.chunks)
        lang = self.active_lang
        def decode():
            try:
                from vosk import Model, KaldiRecognizer
                if lang not in self.model_cache:
                    self.model_cache[lang] = Model(os.path.join(self.model_dir, lang))
                grammar = (['这是苹果','这是香蕉','苹果','香蕉','什么','谢谢','[unk]']
                           if lang == 'zh' else
                           ['this is an apple','this is a banana','apple','banana',
                            'what','thank you','thanks','[unk]'])
                try:
                    rec = KaldiRecognizer(self.model_cache[lang], 16000,
                                          json.dumps(grammar, ensure_ascii=False))
                except Exception:
                    rec = KaldiRecognizer(self.model_cache[lang], 16000)
                rec.AcceptWaveform(samples)
                raw = json.loads(rec.FinalResult()).get('text', '')
                code = recognize_phrase(raw, lang)
                self.root.after(0, lambda: on_result(code, raw, None))
            except Exception as exc:
                self.root.after(0, lambda: on_result(None, '', str(exc)))
        threading.Thread(target=decode, daemon=True).start()
