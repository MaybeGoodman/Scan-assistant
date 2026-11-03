"""Original sample content for the V1.0 eight-module run (all text written for this repo).

Markup inside paragraph strings: $...$ is math LaTeX, @...@ is chemistry LaTeX.
Each module has one comprehensive source question (with printed answer/analysis,
which the student view must drop) and three variants with internal answers,
solution, deterministic checks and the module review checklist.
"""
import re

TOKEN = re.compile(r'\$([^$]+)\$|@([^@]+)@')


def runs(text):
    out, pos = [], 0
    for match in TOKEN.finditer(text):
        if match.start() > pos:
            out.append({'type': 'text', 'text': text[pos:match.start()]})
        if match[1] is not None:
            out.append({'type': 'math', 'latex': match[1]})
        else:
            out.append({'type': 'chemistry', 'latex': match[2]})
        pos = match.end()
    if pos < len(text):
        out.append({'type': 'text', 'text': text[pos:]})
    return out


def para(block_id, text, role=None):
    parts = runs(text)
    block = {'type': 'text', 'id': block_id}
    if len(parts) == 1 and parts[0]['type'] == 'text':
        block['text'] = parts[0]['text']
    else:
        block['runs'] = parts
    if role:
        block['role'] = role
    return block


def checklist(code, notes):
    from subjects import MODULES
    return {'checklist': {key: True for key in MODULES[code]['checklist']}, 'notes': notes}


# ---------------------------------------------------------------- M01 初中数学
M01 = {
    'code': 'M01', 'number': '18', 'title': '九年级数学 等腰三角形综合练习', 'figure': 'triangle',
    'triangle': {'ab': 10, 'bc': 12},
    'stem': ['18．如图，在$\\triangle ABC$中，$AB=AC$，$D$是$BC$的中点，连接$AD$，$DE\\perp AB$于点$E$。'],
    'subs': [('(1)', '（1）求证：$\\angle BAD=\\angle CAD$；', []),
             ('(2)', '（2）若$AB=10$，$BC=12$，求$AD$的长；', []),
             ('(3)', '（3）在（2）的条件下，求$DE$的长。', ['(2)'])],
    'answer': ['【答案】（1）见解析；（2）$AD=8$；（3）$DE=\\frac{24}{5}$。',
               '【解析】（3）由面积法，$\\frac{1}{2}AB\\cdot DE=\\frac{1}{2}BD\\cdot AD$，得$DE=\\frac{6\\times 8}{10}=\\frac{24}{5}$。'],
}
M01['variants'] = [
    {'triangle': {'ab': 13, 'bc': 10},
     'stem': ['如图，在$\\triangle ABC$中，$AB=AC=13$，$BC=10$，$D$为$BC$的中点，$DE\\perp AB$，垂足为$E$。'],
     'subs': ['（1）求证：$AD\\perp BC$；', '（2）求$AD$的长；', '（3）求$DE$的长。'],
     'answers': {'(1)': '由SSS证△ABD≌△ACD，得∠ADB=∠ADC=90°，故AD⊥BC',
                 '(2)': 'AD=12', '(3)': 'DE=60/13'},
     'solution': 'BD=5，AD=√(13²−5²)=12；面积法 13·DE=5·12，DE=60/13。',
     'checks': [{'kind': 'arith', 'item': '(2)', 'expr': 'sqrt(13**2-5**2)', 'expect': '12'},
                {'kind': 'arith', 'item': '(3)', 'expr': '5*12/13', 'expect': '60/13'},
                {'kind': 'semantic', 'item': '(1)', 'independent_answer': '由SSS证△ABD≌△ACD，得∠ADB=∠ADC=90°，故AD⊥BC'},
                {'kind': 'semantic', 'item': '(2)', 'independent_answer': 'AD=12'},
                {'kind': 'semantic', 'item': '(3)', 'independent_answer': 'DE=60/13'}],
     'design': {'difference_from_source': '证明目标由“角平分”改为“垂直”，数据改为5-12-13组合',
                'difference_from_siblings': '直接给腰和底'}},
    {'triangle': {'ab': 10, 'bc': 16},
     'stem': ['如图，等腰$\\triangle ABC$的周长为$36$，底边$BC=16$，$AB=AC$，点$D$是$BC$的中点，过$D$作$DE\\perp AB$于$E$。'],
     'subs': ['（1）求证：$\\angle BAD=\\angle CAD$；', '（2）求腰长$AB$及$AD$的长；', '（3）求$DE$的长。'],
     'answers': {'(1)': '由SSS证△ABD≌△ACD，得∠BAD=∠CAD', '(2)': 'AB=10，AD=6', '(3)': 'DE=24/5'},
     'solution': 'AB=(36−16)/2=10，BD=8，AD=√(100−64)=6；10·DE=8·6，DE=24/5。',
     'checks': [{'kind': 'arith', 'item': '(2)', 'expr': '(36-16)/2', 'expect': '10'},
                {'kind': 'arith', 'item': '(2)', 'expr': 'sqrt(10**2-8**2)', 'expect': '6'},
                {'kind': 'arith', 'item': '(3)', 'expr': '8*6/10', 'expect': '24/5'},
                {'kind': 'semantic', 'item': '(1)', 'independent_answer': '由SSS证△ABD≌△ACD，得∠BAD=∠CAD'},
                {'kind': 'semantic', 'item': '(2)', 'independent_answer': 'AB=10，AD=6'},
                {'kind': 'semantic', 'item': '(3)', 'independent_answer': 'DE=24/5'}],
     'design': {'difference_from_source': '条件改为周长和底边，需先求腰长',
                'difference_from_siblings': '增加由周长求腰的条件转换'}},
    {'triangle': {'ab': 17, 'bc': 16},
     'stem': ['如图，在$\\triangle ABC$中，$AB=AC=17$，$D$是$BC$的中点，$AD=15$，$DE\\perp AB$于点$E$。'],
     'subs': ['（1）求证：$\\angle BAD=\\angle CAD$；', '（2）求$BC$的长；', '（3）求$DE$的长。'],
     'answers': {'(1)': '由SSS证△ABD≌△ACD，得∠BAD=∠CAD', '(2)': 'BC=16', '(3)': 'DE=120/17'},
     'solution': 'AD⊥BC，BD=√(17²−15²)=8，BC=16；17·DE=8·15，DE=120/17。',
     'checks': [{'kind': 'arith', 'item': '(2)', 'expr': '2*sqrt(17**2-15**2)', 'expect': '16'},
                {'kind': 'arith', 'item': '(3)', 'expr': '8*15/17', 'expect': '120/17'},
                {'kind': 'semantic', 'item': '(1)', 'independent_answer': '由SSS证△ABD≌△ACD，得∠BAD=∠CAD'},
                {'kind': 'semantic', 'item': '(2)', 'independent_answer': 'BC=16'},
                {'kind': 'semantic', 'item': '(3)', 'independent_answer': 'DE=120/17'}],
     'design': {'difference_from_source': '已知腰和中线求底边，逆向使用勾股定理',
                'difference_from_siblings': '所求量由中线改为底边'}},
]
M01['design'] = {'knowledge_points': ['等腰三角形三线合一', '勾股定理', '面积法求高'],
                 'method': '全等证明→勾股定理→等积法', 'question_type': '几何综合（证明＋计算）',
                 'difficulty': 'same', 'difficulty_evidence': '三小问，证明一步全等，计算两步，与原题相同'}

