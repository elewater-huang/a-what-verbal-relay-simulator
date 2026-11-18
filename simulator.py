"""Event-driven A What? / Apple and Banana speaking-chain simulator.

No GUI or audio dependencies: deterministic scheduling is injected by the caller.
Python 3.7+.
"""
from dataclasses import dataclass
from collections import deque

PHRASES = {
    'zh': {
        'intro_apple': '這是蘋果', 'intro_banana': '這是香蕉',
        'apple': '蘋果', 'banana': '香蕉',
        'what': '什麼', 'thanks': '謝謝',
    },
    'en': {
        'intro_apple': 'This is an apple', 'intro_banana': 'This is a banana',
        'apple': 'Apple', 'banana': 'Banana',
        'what': 'What?', 'thanks': 'Thank you',
    },
}

INTRO = {'intro_apple': 'apple', 'intro_banana': 'banana'}


@dataclass
class Event:
    stream_id: int
    side: str
    seat: int
    phrase: str
    direction: str  # up = yellow, down = green
    human: bool = False


@dataclass
class Prompt:
    stream_id: int
    side: str
    expected: str
    context: str  # answer, ask-back, finish


@dataclass
class Stream:
    id: int
    side: str
    fruit: str
    depth: int = 1
    complete: bool = False


class Simulator:
    """Allows simultaneous independent messages to circulate in both directions.

    A depth-d message must ask 'what' from d all the way to the origin,
    before the answer moves from the origin to d. Each intermediate speaker
    acknowledges up-chain ('thanks') before answering down-chain ('apple').
    """
    def __init__(self, people=8, reaction=2.0, schedule=None,
                 on_event=None, on_prompt=None, on_status=None):
        if not 3 <= people <= 16:
            raise ValueError('people must be between 3 and 16')
        self.people = people
        self.reaction = float(reaction)
        self._schedule_fn = schedule or (lambda delay, fn: fn())
        self.on_event = on_event or (lambda event: None)
        self.on_prompt = on_prompt or (lambda prompts: None)
        self.on_status = on_status or (lambda message: None)
        self.streams = {}
        self.prompts = {'L': deque(), 'R': deque()}
        self.events = []
        self.seq = 0
        self.generation = 0

    def reset(self, people=None, reaction=None):
        self.generation += 1
        if people is not None:
            if not 3 <= int(people) <= 16:
                raise ValueError('people must be between 3 and 16')
            self.people = int(people)
        if reaction is not None:
            self.reaction = float(reaction)
        self.streams.clear()
        self.prompts = {'L': deque(), 'R': deque()}
        self.events.clear()
        self.seq = 0
        self.on_prompt(self.prompts)
        self.on_status('reset')

    @staticmethod
    def opposite(side):
        return 'R' if side == 'L' else 'L'

    def seat(self, side, distance):
        """Unique physical seat for left/right aliases; host is seat zero."""
        total = self.people + 1
        return distance % total if side == 'L' else (-distance) % total

    def _later(self, fn, delay=None):
        gen = self.generation
        wait = self.reaction if delay is None else delay
        def guarded():
            if gen == self.generation:
                fn()
        self._schedule_fn(wait, guarded)

    def _say(self, stream, distance, phrase, direction, human=False):
        event = Event(stream.id, stream.side, self.seat(stream.side, distance),
                      phrase, direction, human)
        self.events.append(event)
        self.on_event(event)

    def _prompt(self, stream, side, expected, context):
        prompt = Prompt(stream.id, side, expected, context)
        self.prompts[side].append(prompt)
        self.on_prompt(self.prompts)

    def submit(self, side, phrase):
        """Handle six user phrases. Intro starts a fresh stream; others answer prompts."""
        if side not in ('L', 'R') or phrase not in PHRASES['zh']:
            return False, 'invalid'
        if phrase in INTRO:
            self.seq += 1
            stream = Stream(self.seq, side, INTRO[phrase])
            self.streams[stream.id] = stream
            self._say(stream, 0, phrase, 'down', human=True)
            self._later(lambda: self._ask_upstream(stream, 1))
            self.on_status('started')
            return True, 'started'

        pending = self.prompts[side]
        if not pending:
            return False, 'no-prompt'
        # In same-side collisions there is no audible identifier to know which
        # request is being answered; serialize the queue FIFO and expose that.
        prompt = pending[0]
        if phrase != prompt.expected:
            return False, 'wrong-answer'
        pending.popleft()
        self.on_prompt(self.prompts)
        stream = self.streams[prompt.stream_id]
        position = 0
        self._say(stream, position, phrase,
                  'up' if phrase in ('what', 'thanks') else 'down', human=True)
        if prompt.context == 'ask-back':
            self._later(lambda: self._ask_upstream(stream, self.people))
        elif prompt.context == 'answer':
            self._later(lambda: self._answer_downstream(stream, 1))
        elif prompt.context == 'finish':
            stream.complete = True
            self.on_status('completed')
        return True, 'accepted'

    def _ask_upstream(self, stream, distance):
        if stream.complete:
            return
        if distance == self.people + 1:
            # The phrase has reached the host from the *other* neighbor.
            # Host must say 'What?' to this neighbor before query relays back.
            self._prompt(stream, self.opposite(stream.side), 'what', 'ask-back')
        elif distance >= 1:
            self._say(stream, distance, 'what', 'up')
            self._later(lambda: self._ask_upstream(stream, distance - 1))
        else:
            self._prompt(stream, stream.side, stream.fruit, 'answer')

    def _answer_downstream(self, stream, distance):
        if stream.complete:
            return
        if distance == self.people + 1:
            self._prompt(stream, self.opposite(stream.side), 'thanks', 'finish')
            return
        self._say(stream, distance, 'thanks', 'up')
        if distance < stream.depth:
            def relay():
                self._say(stream, distance, stream.fruit, 'down')
                self._later(lambda: self._answer_downstream(stream, distance+1))
            self._later(relay)
        else:
            # Next hop. Receiver now becomes the sender of 'This is an ...'.
            stream.depth += 1
            def next_hop():
                self._say(stream, distance, 'intro_' + stream.fruit, 'down')
                self._later(lambda: self._ask_upstream(stream, stream.depth))
            self._later(next_hop)

    def status(self):
        return {
            'active': sum(1 for x in self.streams.values() if not x.complete),
            'completed': sum(1 for x in self.streams.values() if x.complete),
            'waiting_left': len(self.prompts['L']),
            'waiting_right': len(self.prompts['R']),
            'events': len(self.events),
        }
