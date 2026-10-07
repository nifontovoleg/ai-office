import { useEffect, useState } from 'react';
import { Plus, Search, Settings2, ShieldCheck, UsersRound, X } from 'lucide-react';
import type { Catalog, State } from './types';
import { Badge } from './ui';
import { categoryIcon, memberNames } from './Map';

export default function Team({state,catalog,onAgent,onAll,busy}:{state:State;catalog:Catalog;onAgent:(id:string,tab?:string)=>void;onAll:()=>void;busy:boolean}){
  const [search,setSearch]=useState(''),[category,setCategory]=useState('all'),[page,setPage]=useState(0);
  useEffect(()=>setPage(0),[search,category]);
  const filtered=state.members.filter(m=>{const p=catalog.agents.find(p=>p.id===m.profile_id)!;return (category==='all'||p.category===category)&&(!search||`${m.display_name_ru} ${p.display_name_ru} ${p.description_ru} ${p.name} ${p.id} ${p.description}`.toLowerCase().includes(search.toLowerCase()));});
  const pageCount=Math.max(1,Math.ceil(filtered.length/30));
  const pageIndex=Math.min(page,pageCount-1);
  useEffect(()=>setPage(p=>Math.min(p,pageCount-1)),[pageCount]);
  const visible=filtered.slice(pageIndex*30,(pageIndex+1)*30);
  const departmentCount=new Set(state.members.map(m=>catalog.agents.find(p=>p.id===m.profile_id)?.category)).size;
  return <><div className="catalog-toolbar team-toolbar"><label className="search-field"><Search size={17}/><input aria-label="Поиск участников команды" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Найти участника, роль или специализацию…"/>{search&&<button aria-label="Очистить поиск команды" onClick={()=>setSearch('')}><X size={15}/></button>}</label><select className="category-select" aria-label="Отдел команды" value={category} onChange={e=>setCategory(e.target.value)}><option value="all">Все отделы · {departmentCount}</option>{catalog.categories.filter(c=>state.members.some(m=>catalog.agents.find(p=>p.id===m.profile_id)?.category===c.id)).map(c=><option value={c.id} key={c.id}>{c.display_name_ru} · {state.members.filter(m=>catalog.agents.find(p=>p.id===m.profile_id)?.category===c.id).length}</option>)}</select><span className="mono">В КОМАНДЕ: {state.members.length}</span></div>
    {state.members.length<catalog.agent_count&&<div className="all-team-banner info-banner"><UsersRound size={18}/><span>Доступны все {catalog.agent_count} исходных профиля Agency Agents.</span><button className="btn btn-secondary" disabled={busy} onClick={onAll}><Plus size={15}/>Добавить все {catalog.agent_count}</button></div>}
    <div className="section-panel team-table"><div className="table-heading"><span>АГЕНТ / РОЛЬ</span><span>ОТДЕЛ</span><span>СОСТОЯНИЕ</span><span>АВТОНОМНОСТЬ</span><span/></div>{visible.map(m=>{const p=catalog.agents.find(p=>p.id===m.profile_id)!;const c=catalog.categories.find(c=>c.id===p.category);return <div className="member-row" key={m.profile_id}><button className="member-identity" onClick={()=>onAgent(m.profile_id)}><span className="profile-icon" style={{color:c?.ui_color}}>{categoryIcon(p.category,20)}</span><span><strong>{memberNames(m,catalog)}</strong><small>{c?.display_name_ru}</small></span></button><span className="team-category" style={{color:c?.ui_color}}>{c?.display_name_ru}</span><Badge status={m.status}/><span className="autonomy-label">{{confirm:'С подтверждением',task:'В рамках задачи',schedule:'По расписанию'}[m.autonomy]}</span><button className="btn btn-ghost icon-btn" aria-label={`Настроить ${memberNames(m,catalog)}`} onClick={()=>onAgent(m.profile_id,'access')}><Settings2 size={17}/></button></div>;})}</div>
    {!visible.length&&<div className="empty-state"><Search size={32}/><h3>Участники не найдены</h3><p>Измените запрос или отдел.</p><button className="btn btn-secondary" onClick={()=>{setSearch('');setCategory('all');setPage(0);}}>Сбросить фильтры команды</button></div>}
    <div className="pagination" aria-label="Страницы команды"><span>Показано {filtered.length?pageIndex*30+1:0}–{Math.min((pageIndex+1)*30,filtered.length)} из {filtered.length}</span><button className="btn btn-secondary" disabled={pageIndex===0} onClick={()=>setPage(pageIndex-1)}>Назад</button><button className="btn btn-secondary" disabled={pageIndex+1>=pageCount} onClick={()=>setPage(pageIndex+1)}>Далее</button></div>
    <p className="panel-note"><ShieldCheck size={15}/>Удаление участника из команды сохраняет исходный профиль в библиотеке. Роль и разрешения редактируются в карточке. Задачи выполняют только назначенные исполнители.</p>
  </>;
}