# ---------------------------------------------------------------- M02 初中物理
M02 = {
    'code': 'M02', 'number': '21', 'title': '九年级物理 欧姆定律计算', 'figure': 'circuit',
    'stem': ['21．如图所示电路，电源电压保持不变，定值电阻$R_1=10\\,\\Omega$。闭合开关$S$，电流表示数为$0.3\\,\\mathrm{A}$，电压表示数为$3\\,\\mathrm{V}$。'],
    'subs': [('(1)', '（1）求电源电压$U$；', []),
             ('(2)', '（2）求电阻$R_2$的阻值；', []),
             ('(3)', '（3）若将$R_2$换成阻值为$20\\,\\Omega$的电阻$R_3$，求此时电流表的示数。', ['(1)'])],
    'answer': ['【答案】（1）$6\\,\\mathrm{V}$；（2）$10\\,\\Omega$；（3）$0.2\\,\\mathrm{A}$。',
               '【解析】$U=IR_1+U_2=3\\,\\mathrm{V}+3\\,\\mathrm{V}=6\\,\\mathrm{V}$。'],
}


def m02_variant(r1, current, u2, r3, extra_stem=None, diff=('', ''), sub3=None):
    u = current * r1 + u2
    r2 = u2 / current
    i3 = u / (r1 + r3)
    fmt = lambda v: f'{v:g}'
    stem = extra_stem or (f'如图所示电路，电源电压不变，$R_1={fmt(r1)}\\,\\Omega$。闭合开关$S$后，电流表示数为'
                          f'${fmt(current)}\\,\\mathrm{{A}}$，电压表示数为${fmt(u2)}\\,\\mathrm{{V}}$。')
    return {'stem': [stem],
            'subs': ['（1）求电源电压$U$；', '（2）求电阻$R_2$的阻值；',
                     sub3 or f'（3）若用阻值为${fmt(r3)}\\,\\Omega$的电阻$R_3$替换$R_2$，求电流表的示数。'],
            'answers': {'(1)': f'U={fmt(u)} V', '(2)': f'R2={fmt(r2)} Ω', '(3)': f'I={fmt(i3)} A'},
            'solution': f'U=IR1+U2={fmt(current)}×{fmt(r1)}+{fmt(u2)}={fmt(u)} V；R2=U2/I={fmt(r2)} Ω；I′=U/(R1+R3)={fmt(i3)} A。',
            'checks': [{'kind': 'arith', 'item': '(1)', 'expr': f'{current}*{r1}+{u2}', 'expect': fmt(u), 'tolerance': 1e-9},
                       {'kind': 'arith', 'item': '(2)', 'expr': f'{u2}/{current}', 'expect': fmt(r2), 'tolerance': 1e-9},
                       {'kind': 'arith', 'item': '(3)', 'expr': f'{fmt(u)}/({r1}+{r3})', 'expect': fmt(i3), 'tolerance': 1e-9},
                       {'kind': 'units', 'item': '(1)', 'expr': 'I*R1+U2', 'units': {'I': 'A', 'R1': 'Ohm', 'U2': 'V'}, 'expect': 'V'},
                       {'kind': 'units', 'item': '(3)', 'expr': 'U/(R1+R3)', 'units': {'U': 'V', 'R1': 'Ohm', 'R3': 'Ohm'}, 'expect': 'A'},
                       {'kind': 'semantic', 'item': '(1)', 'independent_answer': f'U={fmt(u)} V'},
                       {'kind': 'semantic', 'item': '(2)', 'independent_answer': f'R2={fmt(r2)} Ω'},
                       {'kind': 'semantic', 'item': '(3)', 'independent_answer': f'I={fmt(i3)} A'}],
            'design': {'difference_from_source': diff[0], 'difference_from_siblings': diff[1]}}


M02['variants'] = [
    m02_variant(20, 0.2, 2, 40, diff=('电阻与电流数据组合改变，替换电阻更大', '电流较小、替换后电流减半')),
    m02_variant(5, 0.4, 4, 25, extra_stem='在图示电路中，电源电压保持不变。已知$R_1=5\\,\\Omega$，闭合开关$S$，电压表测得$R_2$两端电压为$4\\,\\mathrm{V}$，电流表读数为$0.4\\,\\mathrm{A}$。',
                diff=('条件呈现改为“电压表测得R2两端电压”的叙述方式', 'R1小于R2，U2占电源电压大部分')),
    m02_variant(12, 0.25, 6, 6,
                extra_stem='小明用如图所示的电路做实验，电源电压恒定，定值电阻$R_1$的阻值为$12\\,\\Omega$。他闭合开关$S$后记下：电流表读数$0.25\\,\\mathrm{A}$，电压表读数$6\\,\\mathrm{V}$。',
                sub3='（3）小明随后断开开关，把一个$6\\,\\Omega$的电阻$R_3$接在原来$R_2$的位置，再闭合开关，电流表读数变为多少？',
                diff=('实验叙事情境；第（3）问换接更小电阻，电流增大', '换接后电流变大，与其他两道相反')),
]
M02['design'] = {'knowledge_points': ['串联电路电压规律', '欧姆定律'], 'method': '串联分压→欧姆定律→替换后重算电流',
                 'question_type': '电学计算（三小问）', 'difficulty': 'same',
                 'difficulty_evidence': '三步计算，第（3）问依赖第（1）问，与原题一致'}

