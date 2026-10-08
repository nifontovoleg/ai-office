import { useId, useRef, useState } from 'react';
import { Check, Download, ExternalLink, FileText, Link2, Loader2, Paperclip, Trash2, Upload } from 'lucide-react';
import type { Material } from './types';
import { api } from './ui';

export const MAX_FILE_SIZE = 50 * 1024 * 1024;
type QueueEntry = { id: string; file?: File; url?: string; title: string; status: 'pending'|'uploading'|'saved'|'error'; error?: string; invalid?: boolean; material?: Material };
export const fileSize = (size: number) => size < 1024 ? `${size} Б` : size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} КБ` : `${(size / (1024 * 1024)).toFixed(1)} МБ`;
export const extractionLabel = (material: Material) => material.attachment ? ({extracted:'Текст извлечён',truncated:'Текст извлечён частично',empty:'Текст не найден',unsupported:'Сохранён оригинал',failed:'Не удалось извлечь текст'}[material.attachment.extraction_status] || 'Сохранён оригинал') : material.source_url ? 'Ссылка · содержимое не загружено' : '';
export const materialFileUrl = (material: Material, preview = false) => `/api/projects/${encodeURIComponent(material.project_id)}/materials/${encodeURIComponent(material.id)}/${preview ? 'preview' : 'file'}`;

async function uploadFile(projectId: string, file: File): Promise<Material> {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/materials/upload?filename=${encodeURIComponent(file.name)}`, { method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file });
  if (!response.ok) {
    let message = 'Не удалось загрузить файл. Проверьте соединение и повторите.';
    try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail; } catch { /* Keep a useful local message when the server is unavailable. */ }
    throw new Error(message);
  }
  return response.json();
}

export function useMaterialQueue() {
  const [entries, setEntries] = useState<QueueEntry[]>([]);
  const entriesRef = useRef(entries);
  const running = useRef(false);
  const [working, setWorking] = useState(false);
  const [url, setUrl] = useState('');
  const [linkTitle, setLinkTitle] = useState('');
  const [linkError, setLinkError] = useState('');
  const [summary, setSummary] = useState('');
  const update = (items: QueueEntry[]) => { entriesRef.current = items; setEntries(items); };
  const patch = (id: string, data: Partial<QueueEntry>) => update(entriesRef.current.map(item => item.id === id ? {...item,...data} : item));
  const addFiles = (files: FileList | File[]) => {
    if (running.current) return;
    const added: QueueEntry[] = [];
    for (const file of Array.from(files)) {
      if (entriesRef.current.some(item => item.file?.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified)) continue;
      const invalid = file.size > MAX_FILE_SIZE;
      added.push({id:crypto.randomUUID(),file,title:file.name,status:invalid?'error':'pending',invalid,error:invalid?'Файл больше 50 МБ. Удалите его из списка и выберите файл меньшего размера.':undefined});
    }
    update([...entriesRef.current,...added]);
    setSummary('');
  };
  const prepare = () => {
    if (running.current) return false;
    if (url.trim()) {
      let parsed: URL;
      try { parsed = new URL(url.trim()); if (!['http:','https:'].includes(parsed.protocol)) throw new Error(); }
      catch { setLinkError('Введите полную ссылку, которая начинается с https:// или http://.'); return false; }
      const normalized = parsed.href;
      if (!entriesRef.current.some(item => item.url === normalized)) update([...entriesRef.current,{id:crypto.randomUUID(),url:normalized,title:linkTitle.trim() || parsed.hostname,status:'pending'}]);
      setUrl(''); setLinkTitle(''); setLinkError(''); setSummary('');
    } else if (linkTitle.trim()) {
      setLinkError('Добавьте ссылку для этого названия.'); return false;
    }
    return !entriesRef.current.some(item => item.invalid);
  };
  const uploadAll = async (projectId: string) => {
    if (!prepare()) return false;
    const pending = entriesRef.current.filter(item => item.status !== 'saved');
    if (!pending.length) return true;
    running.current = true; setWorking(true); setSummary('Добавляем материалы в проект…');
    try {
      for (const item of pending) {
        patch(item.id,{status:'uploading',error:undefined});
        try {
          const material = item.file ? await uploadFile(projectId,item.file) : await api<Material>(`/projects/${encodeURIComponent(projectId)}/materials/link`,'POST',{title:item.title,url:item.url});
          patch(item.id,{status:'saved',material});
        } catch (error) {
          patch(item.id,{status:'error',error:error instanceof TypeError ? 'Не удалось связаться с сервером. Проверьте соединение и повторите.' : error instanceof Error ? error.message : 'Не удалось добавить материал. Повторите попытку.'});
        }
      }
      const failed = entriesRef.current.filter(item => item.status !== 'saved').length;
      setSummary(failed ? `Не добавлено: ${failed}. Успешно сохранённые материалы останутся в проекте. Повторная попытка добавит только оставшиеся.` : 'Все материалы сохранены в проекте.');
      return failed === 0;
    } finally { running.current = false; setWorking(false); }
  };
  const remove = (id: string) => { if (!running.current) { update(entriesRef.current.filter(item => item.id !== id)); setSummary(''); } };
  return {entries,working,url,setUrl,linkTitle,setLinkTitle,linkError,setLinkError,summary,addFiles,prepare,uploadAll,remove,hasWork:entries.some(item=>item.status!=='saved')||!!url.trim()||!!linkTitle.trim(),hasInvalid:entries.some(item=>item.invalid)};
}

