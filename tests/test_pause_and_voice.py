"""Regression coverage for frozen game time and macOS long-press handling."""
import unittest
from types import SimpleNamespace
from app import App
from timing import PauseableClock
from voice import recognize_phrase, grammar_for


class FakeRoot:
    def __init__(self):
        self.jobs = {}
        self.count = 0
    def after(self, delay, callback):
        self.count += 1
        self.jobs[self.count] = callback
        return self.count
    def after_cancel(self, token):
        self.jobs.pop(token, None)
    def fire(self, token):
        callback = self.jobs.pop(token)
        callback()


class ClockTests(unittest.TestCase):
    def test_scheduled_steps_keep_remaining_time(self):
        t=[0.0]
        root=FakeRoot()
        timer=PauseableClock(root,clock=lambda: t[0])
        output=[]
        timer.schedule(2,lambda: output.append(('first',t[0])))
        t[0]=0.8
        root.fire(timer.timer_id)
        timer.pause()
        t[0]=40.8
        root.fire(timer.timer_id)
        self.assertEqual(output,[])
        timer.resume()
        t[0]=41.9
        root.fire(timer.timer_id)
        self.assertEqual(output,[])
        t[0]=42.05
        root.fire(timer.timer_id)
        self.assertEqual([name for name,_ in output],['first'])
        timer.close()

    def test_pause_does_not_burst_or_lose_jobs(self):
        t=[0.0]
        root=FakeRoot()
        timer=PauseableClock(root,clock=lambda:t[0])
        output=[]
        timer.schedule(.4,lambda:output.append('A'))
        timer.schedule(.6,lambda:output.append('B'))
        timer.pause()
        t[0]=15
        root.fire(timer.timer_id)
        self.assertEqual(output,[])
        timer.resume()
        t[0]=15.45
        root.fire(timer.timer_id)
        self.assertEqual(output,['A'])
        t[0]=15.65
        root.fire(timer.timer_id)
        self.assertEqual(output,['A','B'])
        timer.close()


class KeyboardTests(unittest.TestCase):
    def test_repeat_press_release_does_not_restart_recording(self):
        root=FakeRoot()
        app=App.__new__(App)
        app.root=root
        app.active_key=None
        app.release_job=None
        pressed=[]; released=[]
        app.press=lambda side: pressed.append(side)
        app.release=lambda side: released.append(side)
        app.key_down('L')
        self.assertEqual(pressed,['L'])
        app.key_up('L')
        first_release=app.release_job
        app.key_down('L')  # synthetic repeat after apparent release
        self.assertNotIn(first_release,root.jobs)
        app.key_up('L')
        last=app.release_job
        root.fire(last)
        self.assertEqual(pressed,['L'])
        self.assertEqual(released,['L'])
        self.assertIsNone(app.active_key)

    def test_key_for_other_side_does_not_steal_current_recording(self):
        root=FakeRoot()
        app=App.__new__(App)
        app.root=root
        app.active_key=None
        app.release_job=None
        pressed=[]
        app.press=lambda side: pressed.append(side)
        app.release=lambda side: None
        app.key_down('L')
        app.key_down('R')
        self.assertEqual(pressed,['L'])
        app.key_up('R')
        self.assertIsNone(app.release_job)


class RecordingIntegrationTests(unittest.TestCase):
    def test_press_halts_game_until_voice_decoding_has_finished(self):
        app=App.__new__(App)
        app.recording_side=None
        app.selected=SimpleNamespace(set=lambda side: None)
        app.lang=SimpleNamespace(get=lambda: 'zh')
        calls=[]
        app.clock=SimpleNamespace(pause=lambda:calls.append('clock-pause'),
                                  resume=lambda:calls.append('clock-resume'))
        app.speaker=SimpleNamespace(pause=lambda:calls.append('speaker-pause'),
                                    resume=lambda:calls.append('speaker-resume'))
        class FakeMic:
            def start(self,lang):
                calls.append('mic-start')
                return True,'recording'
            def stop(self,callback):
                calls.append('mic-stop')
                self.callback=callback
        app.mic=FakeMic()
        app.t=lambda name:name+' {raw} {phrase}' if name=='recognized' else name
        app.set_notice=lambda msg:calls.append(('notice',msg))
        app.submit=lambda side,code:calls.append(('submitted',side,code))
        app.press('L')
        app.press('L')
        self.assertEqual(calls[:3],['clock-pause','speaker-pause','mic-start'])
        self.assertEqual(calls.count('mic-start'),1)
        app.release('L')
        self.assertNotIn('clock-resume',calls)
        app.mic.callback('intro_apple','这是苹果',None)
        self.assertIn(('submitted','L','intro_apple'),calls)
        self.assertEqual(calls[-2:],['speaker-resume','clock-resume'])
        self.assertIsNone(app.recording_side)


class ChineseTests(unittest.TestCase):
    def test_normalizes_simplified_and_traditional_spaced_phrases(self):
        cases=[('这 是 苹果','intro_apple'),('這是蘋果','intro_apple'),
               ('这是一个香蕉','intro_banana'),('这时苹果','intro_apple'),
               ('什 麼','what'),('谢 谢','thanks'),('谢谢你','thanks')]
        for spoken,code in cases:
            self.assertEqual(recognize_phrase(spoken,'zh'),code)
        self.assertIsNone(recognize_phrase('天气真好','zh'))
        self.assertIn('这 是 苹果',grammar_for('zh'))


if __name__=='__main__':
    unittest.main()