# ---------------------------------------------------------------- M03 初中化学
M03 = {
    'code': 'M03', 'number': '16', 'title': '九年级化学 根据化学方程式的计算', 'figure': None,
    'stem': ['16．实验室用氯酸钾（@\\mathrm{KClO_3}@）和二氧化锰（@\\mathrm{MnO_2}@）的混合物加热制取氧气。'],
    'subs': [('(1)', '（1）写出该反应的化学方程式；', []),
             ('(2)', '（2）若完全反应后生成氧气$9.6\\,\\mathrm{g}$，求参加反应的氯酸钾的质量；', ['(1)']),
             ('(3)', '（3）若原混合物共$30.0\\,\\mathrm{g}$，求反应后剩余固体中二氧化锰的质量分数（结果精确到0.1%）。', ['(2)'])],
    'answer': ['【答案】（1）@2\\mathrm{KClO_3}\\xrightarrow[\\Delta]{\\mathrm{MnO_2}}2\\mathrm{KCl}+3\\mathrm{O_2}\\uparrow@；（2）$24.5\\,\\mathrm{g}$；（3）27.0%。',
               '【解析】（3）@\\mathrm{MnO_2}@的质量为$30.0-24.5=5.5\\,\\mathrm{g}$，剩余固体为$30.0-9.6=20.4\\,\\mathrm{g}$。'],
}
EQUATION = '2KClO3 -> 2KCl + 3O2'


def m03_variant(o2, mixture, stem=None, diff=('', ''), sub3=None):
    kclo3 = o2 / 96 * 245
    mno2 = mixture - kclo3
    remain = mixture - o2
    percent = round(mno2 / remain * 100, 1)
    fmt = lambda v: f'{v:g}'
    return {'stem': [stem or f'加热氯酸钾（@\\mathrm{{KClO_3}}@）与二氧化锰（@\\mathrm{{MnO_2}}@）的混合物制取氧气，完全反应后共收集到氧气${fmt(o2)}\\,\\mathrm{{g}}$。'],
            'subs': ['（1）写出该反应的化学方程式；', '（2）求参加反应的氯酸钾的质量；',
                     sub3 or f'（3）若原混合物的质量为${mixture:.1f}\\,\\mathrm{{g}}$，求反应后剩余固体中二氧化锰的质量分数（结果精确到0.1%）。'],
            'answers': {'(1)': '2KClO3=(MnO2,△)2KCl+3O2↑', '(2)': f'{fmt(kclo3)} g', '(3)': f'{percent}%'},
            'solution': f'2KClO3~3O2，245:96；m(KClO3)={fmt(o2)}×245/96={fmt(kclo3)} g；m(MnO2)={fmt(mno2)} g；剩余固体{fmt(remain)} g；{percent}%。',
            'checks': [{'kind': 'balance', 'item': '(1)', 'equation': EQUATION},
                       {'kind': 'arith', 'item': '(2)', 'expr': '2*(39+35.5+48)', 'expect': '245'},
                       {'kind': 'arith', 'item': '(2)', 'expr': f'{o2}*245/96', 'expect': fmt(kclo3), 'tolerance': 1e-9},
                       {'kind': 'arith', 'item': '(3)', 'expr': f'({mixture}-{fmt(kclo3)})/({mixture}-{o2})*100',
                        'expect': str(percent), 'tolerance': 0.05},
                       {'kind': 'semantic', 'item': '(1)', 'independent_answer': '2KClO3=(MnO2,△)2KCl+3O2↑'},
                       {'kind': 'semantic', 'item': '(2)', 'independent_answer': f'{fmt(kclo3)} g'},
                       {'kind': 'semantic', 'item': '(3)', 'independent_answer': f'{percent}%'}],
            'design': {'difference_from_source': diff[0], 'difference_from_siblings': diff[1]}}


M03['variants'] = [
    m03_variant(4.8, 16.0, diff=('氧气质量与混合物质量组合改变', '催化剂占比较高')),
    m03_variant(4.8, 20.0, stem='加热一定质量的氯酸钾（@\\mathrm{KClO_3}@）和二氧化锰（@\\mathrm{MnO_2}@）的混合物，完全反应后称得固体质量比反应前减少了$4.8\\,\\mathrm{g}$。',
                diff=('氧气质量改为由“固体质量减少”经质量守恒得到', '需先用质量守恒转换条件')),
    m03_variant(14.4, 40.0,
                stem='某同学称取氯酸钾（@\\mathrm{KClO_3}@）和二氧化锰（@\\mathrm{MnO_2}@）的混合物$40.0\\,\\mathrm{g}$，加热至不再产生气体，冷却后称得剩余固体$25.6\\,\\mathrm{g}$。',
                sub3='（3）求剩余固体中二氧化锰的质量分数（结果精确到0.1%）。',
                diff=('给出反应前后固体质量，需先由质量守恒求氧气质量', '已知量为混合物和剩余固体质量')),
]
M03['design'] = {'knowledge_points': ['化学方程式书写', '根据化学方程式计算', '质量分数'],
                 'method': '写方程式→比例计算→质量守恒求剩余固体', 'question_type': '化学计算（三小问）',
                 'difficulty': 'same', 'difficulty_evidence': '与原题相同的三步链式计算'}