export function ProjectFields({name,context,onName,onContext,create=false,disabled=false}:{name:string;context:string;onName:(value:string)=>void;onContext:(value:string)=>void;create?:boolean;disabled?:boolean}) {
  const id = useId();
  return <fieldset className="form-fields" disabled={disabled}>
    <div className="field"><label htmlFor={`${id}-name`}>{create?'Название':'Название проекта'}</label><input id={`${id}-name`} required maxLength={120} value={name} onChange={e=>onName(e.target.value)} placeholder="Например, сайт автосервиса «Гараж»" aria-describedby={`${id}-name-hint`}/><small id={`${id}-name-hint`}>Короткое название, по которому вы узнаете проект. До 120 символов.</small></div>
    <div className="field"><label htmlFor={`${id}-context`}>{create?'Контекст':'Контекст проекта'}</label><textarea id={`${id}-context`} rows={7} maxLength={20000} value={context} onChange={e=>onContext(e.target.value)} aria-describedby={`${id}-context-hint`} placeholder={'Например: создаём сайт автосервиса «Гараж» в Екатеринбурге.\nДля кого: автовладельцы, которым нужны ремонт и диагностика.\nЧто нужно: услуги и цены, запись на ремонт, контакты и карта.\nРезультат: готовый адаптивный сайт с понятной формой записи.\nСтиль: спокойный, современный; тёмный фон и оранжевые акценты.'}/><small id={`${id}-context-hint`}>Опишите аудиторию, функции, ожидаемый результат, стиль и ограничения. До 20 000 символов. Контекст передаётся агенту при разрешении чтения контекста проекта.</small></div>
  </fieldset>;
}

