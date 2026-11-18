#!/usr/bin/env python3
"""A What? | 問什麼？ — bilingual interactive Tkinter game.

Run: python app.py
Optional offline TTS: pip install pyttsx3
Optional offline microphone: pip install vosk sounddevice, add model dirs.
"""
import csv
import math
import os
import platform
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime

from simulator import Simulator, PHRASES
from voice import PushToTalk, Speaker

BASE = os.path.dirname(os.path.abspath(__file__))
BG = '#0b1729'
PANEL = '#17263e'
PANEL2 = '#21334b'
TEXT = '#f3f6fc'
MUTED = '#aab8cf'
YELLOW = '#f6bf58'
GREEN = '#54d7a9'
BLUE = '#94aaff'

STRINGS = {
 'zh': {
  'title':'A What? ｜ 口語傳遞模擬器',
  'language':'語言', 'people':'虛擬人數（不含你）',
  'reaction':'反應時間（秒）', 'rate':'語速', 'audio':'播放語音',
  'reset':'套用設定／重新開始', 'export':'匯出紀錄 CSV',
  'host':'主持人（你）', 'left':'左側', 'right':'右側',
  'up':'黃色：向源頭追問／致謝', 'down':'綠色：向下一位傳遞／回答',
  'instructions':'按住左／右側區塊或 ←／→ 鍵說話；放開後辨識。\n未安裝離線語音模型時，改按下面六句台詞。',
  'hold':'按住說話', 'pending':'待你回覆', 'log':'對話與事件紀錄',
  'none':'目前沒有待回覆訊息', 'answer':'有人問了「什麼」；請回答水果',
  'ask-back':'訊息繞回你這裡；先問「什麼」',
  'finish':'答案傳回來了；請說「謝謝」',
  'invalid':'這一側目前沒有等待這句話；先檢查傳遞順序',
  'no-prompt':'這一側目前沒有人在等待你回話',
  'mic-unavailable':'麥克風尚未啟用：需安裝 vosk、sounddevice 和語音模型；可使用文字按鈕。',
  'recording':'錄音中，放開按鍵完成辨識…',
  'not-understood':'沒有辨識出六句指定台詞，請再說一次。',
  'voice-error':'語音辨識錯誤：', 'new':'新訊息已送出',
  'done':'一條訊息完成環繞，回到主持人！',
  'intro':'可以隨時從任一側發起新的蘋果或香蕉訊息。',
  'stats':'進行中 {active}｜已完成 {completed}｜發話 {events}',
 },
 'en': {
  'title':'A What? | Verbal Relay Simulator',
  'language':'Language', 'people':'Simulated people (excluding you)',
  'reaction':'Reaction time (sec)', 'rate':'Speech rate', 'audio':'Speak aloud',
  'reset':'Apply / Restart', 'export':'Export log CSV',
  'host':'Host (you)', 'left':'LEFT', 'right':'RIGHT',
  'up':'Yellow: ask / thank upstream', 'down':'Green: relay / answer downstream',
  'instructions':'Hold a LEFT / RIGHT pad or ← / → key to speak; release to recognize.\nWithout an offline speech model, use the six phrase buttons.',
  'hold':'Hold to speak', 'pending':'Waiting on you',
  'log':'Dialogue and event log', 'none':'No reply needed yet',
  'answer':'Someone asked “What?”; answer with the fruit',
  'ask-back':'A message reached you; first say “What?”',
  'finish':'The answer came back; say “Thank you”',
  'invalid':'That phrase is not expected on this side; check the relay order',
  'no-prompt':'Nobody is waiting for an answer on this side',
  'mic-unavailable':'Microphone not enabled: install vosk, sounddevice and a model; use phrase buttons instead.',
  'recording':'Recording; release to recognize…',
  'not-understood':'Could not recognize one of the six phrases; please retry.',
  'voice-error':'Speech recognition error: ', 'new':'New message started',
  'done':'A message has circled all the way back to the host!',
  'intro':'Start another apple or banana from either side at any time.',
  'stats':'Active {active} | Complete {completed} | Utterances {events}',
 },
}
ZH_NUM = ['零','一','二','三','四','五','六','七','八','九','十']

def zh_number(n):
    if n < len(ZH_NUM):
        return ZH_NUM[n]
    return '十' + ZH_NUM[n-10] if n < 20 else str(n)