# ---------------------------------------------------------------- M04 初中英语
M04 = {
    'code': 'M04', 'number': '31-33', 'title': '八年级英语 阅读理解', 'figure': None,
    'material': ['A', "Li Ming's class planned a clean-up day at the city park. On Saturday morning, twenty students met at the park gate at eight o'clock. Mr. Wang, their teacher, gave everyone a pair of gloves and a bag. The students picked up bottles, paper and plastic bags along the lake. At noon they had a picnic under the big trees. In the afternoon, some park workers showed them how to sort the rubbish into four kinds. Li Ming said, \"I never knew that old batteries need a special box.\" Before they left, the students put up a sign: \"Keep our park clean!\""],
    'stem': [],
    'subs': [('(1)', '31. When did the students meet at the park gate?', [],
              'A. At seven.    B. At eight.    C. At noon.    D. In the afternoon.'),
             ('(2)', '32. What did Li Ming learn from the park workers?', [],
              'A. How to plant trees.    B. How to cook a picnic.    C. How to sort rubbish.    D. How to make a sign.'),
             ('(3)', '33. What is the best title for the passage?', [],
              'A. A Busy Teacher    B. A Day to Clean the Park    C. Old Batteries    D. Picnic by the Lake')],
    'answer': ['【答案】31. B  32. C  33. B'],
}


def english_variant(passage, items, diff):
    """items: [(question, {letter: option}, answer, evidence or None)]"""
    numbers = ['(1)', '(2)', '(3)']
    subs, answers, checks = [], {}, []
    for number, (question, options, answer, evidence) in zip(numbers, items):
        subs.append((question, '    '.join(f'{k}. {v}' for k, v in options.items())))
        answers[number] = answer
        checks.append({'kind': 'choice', 'item': number, 'options': options, 'answer': answer})
        if evidence:
            checks.append({'kind': 'evidence', 'item': number, 'quote': evidence})
        checks.append({'kind': 'semantic', 'item': number, 'independent_answer': answer})
    return {'material': passage, 'subs': subs, 'answers': answers,
            'solution': '；'.join(f'{n}：{a}' for n, a in answers.items()) + '（依据见证据句与题意推断）',
            'checks': checks, 'design': {'difference_from_source': diff[0], 'difference_from_siblings': diff[1]}}


M04['variants'] = [
    english_variant("Last Sunday, Kangkang and his friends helped at the school library. They arrived at nine o'clock. Ms. Chen, the librarian, asked them to put returned books back on the shelves. Some books were very old, so the students fixed the broken covers with tape. After lunch, they made a list of new books for the reading corner. Kangkang said, \"I never knew that every book has its own number.\" Before going home, they wrote a note on the door: \"Please return books on time!\"",
                    [('1. When did they arrive at the library?', {'A': 'At eight.', 'B': 'At nine.', 'C': 'After lunch.', 'D': 'In the evening.'}, 'B', "They arrived at nine o'clock."),
                     ('2. What did Kangkang learn at the library?', {'A': 'Every book has its own number.', 'B': 'How to cook lunch.', 'C': 'How to draw a map.', 'D': 'How to buy new books.'}, 'A', 'every book has its own number'),
                     ('3. What is the best title for the passage?', {'A': 'A New Librarian', 'B': 'Helping at the School Library', 'C': 'Broken Covers', 'D': 'Lunch at School'}, 'B', None)],
                    ('情境由公园清洁改为图书馆志愿服务', '细节题考时间，学习内容为图书编号')),
    english_variant("On Saturday, Maria and her classmates visited a community garden near their school. They got there at half past seven. An old farmer, Mr. Zhou, gave each student a small spade. The students watered the vegetables and pulled out weeds between the rows. At ten they had a rest and drank fresh juice. Later, Mr. Zhou showed them how to plant tomato seeds in small pots. Maria said, \"I never knew that seeds need warm soil to grow.\" Before they left, they put a sign on the gate: \"Please don't step on the plants!\"",
                    [('1. When did they get to the garden?', {'A': 'At seven.', 'B': 'At half past seven.', 'C': 'At ten.', 'D': 'At noon.'}, 'B', 'They got there at half past seven.'),
                     ('2. What did Mr. Zhou show the students?', {'A': 'How to make juice.', 'B': 'How to plant tomato seeds.', 'C': 'How to build a gate.', 'D': 'How to draw plants.'}, 'B', 'how to plant tomato seeds in small pots'),
                     ('3. What is the best title for the passage?', {'A': 'Fresh Juice', 'B': 'A Morning at the Community Garden', 'C': 'An Old Spade', 'D': 'Warm Soil'}, 'B', None)],
                    ('情境改为社区菜园劳动，时间干扰项更接近', '干扰项含相近时间“seven/half past seven”')),
    english_variant("Last month, Jane's class spent a day at the science museum as young guides. They met the museum keeper at half past eight. She gave each student a badge and a map. In the morning, the students learned about the old clocks on the second floor. After lunch, they took turns to explain the clocks to younger visitors. Jane said, \"I never knew that the first clocks used water.\" At the end of the day, the keeper thanked them with a small gift.",
                    [('1. What did the museum keeper give each student?', {'A': 'A badge and a map.', 'B': 'A small clock.', 'C': 'A ticket.', 'D': 'Some water.'}, 'A', 'She gave each student a badge and a map.'),
                     ('2. What did Jane learn at the museum?', {'A': 'Clocks are cheap.', 'B': 'The first clocks used water.', 'C': 'Guides need maps.', 'D': 'Museums open late.'}, 'B', 'the first clocks used water'),
                     ('3. What is the best title for the passage?', {'A': 'Young Guides at the Science Museum', 'B': 'Old Maps', 'C': 'A Small Gift', 'D': 'The Second Floor'}, 'A', None)],
                    ('细节题由“时间”改为“物品”，情境为科技馆讲解', '第1题考物品而非时间')),
]
M04['design'] = {'knowledge_points': ['细节理解', '主旨大意'], 'method': '定位关键词→比对选项→归纳标题',
                 'question_type': '共享语篇阅读理解（三题）', 'difficulty': 'same',
                 'difficulty_evidence': '语篇约90词、一般过去时、初二词汇，设问层级同原题'}

# ---------------------------------------------------------------- M05 高中数学
M05 = {
    'code': 'M05', 'number': '19', 'title': '高一数学 二次函数综合', 'figure': None,
    'stem': ['19．已知函数$f(x)=x^2-2ax+3$，$a\\in\\mathbf{R}$。'],
    'subs': [('(1)', '（1）若$f(1)=0$，求$a$的值；', []),
             ('(2)', '（2）在（1）的条件下，求$f(x)$在区间$[0,3]$上的最大值和最小值；', ['(1)']),
             ('(3)', '（3）若$f(x)\\geq 0$对任意$x\\in[1,2]$恒成立，求实数$a$的取值范围。', [])],
    'answer': ['【答案】（1）$a=2$；（2）最大值$3$，最小值$-1$；（3）$a\\leq\\sqrt{3}$。',
               '【解析】（3）分离参数得$2a\\leq x+\\frac{3}{x}$，在$x=\\sqrt{3}$处取最小值$2\\sqrt{3}$。'],
}


