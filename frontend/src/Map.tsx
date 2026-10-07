import { useEffect, useRef, useState } from 'react';
import { ArrowDown, BriefcaseBusiness, ChevronLeft, ChevronRight, Code2, FileText, GitBranch, Layers3, Maximize2, Minus, MousePointer2, Pause, PenTool, Play, Plus, Scan, ShieldCheck, UserRound, Workflow, Wrench } from 'lucide-react';
import type { Category, Catalog, Member, OfficeEvent, State, View } from './types';
import { STATUS } from './ui';

export const categoryIcon = (id: string, size = 18) => {
  const Icon = id === 'design' ? PenTool : id === 'engineering' ? Code2 : id === 'testing' || id === 'security' ? ShieldCheck : id === 'project-management' ? BriefcaseBusiness : id === 'specialized' ? Workflow : Layers3;
  return <Icon size={size} strokeWidth={1.5}/>;
};
export const memberNames = (member: Member, catalog: Catalog) => {
  const profile=catalog.agents.find(p=>p.id===member.profile_id);
  const localized=profile&&'display_name_ru' in profile&&typeof profile.display_name_ru==='string'?profile.display_name_ru:'';
  return member.display_name_ru||localized||'Агент';
};
export const plural = (count:number, one:string, few:string, many:string) => count%100>=11&&count%100<=14?many:count%10===1?one:count%10>=2&&count%10<=4?few:many;

function Core({ motion }: {motion: boolean}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    const ctx:CanvasRenderingContext2D=context;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = 190 * dpr; canvas.height = 190 * dpr;
    ctx.scale(dpr, dpr);
    const points = Array.from({length: 112}, (_, i) => {
      const angle = i * 2.399963;
      const z = 1 - (i + .5) / 56;
      const r = Math.sqrt(1-z*z);
      return {x: Math.cos(angle)*r, y: Math.sin(angle)*r, z};
    });
    let frame = 0;
    let start: number | undefined;
    function draw(t: number) {
      start ??= t;
      const a = motion ? (t-start) * .000055 : .25;
      ctx.clearRect(0,0,190,190);
      const projected = points.map(p => ({x: 95+(p.x*Math.cos(a)+p.z*Math.sin(a))*65, y:95+p.y*65, z:p.z*Math.cos(a)-p.x*Math.sin(a)}));
      const gradient = ctx.createRadialGradient(95,95,4,95,95,82);
      gradient.addColorStop(0,'rgba(239,122,145,.12)'); gradient.addColorStop(1,'rgba(239,122,145,0)');
      ctx.fillStyle=gradient; ctx.fillRect(0,0,190,190);
      projected.forEach((p,i) => {
        projected.slice(i+1).forEach(q => {
          const distance = Math.hypot(p.x-q.x,p.y-q.y,p.z*65-q.z*65);
          if(distance < 27) {
            ctx.beginPath(); ctx.moveTo(p.x,p.y); ctx.lineTo(q.x,q.y);
            ctx.strokeStyle=`rgba(240,133,152,${.08+(1-distance/27)*.2})`; ctx.lineWidth=.5; ctx.stroke();
          }
        });
        ctx.beginPath(); ctx.arc(p.x,p.y,p.z>.3?1.8:1.05,0,Math.PI*2);
        ctx.fillStyle=p.z>.3?'#ffc0c4':`rgba(238,133,151,${.35+(p.z+1)*.2})`; ctx.fill();
      });
      if(motion) frame=requestAnimationFrame(draw);
    }
    draw(performance.now());
    return () => cancelAnimationFrame(frame);
  }, [motion]);
  return <canvas ref={ref} style={{width:190,height:190}} aria-hidden="true"/>;
}

type Node = {id:string; x:number; y:number; type:string; label:string; sub?:string; color:string; agent?:string; category?:string; material?:string; tool?:string; status?:string};
type Edge = {from:string; to:string; label:string; color?:string};
type Props = {state:State; catalog:Catalog; view:View; setView:(v:View)=>void; category:string|null; setCategory:(c:string|null)=>void; onAgent:(id:string)=>void; onTask:(id:string)=>void; onMaterial:(id:string)=>void; onKnowledge:()=>void; selectedTaskId:string|null; motion:boolean; setMotion:(b:boolean)=>void; pulse:OfficeEvent|null};

