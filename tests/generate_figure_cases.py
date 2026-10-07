"""Controlled diagram scenes for renderer/visual QA, not real OCR acceptance."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

SCRIPTS=Path(__file__).resolve().parents[1]/'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0,str(SCRIPTS))
from figure_drawing import render


class Scene:
    def __init__(self, width=400, height=300):
        self.data={'width':width,'height':height,'elements':[],
                   'structure':{'objects':[],'labels':[],'arrows':[],'connections':[],'facts':{}}}

    def add(self, eid, kind, object_id=None, **properties):
        item={'id':eid,'kind':kind,**properties}
        if object_id:
            item['object_id']=object_id
            if not any(o['id']==object_id for o in self.data['structure']['objects']):
                self.data['structure']['objects'].append({'id':object_id,'kind':'observed_object'})
        self.data['elements'].append(item)
        if item.get('arrow','none')!='none':
            points=item['points']
            p,q=(points[1],points[0]) if item['arrow']=='start' else (points[-2],points[-1])
            self.data['structure']['arrows'].append({'element_id':eid,'direction':[q[0]-p[0],q[1]-p[1]],
                                                    **({'both':True} if item['arrow']=='both' else {})})
        if 'connection' in item:self.data['structure']['connections'].append(item['connection'])
        return item

    def line(self,eid,points,object_id=None,**properties):
        return self.add(eid,'line' if len(points)==2 else 'polyline',object_id,points=points,**properties)

    def label(self,eid,value,at,target,**properties):
        field={'text':value} if isinstance(value,str) else {'runs':value}
        self.add(eid,'label',target,label_id=eid,at=at,**field,**properties)
        self.data['structure']['labels'].append({'id':eid,'target':target,**deepcopy(field)})


def examples():
    cases={}
    s=Scene()
    s.line('AB',[[80,250],[300,250]],'triangle')
    s.line('AC',[[80,250],[80,50]],'triangle')
    s.line('BC',[[300,250],[80,50]],'triangle')
    s.line('right-angle',[[80,230],[100,230],[100,250]],'triangle')
    for name,at in [('A',[55,270]),('B',[305,270]),('C',[60,40])]:s.label('label-'+name,name,at,'triangle')
    s.data['structure']['geometry']=[{'kind':'perpendicular','elements':['AB','AC']}]
    cases['geometry']=s.data

    s=Scene()
    s.line('x-axis',[[60,250],[355,250]],'axes',arrow='end')
    s.line('y-axis',[[60,250],[60,35]],'axes',arrow='end')
    s.label('x-label','x',[365,255],'axes');s.label('y-label','y',[40,30],'axes')
    s.label('origin','O',[40,275],'axes')
    s.add('curve','curve','curve',points=[[80,235],[180,230],[240,190],[320,60]])
    s.data['structure']['facts']={'curve_trend':'rises with x','numeric_ticks':'none supplied'}
    s.data['structure']['curves']=[{'element_id':'curve','trend':'increasing','x_direction':1,'y_direction':-1}]
    cases['function']=s.data
    coords=deepcopy(s.data)
    coords['elements']=[e for e in coords['elements'] if e['id']!='curve']
    coords['elements'].append({'id':'P','kind':'circle','object_id':'point','center':[250,110],'radius':3,'fill':'black'})
    coords['elements'].append({'id':'p-label','kind':'label','object_id':'point','label_id':'p-label','at':[260,105],'text':'P'})
    coords['structure']['objects']=[{'id':'axes','kind':'coordinate_axes'},{'id':'point','kind':'point'}]
    coords['structure']['labels'].append({'id':'p-label','target':'point','text':'P'})
    coords['structure']['facts']={'point':'first quadrant','numeric_ticks':'none supplied'}
    coords['structure'].pop('curves')
    cases['coordinates']=coords

    s=Scene();s.add('body','rect','body',at=[90,125],width=100,height=60)
    s.line('surface',[[40,185],[355,185]])
    s.line('velocity',[[190,150],[300,150]],'velocity',arrow='end')
    s.label('velocity-label',[{'text':'v'},{'text':'0','script':'sub'}],[235,130],'velocity')
    cases['motion']=s.data
    force=deepcopy(s.data);force['structure']['facts']={'arrow':'horizontal right, application at right face'}
    force['elements'][-1]['runs']=[{'text':'F'},{'text':'1','script':'sub'}]
    force['structure']['labels'][0]['runs']=[{'text':'F'},{'text':'1','script':'sub'}]
    cases['force']=force

    s=Scene()
    s.add('resistor','rect','resistor',at=[160,70],width=80,height=20)
    s.line('battery-plus',[[180,215],[180,265]],'battery')
    s.line('battery-minus',[[195,225],[195,255]],'battery')
    s.line('left-wire',[[180,240],[60,240],[60,80],[160,80]],connection=['battery','resistor'])
    s.line('right-top',[[240,80],[340,80],[340,120]],connection=['resistor','switch'])
    s.line('switch',[[340,120],[320,150]],'switch')
    s.line('right-bottom',[[340,160],[340,240],[195,240]],connection=['switch','battery'])
    s.add('switch-contact','circle','switch',center=[340,160],radius=2,fill='black')
    s.label('r-label',[{'text':'R'},{'text':'1','script':'sub'}],[195,55],'resistor',anchor='middle')
    s.label('s-label','S',[350,150],'switch')
    s.label('positive','+',[160,205],'battery')
    s.data['structure']['facts']={'switch':'open','battery_positive':'left','component_count':3}
    cases['circuit']=s.data

    s=Scene();s.line('axis',[[30,210],[365,210]],'axis',dash=[8,4])
    s.line('lens',[[200,35],[200,270]],'lens',arrow='both')
    s.line('ray1',[[70,80],[200,80],[330,210]],'ray1',arrow='end')
    s.line('ray2',[[70,80],[200,210],[250,260]],'ray2',arrow='end')
    s.label('lens-center','O',[175,235],'lens')
    s.label('focus','F',[330,235],'axis')
    s.data['structure']['facts']={'lens':'converging','parallel_ray':'refracts through right focus'}
    cases['optics']=s.data

    s=Scene();s.line('beaker',[[110,70],[110,200],[230,200],[230,70]],'beaker')
    s.line('liquid',[[110,150],[230,150]],'liquid')
    s.line('support',[[100,210],[240,210]],'stand')
    s.line('leg1',[[110,210],[90,270]],'stand');s.line('leg2',[[230,210],[250,270]],'stand')
    s.add('flame','polygon','heat',points=[[164,263],[174,238],[184,263]])
    s.add('heater','rect','heat',at=[150,270],width=50,height=15)
    s.label('water',[{'text':'H'},{'text':'2','script':'sub'},{'text':'O'}],[260,145],'liquid')
    s.data['structure']['facts']={'heating':'below vessel','liquid_level':150,'connections':'none'}
    cases['apparatus']=s.data

    s=Scene();s.add('A','rect','A',at=[30,100],width=120,height=100)
    s.add('B','rect','B',at=[250,100],width=120,height=100)
    s.line('flow',[[150,150],[250,150]],'flow',arrow='end',connection=['A','B'])
    s.label('a-label','A',[90,157],'A',anchor='middle');s.label('b-label','B',[310,157],'B',anchor='middle')
    cases['flowchart']=s.data

    s=Scene();s.add('pulley','circle','pulley',center=[200,90],radius=35)
    s.add('axle','circle','pulley',center=[200,90],radius=3,fill='black')
    s.add('rope-arc','arc','rope',center=[200,90],rx=35,ry=35,start=180,end=360)
    s.line('left-rope',[[165,90],[165,205]],'rope');s.line('right-rope',[[235,90],[235,205]],'rope')
    s.add('mass1','rect','mass1',at=[145,205],width=40,height=45)
    s.add('mass2','rect','mass2',at=[215,205],width=40,height=45)
    s.label('m1',[{'text':'m'},{'text':'1','script':'sub'}],[100,235],'mass1')
    s.label('m2',[{'text':'m'},{'text':'2','script':'sub'}],[270,235],'mass2')
    cases['structure']=s.data

    s=Scene(600,300)
    for name,x in [('A',80),('B',380)]:
        s.add('body-'+name,'rect',name,at=[x,110],width=70,height=60)
        s.line('force-'+name,[[x+70,140],[x+170,140]],'force-'+name,arrow='end')
        s.label('label-'+name,name,[x+35,205],name,anchor='middle')
        s.label('F-'+name,[{'text':'F'},{'text':name,'script':'sub'}],[x+120,120],'force-'+name,anchor='middle')
    s.data['structure']['facts']={'combined':'A/B comparison, one shared task','subject_count':2}
    cases['combined']=s.data
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--font')
    args=parser.parse_args()
    output=Path(args.output)
    if output.exists() and any(output.iterdir()):raise FileExistsError('Use a new or empty output directory')
    output.mkdir(parents=True,exist_ok=True)
    cases=examples()
    for name,scene in cases.items():
        render(scene,output/(name+'.svg'),output/(name+'.png'),understanding=scene['structure'],font_path=args.font)
    (output/'scenes.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Generated {len(cases)} controlled SVG/PNG scenes; not real OCR acceptance')


if __name__=='__main__':main()