def m05_variant(fx, cond, interval, rng_interval, answers, checks, diff, solution, stem=None, subs=None):
    return {'stem': [stem or f'已知函数$f(x)={fx}$，$a\\in\\mathbf{{R}}$。'],
            'subs': subs or [f'（1）若${cond}$，求$a$的值；', f'（2）在（1）的条件下，求$f(x)$在区间${interval}$上的最大值和最小值；',
                             f'（3）若$f(x)\\geq 0$对任意$x\\in{rng_interval}$恒成立，求实数$a$的取值范围。'],
            'answers': answers, 'solution': solution, 'checks': checks,
            'design': {'difference_from_source': diff[0], 'difference_from_siblings': diff[1]}}


M05['variants'] = [
    m05_variant('x^2-2ax+5', 'f(1)=0', '[0,4]', '[1,3]',
                {'(1)': 'a=3', '(2)': '最大值5，最小值-4', '(3)': 'a≤√5'},
                [{'kind': 'substitute', 'item': '(1)', 'equation': 'x**2-2*a*x+5 = 0', 'vars': {'x': '1', 'a': '3'}},
                 {'kind': 'arith', 'item': '(2)', 'expr': '3**2-6*3+5', 'expect': '-4'},
                 {'kind': 'arith', 'item': '(2)', 'expr': '0**2-6*0+5', 'expect': '5'},
                 {'kind': 'arith', 'item': '(3)', 'expr': '(sqrt(5)+5/sqrt(5))/2', 'expect': str(5 ** 0.5), 'tolerance': 1e-9},
                 {'kind': 'semantic', 'item': '(1)', 'independent_answer': 'a=3'},
                 {'kind': 'semantic', 'item': '(2)', 'independent_answer': '最大值5，最小值-4'},
                 {'kind': 'semantic', 'item': '(3)', 'independent_answer': 'a≤√5'}],
                ('常数项与区间改变，最值端点为x=0', '对称轴x=3在区间内部，√5在[1,3]内'),
                'a=3，f=x²−6x+5，顶点x=3∈[0,4]，最小f(3)=−4，最大f(0)=5；2a≤x+5/x，最小值2√5于x=√5∈[1,3]，a≤√5。'),
    m05_variant('2x^2-4ax+6', 'f(1)=0', '[0,4]', '[2,3]',
                {'(1)': 'a=2', '(2)': '最大值6，最小值-2', '(3)': 'a≤7/4'},
                [{'kind': 'substitute', 'item': '(1)', 'equation': '2*x**2-4*a*x+6 = 0', 'vars': {'x': '1', 'a': '2'}},
                 {'kind': 'arith', 'item': '(2)', 'expr': '2*2**2-8*2+6', 'expect': '-2'},
                 {'kind': 'arith', 'item': '(2)', 'expr': '2*4**2-8*4+6', 'expect': '6'},
                 {'kind': 'arith', 'item': '(3)', 'expr': '(2+3/2)/2', 'expect': '7/4'},
                 {'kind': 'semantic', 'item': '(1)', 'independent_answer': 'a=2'},
                 {'kind': 'semantic', 'item': '(2)', 'independent_answer': '最大值6，最小值-2'},
                 {'kind': 'semantic', 'item': '(3)', 'independent_answer': 'a≤7/4'}],
                ('二次项系数改为2；第（3）问极值点√3不在[2,3]内，需讨论单调性', '边界情形：最小值在区间端点取得'),
                'a=2，g=2x²−8x+6，顶点x=2，最小−2，g(0)=g(4)=6；a≤(x²+3)/(2x)，h(x)=(x+3/x)/2在[2,3]递增，最小h(2)=7/4。',
                stem='设函数$g(x)=2x^2-4ax+6$，其中$a$为实数。',
                subs=['（1）已知$x=1$是方程$g(x)=0$的一个根，求$a$；', '（2）当$a$取（1）中的值时，求$g(x)$在$[0,4]$上的最大值与最小值；',
                      '（3）若对任意$x\\in[2,3]$，都有$g(x)\\geq 0$，求$a$的取值范围。']),
    m05_variant('x^2-2ax+8', 'f(2)=0', '[1,5]', '[1,4]',
                {'(1)': 'a=3', '(2)': '最大值3，最小值-1', '(3)': 'a≤2√2'},
                [{'kind': 'substitute', 'item': '(1)', 'equation': 'x**2-2*a*x+8 = 0', 'vars': {'x': '2', 'a': '3'}},
                 {'kind': 'roots', 'item': '(1)', 'expr': '4-4*a+8', 'var': 'a', 'claimed': ['3'], 'interval': ['-50', '50']},
                 {'kind': 'arith', 'item': '(2)', 'expr': '3**2-6*3+8', 'expect': '-1'},
                 {'kind': 'arith', 'item': '(2)', 'expr': '5**2-6*5+8', 'expect': '3'},
                 {'kind': 'arith', 'item': '(3)', 'expr': '(sqrt(8)+8/sqrt(8))/2', 'expect': str(8 ** 0.5), 'tolerance': 1e-9},
                 {'kind': 'semantic', 'item': '(1)', 'independent_answer': 'a=3'},
                 {'kind': 'semantic', 'item': '(2)', 'independent_answer': '最大值3，最小值-1'},
                 {'kind': 'semantic', 'item': '(3)', 'independent_answer': 'a≤2√2'}],
                ('已知条件改为f(2)=0；区间两端函数值相等', '最大值在两端同时取得'),
                'f(2)=12−4a=0，a=3；f=x²−6x+8，顶点3，最小−1，f(1)=f(5)=3；2a≤x+8/x，最小4√2于x=2√2∈[1,4]，a≤2√2。',
                stem='二次函数$f(x)=x^2-2ax+8$的图像经过点$(2,0)$。',
                subs=['（1）求$a$的值；', '（2）求$f(x)$在闭区间$[1,5]$上的最大值与最小值；',
                      '（3）当$x\\in[1,4]$时，不等式$f(x)\\geq 0$恒成立，求实数$a$的取值范围。']),
]
M05['design'] = {'knowledge_points': ['二次函数解析式', '闭区间最值', '恒成立与分离参数'],
                 'method': '代入求参→配方讨论对称轴→分离参数结合基本不等式或单调性',
                 'question_type': '函数综合（三小问）', 'difficulty': 'same',
                 'difficulty_evidence': '第（2）问依赖第（1）问，第（3）问独立，与原题同梯度'}