export default function OfficeMap(props:Props) {
  const {state,catalog,view,setView,category,setCategory,onAgent,onTask,onMaterial,onKnowledge,selectedTaskId,motion,setMotion,pulse}=props;
  const [reducedMotion,setReducedMotion]=useState(window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const animate=motion&&!reducedMotion;
  const [zoom,setZoom]=useState(1);
  const [pan,setPan]=useState({x:0,y:0});
  const [selected,setSelected]=useState<string|null>(null);
  const [filters,setFilters]=useState<string[]>(['agent','task','material','tool']);
  const [memberPage,setMemberPage]=useState(0);
  const [graphScope,setGraphScope]=useState('task');
  const container=useRef<HTMLDivElement>(null);
  const drag=useRef<{x:number;y:number;px:number;py:number}|null>(null);
  const profiles=new Map(catalog.agents.map(p=>[p.id,p]));
  const categories=new Map(catalog.categories.map(c=>[c.id,c]));
  const membersByCategory=new Map<string,Member[]>();
  state.members.forEach(member=>{
    const id=profiles.get(member.profile_id)?.category;
    if(id)membersByCategory.set(id,[...(membersByCategory.get(id)||[]),member]);
  });
  const cats=catalog.categories.filter(c=>(membersByCategory.get(c.id)?.length||0)>0);
  const largeTeam=state.members.length>24;
  const task=state.tasks.find(t=>t.id===selectedTaskId)||state.tasks[0];
  const active=state.members.find(m=>m.status==='working');
  const catFor=(member:Member):Category|undefined=>categories.get(profiles.get(member.profile_id)?.category||'');
  const department=cats.find(c=>c.id===category)||cats[0];
  const departmentMembers=membersByCategory.get(department?.id||'')||[];
  const taskAgents=new Set(task?.stages.map(stage=>stage.agent_id)||[]);
  const graphMembers=largeTeam?(graphScope==='task'?state.members.filter(m=>taskAgents.has(m.profile_id)):membersByCategory.get(graphScope)||[]):state.members;
  const scopedMembers=view==='department'?departmentMembers:graphMembers;
  const pageSize=8;
  const gridDepartment=view==='department'&&departmentMembers.length>4;
  const paginated=gridDepartment||largeTeam&&view==='graph';
  const pageCount=Math.max(1,Math.ceil(scopedMembers.length/pageSize));
  const pageIndex=Math.min(memberPage,pageCount-1);
  const visibleMembers=paginated?scopedMembers.slice(pageIndex*pageSize,(pageIndex+1)*pageSize):scopedMembers;
  const graphMaterials=state.materials.filter(m=>!m.task_id||m.task_id===task?.id);
  const visibleGraphMaterials=graphMaterials.slice(largeTeam?-4:-6);
  const reset=()=>{setZoom(1);setPan({x:0,y:0});};
  useEffect(()=>{
    const preference=window.matchMedia('(prefers-reduced-motion: reduce)');
    const update=()=>setReducedMotion(preference.matches);
    preference.addEventListener('change',update);
    return()=>preference.removeEventListener('change',update);
  },[]);
  useEffect(()=>{reset();setSelected(null);setMemberPage(0);},[view,category,graphScope,state.project.id]);
  useEffect(()=>{reset();setSelected(null);},[largeTeam]);
  useEffect(()=>{setMemberPage(p=>Math.min(p,pageCount-1));},[pageCount]);
  useEffect(()=>{
    const el=container.current;
    if(!el) return;
    const wheel=(e:WheelEvent)=>{e.preventDefault();setZoom(z=>Math.max(.45,Math.min(2.6,z-e.deltaY*.001)));};
    el.addEventListener('wheel',wheel,{passive:false});
    return()=>el.removeEventListener('wheel',wheel);
  },[]);
  const nodes:Node[]=[]; const edges:Edge[]=[];
  if(view==='radial'){
    nodes.push({id:'core',x:550,y:350,type:'core',label:'ЯДРО ЗНАНИЙ',sub:`${state.materials.length} ${plural(state.materials.length,'материал','материала','материалов')} проекта`,color:'#ef8a98'});
    cats.forEach((cat,ci)=>{
      const angle=-Math.PI/2+ci*Math.PI*2/cats.length;
      const members=membersByCategory.get(cat.id)||[];
      const memberCount=members.length;
      nodes.push({id:cat.id,x:550+Math.cos(angle)*(largeTeam?420:163),y:350+Math.sin(angle)*(largeTeam?270:163),type:largeTeam?'department-summary':'department',label:cat.display_name_ru,sub:`${memberCount} ${plural(memberCount,'агент','агента','агентов')}`,color:cat.ui_color,category:cat.id});
      edges.push({from:'core',to:cat.id,label:'Контекст проекта',color:cat.ui_color});
      if(!largeTeam)members.forEach((member,mi)=>{
        const spread=(mi-(members.length-1)/2)*.68;
        const agentAngle=angle+spread;
        nodes.push({id:member.profile_id,x:550+Math.cos(agentAngle)*318,y:350+Math.sin(agentAngle)*270,type:'agent',label:memberNames(member,catalog),sub:'Участник проекта',color:cat.ui_color,agent:member.profile_id,status:member.status});
        edges.push({from:cat.id,to:member.profile_id,label:'Участник отдела',color:cat.ui_color});
      });
    });
  } else if(view==='department'){
    const cat=department;
    const members=visibleMembers;
    const tools=state.tools.filter(t=>members.some(m=>m.tools.includes(t.id)));
    tools.forEach((tool,i)=>nodes.push({id:tool.id,x:550+(i-(tools.length-1)/2)*210,y:gridDepartment?135:110,type:'tool',label:tool.name,sub:tool.connected?'Подключён · локальный':'Не подключён',color:'#8b9bac',tool:tool.id,status:tool.connected?'free':'disconnected'}));
    members.forEach((member,i)=>{
      const row=Math.floor(i/4),columns=Math.min(4,members.length-row*4);
      const x=gridDepartment?550+(i%4-(columns-1)/2)*240:550+(i-(members.length-1)/2)*245;
      const y=gridDepartment?260+row*185:285;
      nodes.push({id:member.profile_id,x,y,type:'agent',label:memberNames(member,catalog),sub:'Участник проекта',color:cat.ui_color,agent:member.profile_id,status:member.status});
      member.tools.forEach(id=>edges.push({from:id,to:member.profile_id,label:'Разрешённый инструмент',color:cat.ui_color}));
      const stage=task?.stages.find(s=>s.agent_id===member.profile_id&&s.status!=='completed')||task?.stages.find(s=>s.agent_id===member.profile_id);
      nodes.push({id:'process-'+member.profile_id,x,y:gridDepartment?y+85:455,type:'process',label:stage?.name||'Ожидает назначения',sub:stage?.status==='completed'?'Завершено':stage?.status==='running'?'В работе':stage?'Этап задачи':'Этап не назначен',color:cat.ui_color});
      edges.push({from:member.profile_id,to:'process-'+member.profile_id,label:'Выполняет процесс',color:cat.ui_color});
      edges.push({from:'process-'+member.profile_id,to:cat.id,label:'Процесс отдела',color:cat.ui_color});
    });
    if(cat)nodes.push({id:cat.id,x:550,y:gridDepartment?640:615,type:'department',label:cat.display_name_ru,sub:gridDepartment?`${departmentMembers.length} ${plural(departmentMembers.length,'агент','агента','агентов')} в отделе`:'Отдел проекта',color:cat.ui_color,category:cat.id});
  } else if(view==='hierarchy'){
    nodes.push({id:'owner',x:550,y:65,type:'owner',label:state.project.owner,color:'#dce7f0',sub:'Итоговое решение'});
    const coordinator=state.members.find(m=>m.profile_id==='agents-orchestrator');
    if(coordinator){nodes.push({id:coordinator.profile_id,x:550,y:190,type:'agent',label:memberNames(coordinator,catalog),sub:'Координатор проекта',color:'#ef8a98',agent:coordinator.profile_id,status:coordinator.status});edges.push({from:'owner',to:coordinator.profile_id,label:'Руководит проектом'});}
    cats.forEach((cat,ci)=>{
      if(largeTeam){
        nodes.push({id:cat.id,x:120+(ci%6)*172,y:335+Math.floor(ci/6)*110,type:'department-summary',label:cat.display_name_ru,sub:`${membersByCategory.get(cat.id)?.length||0} ${plural(membersByCategory.get(cat.id)?.length||0,'агент','агента','агентов')}`,color:cat.ui_color,category:cat.id});
        edges.push({from:coordinator?.profile_id||'owner',to:cat.id,label:'Отдел проекта',color:cat.ui_color});
        return;
      }
      const x=110+ci*880/Math.max(1,cats.length-1);
      const members=state.members.filter(m=>catFor(m)?.id===cat.id&&m!==coordinator);
      if(!members.length)return;
      nodes.push({id:cat.id,x,y:345,type:'department',label:cat.display_name_ru,color:cat.ui_color,category:cat.id});
      edges.push({from:coordinator?.profile_id||'owner',to:cat.id,label:'Отдел проекта',color:cat.ui_color});
      members.forEach((member,mi)=>{
        nodes.push({id:member.profile_id,x,y:470+mi*115,type:'agent',label:memberNames(member,catalog),sub:'Назначено: '+state.tasks.filter(t=>t.stages.some(s=>s.agent_id===member.profile_id)).length,color:cat.ui_color,agent:member.profile_id,status:member.status});
        const manager=member.manager_id;
        edges.push({from:manager&&manager!==coordinator?.profile_id?manager:cat.id,to:member.profile_id,label:'Подчиняется руководителю',color:cat.ui_color});
      });
    });
  } else {
    if(task&&filters.includes('task'))nodes.push({id:task.id,x:550,y:largeTeam?405:345,type:'task',label:task.title,sub:`Этап ${Math.min(task.cursor+1,task.stages.length)} / ${task.stages.length}`,color:'#ef8a98'});
    const members=largeTeam?visibleMembers:state.members;
    if(filters.includes('agent'))members.forEach((m,i)=>{
      const angle=-Math.PI/2+i*Math.PI*2/members.length;
      nodes.push({id:m.profile_id,x:550+Math.cos(angle)*345,y:(largeTeam?405:345)+Math.sin(angle)*(largeTeam?160:240),type:'agent',label:memberNames(m,catalog),color:catFor(m)?.ui_color||'#a394ef',agent:m.profile_id,status:m.status});
      if(task?.stages.some(s=>s.agent_id===m.profile_id))edges.push({from:m.profile_id,to:task.id,label:'Выполняет задачу'});
    });
    if(filters.includes('material'))visibleGraphMaterials.forEach((m,i)=>{
      nodes.push({id:m.id,x:largeTeam?550+(i-(visibleGraphMaterials.length-1)/2)*235:120+i*172,y:650,type:'material',label:m.title,color:'#e8bf70',material:m.id,sub:m.example?'Пример':'Материал проекта'});
      if(task)edges.push({from:task.id,to:m.id,label:m.kind==='source'?'Использует материал':'Результат этапа',color:'#e8bf70'});
      if(m.agent_id)edges.push({from:m.agent_id,to:m.id,label:'Создал материал',color:'#e8bf70'});
    });
    if(filters.includes('tool'))state.tools.filter(t=>t.connected).forEach((t,i)=>{
      nodes.push({id:t.id,x:325+i*225,y:largeTeam?145:65,type:'tool',label:t.name,color:'#83a9ef',tool:t.id,sub:'Подключён · локальный'});
      members.filter(m=>m.tools.includes(t.id)).forEach(m=>edges.push({from:m.profile_id,to:t.id,label:'Разрешён инструмент',color:'#83a9ef'}));
    });
    if(pulse?.action==='handoff'&&pulse.target_agent_id)edges.push({from:pulse.agent_id!,to:pulse.target_agent_id,label:'Передал результат',color:'#ef8a98'});
  }
  const connected=new Set<string>(selected?[selected,...edges.filter(e=>e.from===selected||e.to===selected).flatMap(e=>[e.from,e.to])]:nodes.map(n=>n.id));
  const nodeClick=(node:Node)=>{
    setSelected(node.id);
    if(node.agent)onAgent(node.agent);
    else if(node.category){setCategory(node.category);setView('department');}
    else if(node.material)onMaterial(node.material);
    else if(node.type==='task')onTask(node.id);
  };
  const zoomTo=(delta:number)=>setZoom(z=>Math.min(2.6,Math.max(.45,z+delta)));
  const focusNode=(node:Node)=>{
    if(window.innerWidth<=700)setPan({x:(550-node.x)*zoom,y:(370-node.y)*zoom});
  };
  const statusColor=(status?:string)=>status==='working'||status==='tool'?'#b5a5f7':status==='error'?'#ef8a98':status==='approval'?'#e8bf70':status==='free'||status==='completed'?'#7bc8b1':status==='queued'||status==='waiting'?'#92b6f5':'#9aa8b9';
  const departmentLabel=(node:Node)=>({academic:'Наука','game-development':'Игры',gis:'Геоданные',healthcare:'Медицина','paid-media':'Реклама','project-management':'Управление','spatial-computing':'Пространство',specialized:'Спец. роли'}[node.category||'']||node.label);
  const changePage=(delta:number)=>{setMemberPage(p=>Math.max(0,Math.min(pageCount-1,p+delta)));reset();setSelected(null);};
  const shownStart=visibleMembers.length?pageIndex*pageSize+1:0;
  const shownEnd=pageIndex*pageSize+visibleMembers.length;
  return <section className={`map-shell ${animate?'':'effects-paused'} ${largeTeam?'large-team-map':''} ${gridDepartment?'department-grid-map':''}`} aria-label="Интерактивная карта офиса">
    <div className="map-topline"><div className="map-breadcrumb"><span className="tiny-dot"/> {view==='department'?catalog.categories.find(c=>c.id===category)?.display_name_ru:'Все отделы'}<span className="mono"> / {String(state.members.length).padStart(2,'0')} {plural(state.members.length,'АГЕНТ','АГЕНТА','АГЕНТОВ')}</span></div><div className="map-utilities"><button title={motion?'Приостановить визуальные эффекты':'Включить визуальные эффекты'} aria-label={motion?'Приостановить визуальные эффекты':'Включить визуальные эффекты'} onClick={()=>setMotion(!motion)}>{motion?<Pause size={14}/>:<Play size={14}/>}</button><button title="Полноэкранный просмотр" aria-label="Полноэкранный просмотр" onClick={()=>{if(document.fullscreenElement)void document.exitFullscreen();else void container.current?.parentElement?.requestFullscreen();}}><Maximize2 size={15}/></button></div></div>
    {view==='graph'&&<div className="graph-filters" aria-label="Типы связей">{[['agent','Агенты'],['task','Задачи'],['material','Материалы'],['tool','Инструменты']].map(([id,label])=><button key={id} aria-pressed={filters.includes(id)} className={filters.includes(id)?'selected':''} onClick={()=>setFilters(f=>f.includes(id)?f.filter(x=>x!==id):[...f,id])}><span className={`filter-dot ${id}`}/>{label}</button>)}</div>}
    {largeTeam&&(view==='radial'||view==='hierarchy')&&<div className="map-bulk-note"><strong>{cats.length} отделов · {state.members.length} {plural(state.members.length,'участник','участника','участников')}</strong><span>Выберите отдел, чтобы открыть его участников</span><select className="map-mobile-departments" aria-label="Открыть отдел на карте" value="" onChange={e=>{setCategory(e.target.value);setView('department');}}><option value="" disabled>Выбрать отдел…</option>{cats.map(cat=><option key={cat.id} value={cat.id}>{cat.display_name_ru} · {membersByCategory.get(cat.id)?.length||0}</option>)}</select></div>}
    {paginated&&<div className={`map-member-toolbar ${view==='graph'?'graph-member-toolbar':''}`}>
      {view==='graph'&&<label className="map-scope-picker"><span className="sr-only">Участники на карте связей</span><select aria-label="Участники на карте связей" value={graphScope} onChange={e=>setGraphScope(e.target.value)}><option value="task">Исполнители выбранной задачи</option>{cats.map(cat=><option value={cat.id} key={cat.id}>{cat.display_name_ru} · {membersByCategory.get(cat.id)?.length||0}</option>)}</select></label>}
      <div className="map-page-summary" role="status" aria-live="polite"><strong>{view==='graph'&&!filters.includes('agent')?'Агенты скрыты фильтром':`Показано ${shownStart}–${shownEnd} из ${scopedMembers.length}`}</strong>{view==='graph'&&<span>из {state.members.length} участников команды · {graphScope==='task'?'исполнители задачи':'выбранный отдел'}</span>}</div>
      <nav className="map-page-controls" aria-label={view==='department'?'Страницы отдела':'Страницы участников карты'}><button aria-label={view==='department'?'Предыдущая страница отдела':'Предыдущая страница карты'} disabled={pageIndex===0} onClick={()=>changePage(-1)}><ChevronLeft size={16}/></button><span className="mono">{pageIndex+1} / {pageCount}</span><button aria-label={view==='department'?'Следующая страница отдела':'Следующая страница карты'} disabled={pageIndex===pageCount-1} onClick={()=>changePage(1)}><ChevronRight size={16}/></button></nav>
    </div>}
    {view==='department'&&!gridDepartment&&<div className="department-labels">{['Инструменты','Агенты','Процессы','Отдел'].map((t,i)=><span key={t} style={{top:`${[12,35,57,78][i]}%`}}>{String(i+1).padStart(2,'0')}<br/>{t}</span>)}</div>}
    <div className="map-canvas" ref={container} tabIndex={0} role="group" aria-label="Поле карты. Стрелки перемещают карту, плюс и минус меняют масштаб, Home возвращает общий вид" onKeyDown={e=>{
      if(e.target!==e.currentTarget)return;
      if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','Home','Escape'].includes(e.key))e.preventDefault();
      if(e.key==='Home'||e.key==='Escape'){reset();setSelected(null);}
      else if(e.key==='+'||e.key==='=')zoomTo(.15);
      else if(e.key==='-')zoomTo(-.15);
      else if(e.key.startsWith('Arrow'))setPan(p=>({x:p.x+(e.key==='ArrowLeft'?45:e.key==='ArrowRight'?-45:0),y:p.y+(e.key==='ArrowUp'?45:e.key==='ArrowDown'?-45:0)}));
    }} onPointerDown={e=>{if(e.button!==0||(e.target as Element).closest('[data-node]'))return;drag.current={x:e.clientX,y:e.clientY,px:pan.x,py:pan.y};e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(drag.current){const r=e.currentTarget.querySelector('svg')!.getBoundingClientRect();const scale=Math.min(r.width/1100,r.height/740);setPan({x:drag.current.px+(e.clientX-drag.current.x)/scale,y:drag.current.py+(e.clientY-drag.current.y)/scale});}}} onPointerUp={()=>drag.current=null} onPointerCancel={()=>drag.current=null} onLostPointerCapture={()=>drag.current=null}>
      <svg className="office-svg" viewBox="0 0 1100 740" role="group" aria-label={view==='radial'?'Радиальная карта команды':view==='department'?'Детализация отдела':view==='hierarchy'?'Иерархия команды':'Карта связей'}>
        <defs><filter id="glow"><feGaussianBlur stdDeviation="3"/></filter><radialGradient id="core-glow"><stop offset="0" stopColor="#ed8298" stopOpacity=".13"/><stop offset="1" stopColor="#ed8298" stopOpacity="0"/></radialGradient></defs>
        <g transform={`translate(${pan.x} ${pan.y}) translate(550 370) scale(${zoom}) translate(-550 -370)`}>
          {view==='radial'&&<g className="orbit-rings"><circle cx="550" cy="350" r="92" fill="url(#core-glow)" stroke="#7d4a58"/><circle cx="550" cy="350" r="163"/><circle cx="550" cy="350" r="271" strokeDasharray="2 9"/><circle cx="550" cy="350" r="305"/><path d="M218 350h45m574 0h45M550 15v28m0 614v28"/><text x="570" y="56">КОЛЬЦО / 01</text></g>}
          {view==='radial'&&largeTeam&&<g className="team-orbit-dots" aria-hidden="true">{state.members.map((member,i)=>{const angle=-Math.PI/2+i*Math.PI*2/state.members.length;return <circle key={member.profile_id} cx={550+Math.cos(angle)*(480+(i%2)*7)} cy={350+Math.sin(angle)*(318+(i%2)*7)} r={member.status==='working'?3:1.8} fill={catFor(member)?.ui_color||'#94a4b7'} opacity={member.status==='working'?1:.5}/>;})}</g>}
          {edges.map((edge,i)=>{
            const from=nodes.find(n=>n.id===edge.from),to=nodes.find(n=>n.id===edge.to);if(!from||!to)return null;
            const animated=animate&&pulse&&((pulse.action==='handoff'&&edge.from===pulse.agent_id&&edge.to===pulse.target_agent_id)||(pulse.action==='tool_used'&&((edge.from===pulse.agent_id&&edge.to===pulse.tool_id)||(edge.to===pulse.agent_id&&edge.from===pulse.tool_id))));
            const highlighted=Boolean(selected&&(edge.from===selected||edge.to===selected));
            const path=view==='hierarchy'?`M${from.x} ${from.y+30} V${(from.y+to.y)/2} H${to.x} V${to.y-27}`:`M${from.x} ${from.y} L${to.x} ${to.y}`;
            return <g key={`${edge.from}-${edge.to}-${i}`} opacity={selected&&!highlighted? .12:1}><path d={path} stroke={edge.color||'#55697e'} fill="none" strokeWidth={highlighted?1.6:.9} opacity={highlighted? .85:.42}/>{animated&&<path className="event-pulse" d={path} stroke={edge.color||'#ef8a98'} fill="none" strokeWidth="3"/>}{highlighted&&view==='graph'&&<text className="edge-label" x={(from.x+to.x)/2} y={(from.y+to.y)/2-9}>{animated&&pulse?.action==='tool_used'?'Использует инструмент':edge.label}</text>}</g>;
          })}
          {nodes.map(node=>{
            const isActive=node.status==='working';
            if(node.type==='core')return <g className="core-node" key={node.id} data-node="true" role="button" tabIndex={0} aria-label={`Открыть базу знаний, ${node.sub}`} onFocus={()=>focusNode(node)} onClick={onKnowledge} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onKnowledge();}}}><circle className="core-focus-ring" cx={node.x} cy={node.y} r="95" fill="none" stroke="none"/><foreignObject x={node.x-95} y={node.y-95} width="190" height="190"><Core motion={animate}/></foreignObject><text className="core-label" x={node.x} y={node.y+80}>{node.label}</text><text className="core-sub" x={node.x} y={node.y+102}>{node.sub}</text><text className="core-caption" x={node.x} y={node.y-83}>КОНТЕКСТ ПРОЕКТА</text></g>;
            if(node.type==='department-summary')return <g className="svg-node department-summary-node" key={node.id} data-node="true" role="button" tabIndex={0} aria-label={`Открыть отдел ${node.label}, ${node.sub}`} onFocus={()=>focusNode(node)} onClick={()=>nodeClick(node)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();nodeClick(node);}}} style={{color:node.color}}><title>{node.label} · {node.sub}</title><rect className="node-hit-area" x={node.x-68} y={node.y-34} width="136" height="68" fill="transparent"/><rect x={node.x-66} y={node.y-23} width="132" height="46" rx="8" fill="#101925" stroke={node.color} strokeOpacity=".6"/><foreignObject x={node.x-54} y={node.y-10} width="20" height="20"><div className="node-icon">{categoryIcon(node.category!,17)}</div></foreignObject><text className="summary-name" x={node.x-26} y={node.y-2} fill={node.color} textLength={departmentLabel(node).length>10?86:undefined} lengthAdjust="spacingAndGlyphs">{departmentLabel(node)}</text><text className="summary-count" x={node.x-26} y={node.y+15}>{node.sub}</text></g>;
            if(node.type==='department')return <g className="svg-node department-node" key={node.id} data-node="true" role="button" tabIndex={0} aria-label={`Открыть отдел ${node.label}`} onFocus={()=>focusNode(node)} onClick={()=>nodeClick(node)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();nodeClick(node);}}} style={{color:node.color}} opacity={connected.has(node.id)?1:.25}><title>{node.label}</title><circle className="node-hit-area" cx={node.x} cy={node.y} r="34" fill="transparent"/><circle cx={node.x} cy={node.y} r={view==='radial'?23:25} fill="#101925" stroke={node.color} strokeOpacity=".65"/><foreignObject x={node.x-12} y={node.y-12} width="24" height="24"><div className="node-icon">{categoryIcon(node.category!,22)}</div></foreignObject><text className="department-name" x={node.x} y={node.y+44} fill={node.color}>{departmentLabel(node)}</text>{zoom>.7&&node.sub&&<text className="node-sub" x={node.x} y={node.y+63}>{node.sub}</text>}</g>;
            const Icon=node.type==='agent'?UserRound:node.type==='task'?GitBranch:node.type==='material'?FileText:node.type==='tool'?Wrench:node.type==='owner'?UserRound:ArrowDown;
            return <g className={`svg-node entity-node ${isActive?'agent-working':''}`} key={node.id} data-node="true" role="button" tabIndex={0} aria-label={`${node.type==='owner'||node.type==='process'||node.type==='tool'?'Выделить связи: ':''}${node.label}${node.type==='tool'?' — '+(node.sub||'Не подключён'):node.status?' — '+(STATUS[node.status]||node.status):''}`} aria-pressed={selected===node.id} onFocus={()=>focusNode(node)} onClick={()=>nodeClick(node)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();nodeClick(node);}}} opacity={connected.has(node.id)?1:.2} style={{color:node.color}}>
              <title>{node.label}</title>
              {isActive&&<rect className="working-ring" x={node.x-100} y={node.y-38} width="200" height="76" rx="13" fill="none" stroke={node.color} strokeOpacity=".4"/>}
              <rect x={node.x-95} y={node.y-32} width="190" height="64" rx="9" fill={isActive?'#1c2234':'#111923'} stroke={isActive?node.color:'#2c3949'} strokeWidth={isActive?1.5:1}/>
              <rect x={node.x-83} y={node.y-19} width="32" height="38" rx="7" fill={node.color} fillOpacity=".09"/>
              <foreignObject x={node.x-76} y={node.y-9} width="19" height="19"><div className="node-icon"><Icon size={18} strokeWidth={1.5}/></div></foreignObject>
              <text className="node-name" x={node.x-43} y={node.y-4}>{node.label.length>18?node.label.slice(0,17)+'…':node.label}</text>
              {zoom>.65&&<text className="node-sub" textAnchor="start" x={node.x-43} y={node.y+16}>{node.type==='tool'?node.sub||'Не подключён':node.status?`${node.status==='working'||node.status==='tool'?'◉':node.status==='error'?'!':node.status==='approval'?'◇':node.status==='queued'||node.status==='waiting'?'◷':node.status==='disconnected'?'⊘':node.status==='completed'?'✓':'○'} ${STATUS[node.status]||node.status}`:node.sub&&node.sub.length>23?node.sub.slice(0,22)+'…':node.sub||''}</text>}
              {node.type==='agent'&&<circle cx={node.x+85} cy={node.y-22} r="3" fill={statusColor(node.status)}/>}
            </g>;
          })}
        </g>
      </svg>
    </div>
    <div className="map-caption"><MousePointer2 size={13}/><span>{largeTeam&&view==='radial'?'Откройте отдел для просмотра агентов':'Выберите отдел или агента'}</span><span className="caption-separator">·</span><span>Перетаскивайте поле</span></div>
    <div className="map-minimap" role="button" tabIndex={0} aria-label="Вернуться к общему виду" onClick={reset} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();reset();}}}><div className="minimap-top"><span>ОБЗОР</span><Scan size={11}/></div><svg viewBox="0 0 1100 740" aria-hidden="true">{nodes.map(n=><circle key={n.id} cx={n.x} cy={n.y} r={n.type==='core'?30:13} fill={n.color}/>)}<rect x="160" y="90" width="780" height="570" rx="10" fill="none" stroke="#627080" strokeWidth="8"/></svg></div>
    <div className="map-controls"><button aria-label="Уменьшить масштаб" onClick={()=>zoomTo(-.15)}><Minus size={16}/></button><span className="mono">{Math.round(zoom*100)}%</span><button aria-label="Увеличить масштаб" onClick={()=>zoomTo(.15)}><Plus size={16}/></button><i/><button aria-label="Вернуться к общему виду" title="Общий вид" onClick={reset}><Scan size={17}/></button></div>
    <div className="map-status"><span className={`tiny-dot ${active?'active':''}`}/><span className="map-status-copy" title={active?memberNames(active,catalog)+' работает':'Команда готова к запуску'}>{active?memberNames(active,catalog)+' работает':'Команда готова к запуску'}</span><span className="mono">{view==='radial'?'ОБЩИЙ ВИД':view==='graph'?'СВЯЗИ':view==='hierarchy'?'ИЕРАРХИЯ':'ОТДЕЛ'}</span></div>
  </section>;
}