def seat_layout(people, width, height):
    """Return a close, nearly circular ellipse with the host at the bottom.

    Seat numbers increase toward the host's *left* as viewed on screen.
    Each physical seat has both a left- and a right-hand alias.
    """
    w=max(width, 580)
    h=max(height, 430)
    count=people+1
    cx,cy=w/2, h/2
    # Wider than tall by only 16%; deliberately avoid a distant table view.
    rx=min(w*0.305, (h-112)*0.5*1.16, 228)
    ry=rx/1.16
    # Respect the gap between adjacent seats as the number of players grows.
    node_r=max(23, min(38, ry*math.sin(math.pi/count)*0.75))
    positions={}
    for seat in range(count):
        angle=math.pi+seat*2*math.pi/count
        positions[seat]=(cx+rx*math.sin(angle), cy-ry*math.cos(angle))
    return (cx,cy,rx,ry,node_r,positions)


class App:
    def __init__(self, root):
        self.root = root
        self.lang = tk.StringVar(value='zh')
        self.people_var = tk.IntVar(value=8)
        self.delay_var = tk.DoubleVar(value=2.0)
        self.rate_var = tk.IntVar(value=150)
        self.audio_var = tk.BooleanVar(value=True)
        self.selected = tk.StringVar(value='L')
        self.active_key = None
        self.last_event = {}
        self.last_serial = {}
        self.serial = 0
        self.session_start = datetime.now()
        self.recorded = []
        self.speaker = Speaker()
        self.audio_var.set(self.speaker.available)
        self.mic = PushToTalk(root, model_dir=os.path.join(BASE, 'models'))
        self.engine = Simulator(people=8, reaction=2.,
                                schedule=self.schedule,
                                on_event=self.on_event,
                                on_prompt=self.on_prompt,
                                on_status=self.on_status)
        self.build()
        self.translate()
        self.redraw()
        self.root.bind('<KeyPress-Left>', lambda e: self.key_down('L'))
        self.root.bind('<KeyPress-Right>', lambda e: self.key_down('R'))
        self.root.bind('<KeyRelease-Left>', lambda e: self.key_up('L'))
        self.root.bind('<KeyRelease-Right>', lambda e: self.key_up('R'))
        self.root.bind('<KeyPress>', self.number_key)
        self.root.protocol('WM_DELETE_WINDOW', self.close)

    def t(self, name):
        return STRINGS[self.lang.get()][name]

    def schedule(self, seconds, fn):
        self.root.after(max(0, int(seconds*1000)), fn)

    def frame(self, parent, **kw):
        return tk.Frame(parent, bg=PANEL, **kw)

    def label(self, parent, text='', fg=TEXT, size=11, bold=False, **kw):
        family = 'Microsoft JhengHei' if platform.system() == 'Windows' else (
            'PingFang TC' if platform.system() == 'Darwin' else 'DejaVu Sans')
        return tk.Label(parent, text=text, fg=fg, bg=parent['bg'],
                        font=(family,size,'bold' if bold else 'normal'), **kw)

    def button(self, parent, text, command, bg=PANEL2, fg=TEXT, **kw):
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground='#304760', activeforeground=TEXT,
                         relief='flat', bd=0, padx=6, pady=7, cursor='hand2', **kw)

    def build(self):
        self.root.title('A What? | Verbal Relay Simulator')
        self.root.configure(bg=BG)
        self.root.geometry('1220x880')
        self.root.minsize(1030, 740)
        top = tk.Frame(self.root,bg=BG)
        top.pack(fill='x',padx=18,pady=(12,8))
        self.title_label = self.label(top,size=17,bold=True)
        self.title_label.pack(side='left')
        settings = tk.Frame(self.root,bg=PANEL,padx=12,pady=10)
        settings.pack(fill='x',padx=18,pady=(0,9))
        self.people_lbl = self.label(settings,size=9)
        self.people_lbl.pack(side='left')
        tk.Spinbox(settings,from_=3,to=16,width=3,textvariable=self.people_var).pack(side='left',padx=(6,13))
        self.delay_lbl = self.label(settings,size=9)
        self.delay_lbl.pack(side='left')
        tk.Spinbox(settings,from_=0,to=10,increment=.5,width=4,textvariable=self.delay_var).pack(side='left',padx=(6,13))
        self.rate_lbl = self.label(settings,size=9)
        self.rate_lbl.pack(side='left')
        tk.Scale(settings,from_=100,to=220,orient='horizontal',variable=self.rate_var,
                 showvalue=True,bd=0,length=125,highlightthickness=0,
                 bg=PANEL,fg=TEXT,troughcolor=PANEL2,command=self.set_rate).pack(side='left',padx=3)
        self.audio_chk = tk.Checkbutton(settings,variable=self.audio_var,
                                        bg=PANEL,fg=TEXT,selectcolor=BG,
                                        activebackground=PANEL,activeforeground=TEXT,
                                        command=self.set_audio)
        self.audio_chk.pack(side='left',padx=8)
        language_menu = ttk.Combobox(settings,values=['繁體中文','English'],width=10,state='readonly')
        language_menu.current(0)
        language_menu.pack(side='right')
        language_menu.bind('<<ComboboxSelected>>',lambda e:self.switch_lang(language_menu.current()))
        self.language_lbl = self.label(settings,size=9)
        self.language_lbl.pack(side='right',padx=7)
        row = tk.Frame(self.root,bg=BG)
        row.pack(fill='both',expand=True,padx=18)
        left_frame = tk.Frame(row,bg=PANEL)
        left_frame.pack(side='left',fill='both',expand=True,padx=(0,10))
        self.canvas = tk.Canvas(left_frame,bg=PANEL,bd=0,highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>', lambda e:self.redraw())
        legend = tk.Frame(left_frame,bg=PANEL,pady=7)
        legend.pack(fill='x')
        self.legend_up=self.label(legend,fg=YELLOW,size=9)
        self.legend_up.pack(side='left',padx=14)
        self.legend_down=self.label(legend,fg=GREEN,size=9)
        self.legend_down.pack(side='left')
        right_frame = tk.Frame(row,bg=PANEL,width=415,padx=12,pady=12)
        right_frame.pack(side='right',fill='y')
        right_frame.pack_propagate(False)
        # The bilingual instructions can wrap differently. Reserve their area
        # too, so switching languages never shifts the controls mid-session.
        instructions_slot=tk.Frame(right_frame,bg=PANEL,height=62)
        instructions_slot.pack(fill='x',pady=(0,7))
        instructions_slot.pack_propagate(False)
        self.instructions=self.label(instructions_slot,fg=MUTED,size=9,
                                     justify='left',wraplength=390,anchor='nw')
        self.instructions.place(x=0,y=0,relwidth=1,relheight=1)
        pair = tk.Frame(right_frame,bg=PANEL)
        pair.pack(fill='x')
        self.side_frames = {}
        self.side_lbls={}
        self.pad_btns={}
        self.prompt_lbls={}
        self.phrase_btns={}
        for side in ('L','R'):
            col=tk.Frame(pair,bg=PANEL2,padx=7,pady=9)
            col.pack(side='left',fill='both',expand=True,padx=(0,3) if side=='L' else (3,0))
            self.side_frames[side]=col
            self.side_lbls[side]=self.label(col,size=13,bold=True)
            self.side_lbls[side].pack(pady=(0,5))
            pad=tk.Label(col,bg='#37516a',fg=TEXT,font=('Arial',11,'bold'),
                         relief='raised',bd=1,height=3,justify='center')
            pad.pack(fill='x',pady=(0,5))
            pad.bind('<ButtonPress-1>',lambda e,s=side:self.press(s))
            pad.bind('<ButtonRelease-1>',lambda e,s=side:self.release(s))
            self.pad_btns[side]=pad
            # Reserve a constant-height status area. A pending reply can add
            # multiple lines of text, but must NEVER move any phrase button:
            # the player may already be aiming at one of those positions.
            prompt_slot=tk.Frame(col,bg=PANEL2,height=68)
            prompt_slot.pack(fill='x',pady=(0,7))
            prompt_slot.pack_propagate(False)
            pl=self.label(prompt_slot,fg=YELLOW,size=9,
                          wraplength=175,justify='left',anchor='nw')
            pl.place(x=0,y=0,relwidth=1,relheight=1)
            self.prompt_lbls[side]=pl
            self.phrase_btns[side]={}
            for code in ('intro_apple','intro_banana','apple','banana','what','thanks'):
                fg=GREEN if code in ('intro_apple','intro_banana','apple','banana') else YELLOW
                b=self.button(col,'',lambda s=side,c=code:self.submit(s,c),fg=fg)
                b.pack(fill='x',pady=2)
                self.phrase_btns[side][code]=b
        buttons=tk.Frame(right_frame,bg=PANEL)
        buttons.pack(fill='x',pady=(11,2))
        self.reset_btn=self.button(buttons,'',self.reset,bg='#3858a0')
        self.reset_btn.pack(side='left',fill='x',expand=True,padx=(0,3))
        self.export_btn=self.button(buttons,'',self.export_csv)
        self.export_btn.pack(side='left',fill='x',expand=True,padx=(3,0))
        self.notice=self.label(right_frame,fg=YELLOW,size=9,justify='left',wraplength=390)
        self.notice.pack(fill='x',pady=(8,0))
        self.stat_lbl=self.label(self.root,fg=MUTED,size=9)
        self.stat_lbl.pack(anchor='w',padx=22,pady=(8,3))
        log_frame=tk.Frame(self.root,bg=PANEL)
        log_frame.pack(fill='x',padx=18,pady=(0,12))
        self.log_title=self.label(log_frame,size=10,bold=True)
        self.log_title.pack(anchor='w',padx=10,pady=(7,3))
        self.log_text=tk.Text(log_frame,height=7,wrap='word',bg=BG,fg=TEXT,
                              insertbackground=TEXT,relief='flat',bd=0,font=('Consolas',10))
        self.log_text.pack(side='left',fill='both',expand=True,padx=(10,0),pady=(0,8))
        scroll=tk.Scrollbar(log_frame,command=self.log_text.yview)
        scroll.pack(side='right',fill='y')
        self.log_text.configure(yscrollcommand=scroll.set,state='disabled')

    def switch_lang(self,index):
        self.lang.set('zh' if index==0 else 'en')
        self.translate()
        self.redraw()
        self.on_prompt(self.engine.prompts)

    def translate(self):
        self.title_label.configure(text=self.t('title'))
        self.people_lbl.configure(text=self.t('people'))
        self.delay_lbl.configure(text=self.t('reaction'))
        self.rate_lbl.configure(text=self.t('rate'))
        self.audio_chk.configure(text=self.t('audio'))
        self.language_lbl.configure(text=self.t('language'))
        self.legend_up.configure(text=self.t('up'))
        self.legend_down.configure(text=self.t('down'))
        self.instructions.configure(text=self.t('instructions'))
        self.reset_btn.configure(text=self.t('reset'))
        self.export_btn.configure(text=self.t('export'))
        self.log_title.configure(text=self.t('log'))
        for side in ('L','R'):
            self.side_lbls[side].configure(text=self.t('left' if side=='L' else 'right'))
            self.pad_btns[side].configure(text='◉  '+self.t('hold')+'  ◉')
            for code,b in self.phrase_btns[side].items():
                b.configure(text=PHRASES[self.lang.get()][code])
        self.update_stats()

    def set_rate(self, *_):
        self.speaker.rate=self.rate_var.get()

    def set_audio(self):
        self.speaker.enabled=self.audio_var.get() and self.speaker.available
        if self.audio_var.get() and not self.speaker.available:
            self.set_notice("pyttsx3 not installed: pip install -r requirements-audio.txt")

    def _name(self,seat):
        if seat == 0:
            return self.t('host')
        left=seat
        right=self.engine.people+1-seat
        if self.lang.get()=='zh':
            return '左%s（右%s）' % (zh_number(left),zh_number(right))
        return 'L%d (R%d)' % (left,right)

    def redraw(self):
        if not hasattr(self,'canvas'):
            return
        c=self.canvas
        c.delete('all')
        w=max(c.winfo_width(),580)
        h=max(c.winfo_height(),430)
        cx,cy,rx,ry,node_r,positions=seat_layout(self.engine.people,w,h)
        n=self.engine.people+1

        c.create_oval(cx-rx,cy-ry,cx+rx,cy+ry,
                      outline='#415677',width=2,dash=(5,6))
        for seat in range(n):
            x,y=positions[seat]
            event=self.last_event.get(seat)
            col=YELLOW if event and event.direction=='up' else GREEN if event else '#2b4060'
            active=bool(event)
            c.create_oval(x-node_r,y-node_r,x+node_r,y+node_r,fill=col if active else PANEL2,
                          outline=col,width=2)
            name=self._name(seat)
            fontsize=9 if n<=11 else 7
            c.create_text(x,y-9 if active else y,text=name,fill=BG if active else TEXT,
                          font=('Arial',fontsize,'bold'),width=node_r*2+14)
            if active:
                phrase=PHRASES[self.lang.get()][event.phrase]
                c.create_text(x,y+15,text=phrase,fill=BG,font=('Arial',10,'bold'),width=node_r*2+16)

        info_y=cy-6
        c.create_text(cx,info_y-16,text='A WHAT?',font=('Arial',16,'bold'),fill=TEXT)
        c.create_text(cx,info_y+10,text='🍎    🍌',font=('Arial',15),fill=MUTED)
        c.create_text(cx,info_y+39,text=('問 ↗　答 ↘' if self.lang.get()=='zh' else 'ASK ↗   REPLY ↘'),
                      font=('Arial',10),fill=MUTED)

    def update_stats(self):
        status=self.engine.status()
        self.stat_lbl.configure(text=self.t('stats').format(**status))

    def set_notice(self,message):
        self.notice.configure(text=message)

    def log(self,stream,seat,phrase,dir):
        now=datetime.now().strftime('%H:%M:%S')
        line='[%s] #%d %s  %s  %s\n' % (now,stream,self._name(seat),
                             '↑' if dir=='up' else '↓',PHRASES[self.lang.get()][phrase])
        self.log_text.configure(state='normal')
        self.log_text.insert('end',line)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def on_event(self,event):
        self.last_event[event.seat]=event
        self.serial+=1
        seq=self.serial
        self.last_serial[event.seat]=seq
        self.redraw()
        self.log(event.stream_id,event.seat,event.phrase,event.direction)
        self.recorded.append((datetime.now().isoformat(timespec='milliseconds'),
                              event.stream_id,event.seat,event.side,
                              event.direction,event.phrase,event.human))
        if not event.human and self.audio_var.get():
            self.speaker.say(PHRASES[self.lang.get()][event.phrase],self.lang.get())
        def clear():
            if self.last_serial.get(event.seat)==seq:
                self.last_event.pop(event.seat,None)
                self.redraw()
        self.root.after(max(1800,int(self.engine.reaction*1000)),clear)
        self.update_stats()

    def on_prompt(self,prompts):
        if not hasattr(self,'prompt_lbls'):
            return
        for side in ('L','R'):
            q=prompts[side]
            if not q:
                text=self.t('none')
            else:
                p=q[0]
                text='%s: %d\n%s' % (self.t('pending'),len(q),self.t(p.context))
            self.prompt_lbls[side].configure(text=text)
            self.pad_btns[side].configure(bg='#56678b' if q else '#37516a')
        self.update_stats()

    def on_status(self,status):
        if status=='started':
            self.set_notice(self.t('new'))
        elif status=='completed':
            self.set_notice(self.t('done'))
        elif status=='reset':
            self.set_notice(self.t('intro'))
        if hasattr(self,'stat_lbl'):
            self.update_stats()

    def submit(self,side,phrase):
        self.selected.set(side)
        ok,reason=self.engine.submit(side,phrase)
        if not ok:
            self.set_notice(self.t('no-prompt' if reason=='no-prompt' else 'invalid'))
        self.update_stats()

    def key_down(self,side):
        if self.active_key:
            return 'break'
        self.active_key=side
        self.press(side)
        return 'break'

    def key_up(self,side):
        if self.active_key==side:
            self.active_key=None
            self.release(side)
        return 'break'

    def number_key(self,event):
        if event.char in '123456':
            code=('intro_apple','intro_banana','apple','banana','what','thanks')[int(event.char)-1]
            self.submit(self.selected.get(),code)

    def press(self,side):
        self.selected.set(side)
        ok,reason=self.mic.start(self.lang.get())
        if not ok:
            self.set_notice(self.t('mic-unavailable') if reason=='no-model-or-package' else reason)
        else:
            self.set_notice(self.t('recording'))

    def release(self,side):
        if self.mic.stream is None:
            return
        self.mic.stop(lambda code,raw,error:self.mic_result(side,code,raw,error))

    def mic_result(self,side,code,raw,error):
        if error:
            self.set_notice(self.t('voice-error')+error)
        elif code:
            self.submit(side,code)
        else:
            self.set_notice(self.t('not-understood')+' ['+raw+']')

    def reset(self):
        try:
            count=int(self.people_var.get())
            delay=float(self.delay_var.get())
            if not 3<=count<=16 or not 0<=delay<=10:
                raise ValueError()
        except (ValueError,tk.TclError):
            messagebox.showerror('Invalid settings','People: 3–16; reaction: 0–10 seconds.')
            return
        self.engine.reset(count,delay)
        self.last_event.clear()
        self.last_serial.clear()
        self.recorded.clear()
        self.session_start=datetime.now()
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0','end')
        self.log_text.configure(state='disabled')
        self.speaker.rate=int(self.rate_var.get())
        self.redraw()

    def export_csv(self):
        path=filedialog.asksaveasfilename(defaultextension='.csv',
                                           initialfile='a-what-log.csv',
                                           filetypes=[('CSV files','*.csv')])
        if not path:
            return
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            wr=csv.writer(f)
            wr.writerow(['timestamp','stream_id','seat','original_side','direction','phrase_key','human'])
            wr.writerows(self.recorded)

    def close(self):
        self.speaker.close()
        self.root.destroy()


def main():
    root=tk.Tk()
    App(root)
    root.mainloop()

if __name__=='__main__':
    main()
