import heapq
import itertools
import unittest
from simulator import Simulator
from voice import recognize_phrase


class Scheduler:
    def __init__(self):
        self.heap=[]
        self.counter=itertools.count()
        self.now=0
    def schedule(self,delay,callback):
        heapq.heappush(self.heap,(self.now+delay,next(self.counter),callback))
    def advance_until(self,condition,limit=10000):
        for _ in range(limit):
            if condition():
                return
            if not self.heap:
                raise RuntimeError('no scheduled events')
            self.now,_,fn=heapq.heappop(self.heap)
            fn()
        raise AssertionError('too many steps')


class SimTests(unittest.TestCase):
    def setUp(self):
        self.s=Scheduler()
        self.sim=Simulator(people=8,reaction=2,schedule=self.s.schedule)

    def wait_prompt(self,side):
        self.s.advance_until(lambda: bool(self.sim.prompts[side]))
        return self.sim.prompts[side][0]

    def test_left_first_two_hops_exact_sequence(self):
        self.assertTrue(self.sim.submit('L','intro_apple')[0])
        self.assertEqual(self.wait_prompt('L').expected,'apple')
        self.sim.submit('L','apple')
        # When left2 eventually asks, left1 must relay What? to the host.
        self.wait_prompt('L')
        observed=[(x.seat,x.phrase,x.direction) for x in self.sim.events]
        self.assertEqual(observed[:6],[
            (0,'intro_apple','down'),(1,'what','up'),
            (0,'apple','down'),(1,'thanks','up'),
            (1,'intro_apple','down'),(2,'what','up')])
        self.s.advance_until(lambda: len(self.sim.events)>=7)
        self.assertEqual((self.sim.events[6].seat,self.sim.events[6].phrase),(1,'what'))
        self.sim.submit('L','apple')
        self.s.advance_until(lambda: len(self.sim.events)>=11)
        self.assertEqual([(x.seat,x.phrase) for x in self.sim.events[7:11]],
                         [(0,'apple'),(1,'thanks'),(1,'apple'),(2,'thanks')])

    def test_right_aliases_and_round_trip(self):
        self.assertEqual(self.sim.seat('L',1),1)
        self.assertEqual(self.sim.seat('R',8),1)
        self.assertEqual(self.sim.seat('L',2),2)
        self.assertEqual(self.sim.seat('R',7),2)
        self.sim.submit('R','intro_banana')
        for hop in range(1,9):
            prompt=self.wait_prompt('R')
            self.assertEqual(prompt.expected,'banana')
            self.assertTrue(self.sim.submit('R','banana')[0])
            self.s.advance_until(lambda: self.sim.streams[1].depth>hop)
        # End of ring reaches host from opposite side (left).
        self.assertEqual(self.wait_prompt('L').expected,'what')
        self.sim.submit('L','what')
        self.assertEqual(self.wait_prompt('R').expected,'banana')
        self.sim.submit('R','banana')
        self.assertEqual(self.wait_prompt('L').expected,'thanks')
        self.sim.submit('L','thanks')
        self.assertTrue(self.sim.streams[1].complete)

    def test_wrong_answer_does_not_advance(self):
        self.sim.submit('L','intro_apple')
        self.wait_prompt('L')
        self.assertEqual(self.sim.submit('L','banana'),(False,'wrong-answer'))
        self.assertEqual(self.sim.prompts['L'][0].expected,'apple')
        self.assertEqual(self.sim.submit('L','apple'),(True,'accepted'))

    def test_dual_start_and_fruit_collisions(self):
        self.sim.submit('L','intro_apple')
        self.sim.submit('R','intro_banana')
        self.wait_prompt('L')
        self.wait_prompt('R')
        self.assertEqual(self.sim.prompts['L'][0].expected,'apple')
        self.assertEqual(self.sim.prompts['R'][0].expected,'banana')
        self.sim.submit('R','banana')
        self.sim.submit('L','apple')
        self.assertEqual(self.sim.status()['active'],2)

    def test_reset_cancels_existing_scheduled_events(self):
        self.sim.submit('L','intro_apple')
        self.sim.reset(8,2)
        while self.s.heap:
            self.s.now,_,fn=heapq.heappop(self.s.heap)
            fn()
        self.assertEqual(self.sim.status()['events'],0)

    def test_six_fixed_phrases_normalized(self):
        self.assertEqual(recognize_phrase('這是蘋果','zh'),'intro_apple')
        self.assertEqual(recognize_phrase('这是香蕉','zh'),'intro_banana')
        self.assertEqual(recognize_phrase('謝謝','zh'),'thanks')
        self.assertEqual(recognize_phrase('this is an apple','en'),'intro_apple')
        self.assertEqual(recognize_phrase('thank you','en'),'thanks')
        self.assertIsNone(recognize_phrase('purple pear','en'))

if __name__=='__main__':
    unittest.main()