# ---------------------------------------------------------------- M06 高中物理（含遮挡推断补写样本）
M06 = {
    'code': 'M06', 'number': '15', 'title': '高一物理 多过程直线运动', 'figure': None,
    'occluded': '6',
    'stem': ['15．一辆小车从静止开始做匀加速直线运动，加速度$a_1=2\\,\\mathrm{m/s^2}$，经过$4\\,\\mathrm{s}$后改做匀速直线运动，匀速运动〔6〕$\\,\\mathrm{s}$后开始做匀减速直线运动，再经过$2\\,\\mathrm{s}$恰好停止。'],
    'subs': [('(1)', '（1）求小车运动过程中的最大速度；', []),
             ('(2)', '（2）求匀减速阶段加速度的大小；', ['(1)']),
             ('(3)', '（3）求小车运动的总位移。', ['(1)'])],
    'answer': ['【答案】（1）$8\\,\\mathrm{m/s}$；（2）$4\\,\\mathrm{m/s^2}$；（3）$72\\,\\mathrm{m}$。'],
}


def m06_variant(stem, answers, checks, solution, diff):
    return {'stem': [stem], 'subs': ['（1）求小车运动过程中的最大速度；', '（2）求匀减速阶段加速度的大小；', '（3）求小车运动的总位移。'],
            'answers': answers, 'solution': solution, 'checks': checks,
            'design': {'difference_from_source': diff[0], 'difference_from_siblings': diff[1]}}


M06['variants'] = [
    m06_variant('一辆小车从静止开始以$a_1=3\\,\\mathrm{m/s^2}$的加速度做匀加速直线运动，$4\\,\\mathrm{s}$后做匀速直线运动，匀速运动$5\\,\\mathrm{s}$后开始匀减速，再经$3\\,\\mathrm{s}$停止。',
                {'(1)': '12 m/s', '(2)': '4 m/s²', '(3)': '102 m'},
                [{'kind': 'arith', 'item': '(1)', 'expr': '3*4', 'expect': '12'},
                 {'kind': 'arith', 'item': '(2)', 'expr': '12/3', 'expect': '4'},
                 {'kind': 'arith', 'item': '(3)', 'expr': '12/2*4+12*5+12/2*3', 'expect': '102'},
                 {'kind': 'units', 'item': '(1)', 'expr': 'a*t', 'units': {'a': 'm/s^2', 't': 's'}, 'expect': 'm/s'},
                 {'kind': 'units', 'item': '(3)', 'expr': 'v*t', 'units': {'v': 'm/s', 't': 's'}, 'expect': 'm'},
                 {'kind': 'semantic', 'item': '(1)', 'independent_answer': '12 m/s'},
                 {'kind': 'semantic', 'item': '(2)', 'independent_answer': '4 m/s²'},
                 {'kind': 'semantic', 'item': '(3)', 'independent_answer': '102 m'}],
                'v=a1t1=12 m/s；a3=v/t3=4 m/s²；x=6×4+12×5+6×3=102 m。',
                ('加速度与各阶段时间改变', '减速时间更长')),
    m06_variant('一辆小车从静止开始做匀加速直线运动，在前$4\\,\\mathrm{s}$内通过的位移为$20\\,\\mathrm{m}$，随后匀速运动$6\\,\\mathrm{s}$，最后匀减速运动$2.5\\,\\mathrm{s}$停止。',
                {'(1)': '10 m/s', '(2)': '4 m/s²', '(3)': '92.5 m'},
                [{'kind': 'arith', 'item': '(1)', 'expr': '2*20/4', 'expect': '10'},
                 {'kind': 'arith', 'item': '(2)', 'expr': '10/2.5', 'expect': '4'},
                 {'kind': 'arith', 'item': '(3)', 'expr': '20+10*6+10/2*2.5', 'expect': '92.5'},
                 {'kind': 'units', 'item': '(1)', 'expr': 'x/t', 'units': {'x': 'm', 't': 's'}, 'expect': 'm/s'},
                 {'kind': 'units', 'item': '(2)', 'expr': 'v/t', 'units': {'v': 'm/s', 't': 's'}, 'expect': 'm/s^2'},
                 {'kind': 'semantic', 'item': '(1)', 'independent_answer': '10 m/s'},
                 {'kind': 'semantic', 'item': '(2)', 'independent_answer': '4 m/s²'},
                 {'kind': 'semantic', 'item': '(3)', 'independent_answer': '92.5 m'}],
                'x1=v t1/2，v=2×20/4=10 m/s；a3=10/2.5=4 m/s²；x=20+60+12.5=92.5 m。',
                ('加速阶段条件由加速度改为位移，需用平均速度求最大速度', '条件呈现转换')),
    m06_variant('一辆小车从静止开始以$a_1=1.5\\,\\mathrm{m/s^2}$的加速度匀加速运动$6\\,\\mathrm{s}$，接着匀速运动$4\\,\\mathrm{s}$，最后匀减速滑行$13.5\\,\\mathrm{m}$停止。',
                {'(1)': '9 m/s', '(2)': '3 m/s²', '(3)': '76.5 m'},
                [{'kind': 'arith', 'item': '(1)', 'expr': '1.5*6', 'expect': '9'},
                 {'kind': 'arith', 'item': '(2)', 'expr': '9**2/(2*13.5)', 'expect': '3'},
                 {'kind': 'arith', 'item': '(3)', 'expr': '9/2*6+9*4+13.5', 'expect': '76.5'},
                 {'kind': 'units', 'item': '(2)', 'expr': 'v**2/x', 'units': {'v': 'm/s', 'x': 'm'}, 'expect': 'm/s^2'},
                 {'kind': 'semantic', 'item': '(1)', 'independent_answer': '9 m/s'},
                 {'kind': 'semantic', 'item': '(2)', 'independent_answer': '3 m/s²'},
                 {'kind': 'semantic', 'item': '(3)', 'independent_answer': '76.5 m'}],
                'v=1.5×6=9 m/s；v²=2a3x3，a3=81/27=3 m/s²；x=27+36+13.5=76.5 m。',
                ('减速阶段给位移而非时间，需用速度-位移关系', '第（2）问换用v²=2ax')),
]
M06['design'] = {'knowledge_points': ['匀变速直线运动规律', '多过程运动'], 'method': '分段列式，速度在阶段间传递',
                 'question_type': '多阶段运动计算（三小问）', 'difficulty': 'same',
                 'difficulty_evidence': '三段运动、三小问，第（2）（3）问依赖第（1）问'}

