import { createContext, useContext, useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { AlertCircle, Check, CheckCircle2, Circle, Clock3, Loader2, Unplug, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

export const STATUS: Record<string,string> = {free:'Свободен',disconnected:'Не подключён',queued:'В очереди',working:'Работает',tool:'Использует инструмент',waiting:'Ожидает результат',approval:'Требуется решение',error:'Ошибка',completed:'Завершено',pending:'Готова к запуску',running:'В работе',awaiting_approval:'Требуется решение',cancelled:'Отменено'};
export const FeedbackContext = createContext<{message:string;error?:boolean}|null>(null);
export function Badge({status,children}:{status:string;children?:ReactNode}) {
  const Icon=['completed'].includes(status)?CheckCircle2:['working','running','tool'].includes(status)?Loader2:['error','approval','awaiting_approval'].includes(status)?AlertCircle:status==='disconnected'?Unplug:status==='queued'?Clock3:Circle;
  return <span className={`status-badge status-${status}`}><Icon size={12}/>{children||STATUS[status]||status}</span>;
}
export function Markdown({content}:{content:string}) {return <div className="markdown"><ReactMarkdown components={{pre:({node,children,...props})=><pre {...props} tabIndex={0} aria-label="Блок кода, прокручиваемый с клавиатуры">{children}</pre>}}>{content}</ReactMarkdown></div>;}
export function Dialog({title,children,onClose,drawer=false}:{title:string;children:ReactNode;onClose:()=>void;drawer?:boolean}) {
  const feedback=useContext(FeedbackContext);
  const ref=useRef<HTMLDialogElement>(null);
  const closeRef=useRef(onClose);closeRef.current=onClose;
  useEffect(()=>{
    const element=ref.current!;
    const active=document.activeElement as HTMLElement|null;
    element.showModal();
    return()=>{element.close();active?.focus();};
  },[]);
  return <dialog ref={ref} className={drawer?'drawer':'modal'} aria-label={title} onCancel={e=>{e.preventDefault();closeRef.current();}} onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose();}}}>
    <div className={drawer?'drawer-header':'modal-header'}><h2>{title}</h2><button className="btn btn-ghost icon-btn" aria-label="Закрыть" onClick={onClose}><X size={18}/></button></div>{feedback&&<div className={`info-banner dialog-feedback ${feedback.error?'error':''}`} role={feedback.error?'alert':'status'}>{feedback.message}</div>}{children}
  </dialog>;
}
export async function api<T>(path:string,method='GET',body?:unknown):Promise<T> {
  const response=await fetch('/api'+path,{method,headers:body!==undefined?{'Content-Type':'application/json'}:undefined,body:body!==undefined?JSON.stringify(body):undefined});
  if(!response.ok){let error='Не удалось выполнить запрос';try{const data=await response.json();error=typeof data.detail==='string'?data.detail:'Проверьте заполнение полей';}catch{/* The server can be offline. */}throw new Error(error);}
  return response.json();
}
export const time=(value:string)=>new Date(value).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'Asia/Yekaterinburg'});
export const date=(value:string)=>new Date(value).toLocaleString('ru-RU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Yekaterinburg'});
