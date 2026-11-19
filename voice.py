"""Optional local speech output and Vosk push-to-talk recognition.

On macOS we use the built-in `say` command as an interruptible subprocess,
so the player's microphone never records a long queued synthetic utterance.
"""
import importlib.util
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import unicodedata


def recognize_phrase(text, language):
    """Map recognition variants to the six fixed commands, without guessing."""
    clean = unicodedata.normalize('NFKC', text or '').lower()
    clean = re.sub(r'[\s,.!?;:，。！？、\-~～]+', '', clean)
    if language == 'zh':
        for traditional, simplified in (('這','这'),('蘋','苹'),('謝','谢'),
                                        ('麼','么'),('個','个'),('時','时'),('麽','么')):
            clean = clean.replace(traditional, simplified)
        phrases = {
            '这是苹果':'intro_apple','这是一个苹果':'intro_apple',
            '这是个苹果':'intro_apple','这时苹果':'intro_apple',
            '这是香蕉':'intro_banana','这是一个香蕉':'intro_banana',
            '这是个香蕉':'intro_banana','这时香蕉':'intro_banana',
            '苹果':'apple','香蕉':'banana',
            '什么':'what','什么呀':'what','啥':'what',
            '谢谢':'thanks','谢谢你':'thanks','谢谢谢谢':'thanks',
        }
    else:
        phrases = {
            'thisisanapple':'intro_apple','thisisapple':'intro_apple',
            'thisisabanana':'intro_banana','thisisbanana':'intro_banana',
            'apple':'apple','banana':'banana',
            'what':'what','thanks':'thanks','thankyou':'thanks',
        }
    return phrases.get(clean)


def grammar_for(language):
    """Include both Chinese segmented/unsegmented spelling for model variants."""
    if language == 'zh':
        return ['这是苹果','这 是 苹果','这是香蕉','这 是 香蕉',
                '苹果','香蕉','什么','谢谢','[unk]']
    return ['this is an apple','this is a banana','apple','banana',
            'what','thank you','thanks','[unk]']