# ---------------------------------------------------------------- M07 高中化学
M07 = {
    'code': 'M07', 'number': '17', 'title': '高一化学 原电池原理', 'figure': None,
    'stem': ['17．用铜片、石墨棒和@\\mathrm{FeCl_3}@溶液可以组成原电池。'],
    'subs': [('(1)', '（1）写出铜与@\\mathrm{FeCl_3}@溶液反应的离子方程式；', []),
             ('(2)', '（2）该原电池的负极材料是什么？写出正极的电极反应式；', ['(1)']),
             ('(3)', '（3）若电路中通过$0.2\\,\\mathrm{mol}$电子，求负极质量减少了多少克。', ['(2)'])],
    'answer': ['【答案】（1）@\\mathrm{Cu}+2\\mathrm{Fe^{3+}}=\\mathrm{Cu^{2+}}+2\\mathrm{Fe^{2+}}@；（2）铜，@\\mathrm{Fe^{3+}}+\\mathrm{e^-}=\\mathrm{Fe^{2+}}@；（3）$6.4\\,\\mathrm{g}$。'],
}


def m07_variant(stem, subs, answers, equations, arith, solution, diff):
    checks = [{'kind': 'balance', 'item': item, 'equation': eq} for item, eq in equations]
    checks += arith
    checks += [{'kind': 'semantic', 'item': k, 'independent_answer': v} for k, v in answers.items()]
    return {'stem': [stem], 'subs': subs, 'answers': answers, 'solution': solution, 'checks': checks,
            'design': {'difference_from_source': diff[0], 'difference_from_siblings': diff[1]}}


M07['variants'] = [
    m07_variant('用铁片、石墨棒和@\\mathrm{FeCl_3}@溶液组成原电池。',
                ['（1）写出铁与@\\mathrm{FeCl_3}@溶液反应的离子方程式；', '（2）该原电池的负极材料是什么？写出正极的电极反应式；',
                 '（3）若电路中通过$0.4\\,\\mathrm{mol}$电子，求负极质量减少了多少克。'],
                {'(1)': 'Fe+2Fe3+=3Fe2+', '(2)': '铁；Fe3++e-=Fe2+', '(3)': '11.2 g'},
                [('(1)', 'Fe + 2Fe^3+ = 3Fe^2+'), ('(2)', 'Fe^3+ + e- = Fe^2+')],
                [{'kind': 'arith', 'item': '(3)', 'expr': '0.4/2*56', 'expect': '11.2', 'tolerance': 1e-9}],
                '负极Fe−2e⁻=Fe²⁺，0.4 mol e⁻对应0.2 mol Fe，质量11.2 g。',
                ('负极材料改为铁，产物只有Fe²⁺（归中反应）', '归中反应，产物单一')),
    m07_variant('用锌片、铜片和@\\mathrm{CuSO_4}@溶液组成原电池。',
                ['（1）写出锌与@\\mathrm{CuSO_4}@溶液反应的离子方程式；', '（2）该原电池的负极材料是什么？写出正极的电极反应式；',
                 '（3）若电路中通过$0.2\\,\\mathrm{mol}$电子，求负极质量减少了多少克。'],
                {'(1)': 'Zn+Cu2+=Zn2++Cu', '(2)': '锌；Cu2++2e-=Cu', '(3)': '6.5 g'},
                [('(1)', 'Zn + Cu^2+ = Zn^2+ + Cu'), ('(2)', 'Cu^2+ + 2e- = Cu')],
                [{'kind': 'arith', 'item': '(3)', 'expr': '0.2/2*65', 'expect': '6.5', 'tolerance': 1e-9}],
                '负极Zn−2e⁻=Zn²⁺，0.2 mol e⁻对应0.1 mol Zn，质量6.5 g。',
                ('电解质改为CuSO4，正极析出金属', '正极反应转移2个电子')),
    m07_variant('用铜片、银片和@\\mathrm{AgNO_3}@溶液组成原电池。',
                ['（1）写出铜与@\\mathrm{AgNO_3}@溶液反应的离子方程式；', '（2）该原电池的负极材料是什么？写出正极的电极反应式；',
                 '（3）若电路中通过$0.3\\,\\mathrm{mol}$电子，求负极质量减少了多少克。'],
                {'(1)': 'Cu+2Ag+=Cu2++2Ag', '(2)': '铜；Ag++e-=Ag', '(3)': '9.6 g'},
                [('(1)', 'Cu + 2Ag^+ = Cu^2+ + 2Ag'), ('(2)', 'Ag^+ + e- = Ag')],
                [{'kind': 'arith', 'item': '(3)', 'expr': '0.3/2*64', 'expect': '9.6', 'tolerance': 1e-9}],
                '负极Cu−2e⁻=Cu²⁺，0.3 mol e⁻对应0.15 mol Cu，质量9.6 g。',
                ('电解质改为AgNO3，正负极材料均为金属', '正极为银，析出银')),
]
M07['design'] = {'knowledge_points': ['离子方程式', '原电池正负极判断', '电子转移计算'],
                 'method': '写总反应→拆分电极反应→电子守恒计算', 'question_type': '电化学综合（三小问）',
                 'difficulty': 'same', 'difficulty_evidence': '三小问链式依赖，与原题相同'}