export function AttachmentsEditor({queue,disabled=false,existing=[],onMaterial}:{queue:ReturnType<typeof useMaterialQueue>;disabled?:boolean;existing?:Material[];onMaterial?:(id:string)=>void}) {
  const id = useId();
  const picker = useRef<HTMLInputElement>(null);
  const [dragging,setDragging] = useState(false);
  const locked = disabled || queue.working;
  const savedIds = new Set(queue.entries.map(item=>item.material?.id));
  return <section className="attachments-block" aria-labelledby={`${id}-heading`} aria-busy={queue.working}>
    <h3 id={`${id}-heading`}>ТЗ и материалы</h3>
    <p className="attachment-hint" id={`${id}-hint`}>Добавьте техническое задание, документы и примеры. Это можно сделать сейчас или позже в настройках проекта и базе знаний.</p>
    <fieldset className="form-fields" disabled={locked}>
      <div className={`attachment-drop ${dragging?'is-dragging':''}`} onDragOver={e=>{e.preventDefault();if(!locked)setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);if(!locked)queue.addFiles(e.dataTransfer.files);}}>
        <Paperclip size={20}/><strong>Файлы проекта</strong><span id={`${id}-files-hint`}>PDF, DOCX, текст, изображения, фото, видео и другие файлы. До 50 МБ на файл.</span>
        <input ref={picker} id={`${id}-files`} type="file" multiple className="sr-only" tabIndex={-1} aria-label="Файлы проекта" aria-describedby={`${id}-files-hint`} onChange={e=>{if(e.target.files)queue.addFiles(e.target.files);e.target.value='';}}/>
        <button type="button" className="btn btn-secondary" onClick={()=>picker.current?.click()} aria-describedby={`${id}-files-hint`}><Upload size={15}/>Выбрать файлы</button><small>Можно выбрать несколько файлов или перетащить их сюда.</small>
      </div>
      <p className="attachment-hint">Из PDF, DOCX и текстовых файлов извлекается текст. Фото, изображения и видео сохраняются как исходные файлы; распознавание и анализ содержимого пока не выполняются.</p>
      <div className="field"><label htmlFor={`${id}-url`}>Ссылка на ТЗ или материал</label><input id={`${id}-url`} type="url" maxLength={2000} value={queue.url} onChange={e=>{queue.setUrl(e.target.value);queue.setLinkError('');}} placeholder="Например, https://docs.google.com/document/d/…" aria-describedby={`${id}-url-hint${queue.linkError?` ${id}-url-error`:''}`} aria-invalid={!!queue.linkError}/><small id={`${id}-url-hint`}>Ссылка на документ, сайт, папку или пример. Сохраняется адрес; содержимое по ссылке автоматически не загружается.</small></div>
      <div className="attachment-link-row"><div className="field"><label htmlFor={`${id}-link-title`}>Название ссылки (необязательно)</label><input id={`${id}-link-title`} maxLength={180} value={queue.linkTitle} onChange={e=>queue.setLinkTitle(e.target.value)} placeholder="Например, ТЗ на сайт или примеры дизайна"/></div><button type="button" className="btn btn-secondary" onClick={()=>queue.prepare()} disabled={!queue.url.trim()&&!queue.linkTitle.trim()}><Link2 size={15}/>Добавить ссылку</button></div>
      {queue.linkError&&<p id={`${id}-url-error`} className="attachment-error" role="alert">{queue.linkError}</p>}
    </fieldset>
    {!!queue.entries.length&&<ul className="attachment-list" aria-label="Добавляемые материалы">{queue.entries.map(item=><li key={item.id} className={`attachment-item ${item.status==='error'?'has-error':''}`}>
      {item.file?<FileText size={17}/>:<Link2 size={17}/>}<div className="attachment-item-copy">{item.material&&onMaterial?<button type="button" className="attachment-open" disabled={locked} onClick={()=>onMaterial(item.material!.id)}>{item.title}</button>:<strong>{item.title}</strong>}{item.file?<small>{fileSize(item.file.size)}</small>:<a href={item.url} target="_blank" rel="noopener noreferrer">{item.url}<ExternalLink size={12}/></a>}<small className={`attachment-status ${item.status}`} role={item.status==='error'?'alert':undefined}>{item.status==='saved'?<Check size={12}/>:item.status==='uploading'?<Loader2 size={12} className="spin"/>:null}{item.status==='saved'?`Сохранено${item.material?.attachment?` · ${extractionLabel(item.material)}`:''}`:item.status==='uploading'?'Загружается…':item.status==='error'?item.error:'Добавится при сохранении'}</small></div>
      {item.status!=='saved'&&<button type="button" className="btn btn-ghost icon-btn" disabled={locked} aria-label={`Убрать ${item.file?'файл':'ссылку'} ${item.title}`} onClick={()=>queue.remove(item.id)}><Trash2 size={16}/></button>}
    </li>)}</ul>}
    {queue.summary&&<p className="attachment-summary" role="status" aria-live="polite">{queue.summary}</p>}
    {!!existing.filter(material=>(material.attachment||material.source_url)&&!savedIds.has(material.id)).length&&<><h4>Уже в проекте</h4><ul className="attachment-list" aria-label="Сохранённые материалы">{existing.filter(material=>(material.attachment||material.source_url)&&!savedIds.has(material.id)).map(material=><li key={material.id} className="attachment-item"><span>{material.attachment?<FileText size={17}/>:<Link2 size={17}/>}</span><div className="attachment-item-copy">{onMaterial?<button type="button" className="attachment-open" disabled={locked} onClick={()=>onMaterial(material.id)}>{material.title}</button>:<strong>{material.title}</strong>}<small>{material.attachment?`${fileSize(material.attachment.size)} · ${extractionLabel(material)}`:extractionLabel(material)}</small>{material.source_url&&<a href={material.source_url} target="_blank" rel="noopener noreferrer">{material.source_url}<ExternalLink size={12}/></a>}</div>{material.attachment&&<a className="btn btn-ghost icon-btn" href={materialFileUrl(material)} download aria-label={`Скачать оригинал ${material.attachment.filename}`}><Download size={15}/></a>}</li>)}</ul></>}
  </section>;
}