class Speaker:
    """Speech queue with immediate interruption on macOS."""
    def __init__(self, enabled=True, rate=150):
        self.mac_say = sys.platform == 'darwin' and shutil.which('say') is not None
        self.available = self.mac_say or importlib.util.find_spec('pyttsx3') is not None
        self.enabled = bool(enabled and self.available)
        self.rate = int(rate)
        self.items = queue.Queue()
        self.lock = threading.RLock()
        self.paused = False
        self.epoch = 0
        self.process = None
        self.voices = {}
        if self.mac_say:
            self.voices = self._mac_voices()
        self.worker = None
        if self.available:
            self.worker = threading.Thread(target=self._work, daemon=True)
            self.worker.start()

    @staticmethod
    def _mac_voices():
        result = {}
        try:
            output = subprocess.check_output(['say','-v','?'],
                                             stderr=subprocess.DEVNULL).decode('utf-8','replace')
            voices = []
            for line in output.splitlines():
                match = re.match(r'^(.+?)\s{2,}([a-z]{2}[_-][A-Z]{2})\s+#', line)
                if match:
                    voices.append((match.group(1).strip(), match.group(2)))
            for lang, prefixes in (('zh',('zh_TW','zh_CN','zh_HK')),
                                   ('en',('en_US','en_GB','en_AU'))):
                for prefix in prefixes:
                    found = next((name for name,locale in voices if locale == prefix),None)
                    if found:
                        result[lang] = found
                        break
        except Exception:
            pass
        return result

    def say(self, text, language='zh'):
        with self.lock:
            if self.enabled and not self.paused:
                self.items.put((text,language,self.rate,self.epoch))

    def pause(self):
        """Prevent future utterances and interrupt the current macOS sentence."""
        with self.lock:
            self.paused = True
            self.epoch += 1
            process = self.process
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        # Old queued phrases must not resume after the player has spoken.
        while True:
            try:
                item = self.items.get_nowait()
                if item is None:
                    self.items.put(None)
                    break
            except queue.Empty:
                break

    def resume(self):
        with self.lock:
            self.paused = False

    def close(self):
        self.pause()
        self.items.put(None)

    def _work(self):
        if self.mac_say:
            self._work_mac()
        else:
            self._work_pyttsx3()

    def _work_mac(self):
        while True:
            item = self.items.get()
            if item is None:
                return
            text,lang,rate,epoch = item
            with self.lock:
                if self.paused or epoch != self.epoch:
                    continue
                cmd = ['say','-r',str(int(rate))]
                if lang in self.voices:
                    cmd.extend(['-v',self.voices[lang]])
                cmd.append(text)
                try:
                    process = subprocess.Popen(cmd,stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
                except OSError:
                    continue
                self.process = process
            process.wait()
            with self.lock:
                if self.process is process:
                    self.process = None

    def _work_pyttsx3(self):
        # Legacy systems still use pyttsx3; the already-speaking sentence may
        # not be interruptible. Pending audio is always cleared on pause.
        try:
            if os.name == 'nt':
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except ImportError:
                    pass
            import pyttsx3
            engine = pyttsx3.init()
        except Exception:
            return
        voices = engine.getProperty('voices') or []
        def pick_voice(lang):
            for item in voices:
                parts = str(item.name).lower() + ' ' + str(item.id).lower()
                for val in getattr(item,'languages',[]) or []:
                    parts += ' ' + str(val).lower()
                if lang == 'zh' and any(k in parts for k in ('chinese','mandarin','zh-','zh_')):
                    return item.id
                if lang == 'en' and any(k in parts for k in ('english','en-us','en_gb')):
                    return item.id
            return None
        while True:
            item = self.items.get()
            if item is None:
                return
            text,lang,rate,epoch = item
            with self.lock:
                if self.paused or epoch != self.epoch:
                    continue
            try:
                engine.setProperty('rate',rate)
                voice = pick_voice(lang)
                if voice:
                    engine.setProperty('voice',voice)
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass


class PushToTalk:
    """Record raw audio on key/button down, decode asynchronously on release."""
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
            self.stream = sd.RawInputStream(samplerate=16000,blocksize=4000,
                                            channels=1,dtype='int16',callback=callback)
            self.stream.start()
        except Exception as exc:
            self.stream = None
            return False,str(exc)
        return True,'recording'

    def stop(self, on_result):
        if self.stream is None:
            return
        stream = self.stream
        self.stream = None
        try:
            stream.stop()
            stream.close()
            samples = b''.join(self.chunks)
        except Exception as exc:
            self.root.after(0,lambda: on_result(None,'',str(exc)))
            return
        lang = self.active_lang
        def decode():
            try:
                from vosk import Model,KaldiRecognizer
                if lang not in self.model_cache:
                    self.model_cache[lang] = Model(os.path.join(self.model_dir,lang))
                model = self.model_cache[lang]
                def interpret(grammar=None):
                    if grammar is None:
                        rec = KaldiRecognizer(model,16000)
                    else:
                        rec = KaldiRecognizer(model,16000,json.dumps(grammar,ensure_ascii=False))
                    rec.AcceptWaveform(samples)
                    return json.loads(rec.FinalResult()).get('text','')
                raw = interpret(grammar_for(lang))
                code = recognize_phrase(raw,lang)
                if code is None and lang == 'zh' and samples:
                    fallback = interpret()
                    alternative = recognize_phrase(fallback,lang)
                    # Show both raw recognitions if neither maps to a command.
                    if alternative is not None:
                        raw,code = fallback,alternative
                    else:
                        raw = 'grammar=%r; free=%r' % (raw,fallback)
                self.root.after(0,lambda: on_result(code,raw,None))
            except Exception as exc:
                self.root.after(0,lambda: on_result(None,'',str(exc)))
        threading.Thread(target=decode,daemon=True).start()