# ---------------------------------------------------------------- M08 高中英语
M08 = {
    'code': 'M08', 'number': '24-26', 'title': '高一英语 推断型阅读', 'figure': None,
    'material': ['B', "When Maya first joined the robotics club, she rarely spoke. She sat at the back, sketching gears in her notebook while others argued loudly about motors and code. Three weeks before the regional contest, the team's robot kept tipping over on the ramp. Everyone blamed the software. Maya quietly placed her notebook on the table. Her drawing showed the robot's battery mounted too high, shifting its weight backward on slopes. The team moved the battery lower that evening, and the robot climbed the ramp on its first try. At the contest, the captain insisted that Maya present the design. \"Good ideas,\" he told the judges, \"don't always come from the loudest voice.\""],
    'stem': [],
    'subs': [('(1)', '24. Why did the robot keep tipping over on the ramp?', [],
              'A. The code had a serious error.    B. The motors were too weak.    C. Its weight was placed too high at the back.    D. The ramp was badly built.'),
             ('(2)', '25. What can we infer about Maya from the passage?', [],
              'A. She preferred observing to arguing.    B. She disliked working in a team.    C. She was the best programmer.    D. She wanted to become captain.'),
             ('(3)', "26. What is the captain's main point in the last sentence?", [],
              'A. Loud people are rude.    B. Quiet members may offer valuable ideas.    C. Judges should listen carefully.    D. Presentations need strong voices.')],
    'answer': ['【答案】24. C  25. A  26. B'],
}
M08['variants'] = [
    english_variant("Leo had played the violin in the school orchestra for a year, yet few people noticed him. During breaks he would wander off alone, listening closely to the hall's empty corners. A month before the spring concert, the music teacher complained that the brass section always sounded muddy. The players practised harder, but nothing changed. Leo finally suggested a simple test: he moved the brass chairs two metres away from the back wall. Their sound immediately became clearer, because the wall had been bouncing it back too early. On concert night, the teacher asked Leo to explain the new seating to the audience. \"Sometimes,\" she said, \"the best listener in the room solves the problem.\"",
                    [('1. Why did the brass section sound muddy?', {'A': 'The players did not practise enough.', 'B': 'The back wall reflected their sound too early.', 'C': 'Their instruments were old.', 'D': 'The hall was too small.'}, 'B', 'the wall had been bouncing it back too early'),
                     ('2. What can we infer about Leo?', {'A': 'He paid careful attention to how sound behaved.', 'B': 'He wanted to leave the orchestra.', 'C': 'He led the brass section.', 'D': 'He found practice boring.'}, 'A', "listening closely to the hall's empty corners"),
                     ('3. What does the teacher mean by her last words?', {'A': 'Careful listening can lead to solutions.', 'B': 'Only teachers can solve problems.', 'C': 'Audiences should stay quiet.', 'D': 'Musicians must speak more often.'}, 'A', None)],
                    ('情境改为乐团声学问题，推断依据为倾听行为', '原因细节题涉及声音反射')),
    english_variant("Sara joined the school newspaper as a photographer and seldom offered opinions in meetings. While the writers rushed to finish stories, she kept a small table of every number the paper printed. Before the issue about the canteen survey went out, she noticed something odd: the article said 70 percent of students liked the new menu, but only 120 of the 300 forms said so. The editor checked the forms and found that the writer had counted the same pile twice. The story was corrected just in time. At the end of the term, the editor gave Sara a new role. \"Checking facts,\" he explained, \"is as important as telling stories.\"",
                    [('1. What was wrong with the canteen article?', {'A': 'It used an old photo.', 'B': 'Its percentage did not match the forms.', 'C': 'It was printed too late.', 'D': 'It criticised the cooks.'}, 'B', 'only 120 of the 300 forms said so'),
                     ('2. What can we infer about Sara?', {'A': 'She was careful with details.', 'B': 'She wanted to be a writer.', 'C': 'She disliked the new menu.', 'D': 'She often argued with the editor.'}, 'A', 'she kept a small table of every number the paper printed'),
                     ('3. What new role was Sara most probably given?', {'A': 'Photographer.', 'B': 'Fact checker.', 'C': 'Canteen manager.', 'D': 'Story writer.'}, 'B', None)],
                    ('情境改为校报数据核查；第3题由句意理解变为角色推断', '第3题推断新职务')),
    english_variant("Tom was the youngest member of the town's tree-planting club, and he mostly listened during planning meetings. Last autumn, half of the young trees the club planted along the river died within weeks. The older members thought the soil was too poor and wanted to buy expensive fertiliser. Tom, who walked along the river every morning, had noticed that the dead trees were all on the side where people let their dogs run. He suggested putting up simple wooden fences instead. The club tried his idea on twenty new trees, and every one of them survived the winter. At the spring meeting, the chairwoman asked Tom to lead the next planting day.",
                    [('1. Why did many young trees die?', {'A': 'The soil had no fertiliser.', 'B': 'Dogs damaged them on one side of the river.', 'C': 'The winter was too cold.', 'D': 'They were planted too late.'}, 'B', 'the dead trees were all on the side where people let their dogs run'),
                     ('2. What can we infer about Tom?', {'A': 'He noticed things others missed.', 'B': 'He knew a lot about fertiliser.', 'C': 'He owned several dogs.', 'D': 'He disliked meetings.'}, 'A', 'had noticed that the dead trees were all on the side'),
                     ('3. Why did the chairwoman ask Tom to lead the next planting day?', {'A': 'He was the oldest member.', 'B': 'His idea had proved effective.', 'C': 'He had bought the fences.', 'D': 'He asked for the job.'}, 'B', 'every one of them survived the winter')],
                    ('情境改为植树社团，第3题为因果推断', '第3题询问原因并有证据句')),
]
M08['design'] = {'knowledge_points': ['细节理解', '推理判断', '观点态度/意图理解'],
                 'method': '定位证据句→推断人物特点→理解结尾观点',
                 'question_type': '共享语篇推断型阅读（三题）', 'difficulty': 'same',
                 'difficulty_evidence': '语篇约110词，含因果与推断，设问层级同原题'}

ALL = [M01, M02, M03, M04, M05, M06, M07, M08]
