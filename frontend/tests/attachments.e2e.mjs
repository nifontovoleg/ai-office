import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import { mkdir, writeFile, readFile, open } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const output = path.join(root, 'output/playwright');
const fixtures = path.join(root, '.repo-prep/attachment-fixtures');
await mkdir(output, {recursive:true});
await mkdir(fixtures, {recursive:true});
const python = process.env.OFFICE_PYTHON || path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
execFileSync(python, ['-c', 'import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]) / "tests")); from attachment_fixtures import pdf_bytes, docx_bytes; dest=Path(sys.argv[2]); (dest / "brief.pdf").write_bytes(pdf_bytes()); (dest / "ТЗ.docx").write_bytes(docx_bytes())', root, fixtures]);
// A genuine short MP4 makes the browser decode/range test meaningful.
execFileSync(process.env.FFMPEG || 'ffmpeg', ['-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=0xEC8C9C:s=320x180:d=1','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',path.join(fixtures,'reference.mp4')]);
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=', 'base64');
const upload = (name, mimeType, buffer) => ({name,mimeType,buffer});
const base = process.env.OFFICE_URL || 'http://127.0.0.1:4201';
const browser = await chromium.launch({channel:process.env.OFFICE_BROWSER === 'chromium' ? undefined : process.env.OFFICE_BROWSER || 'msedge',headless:true});
const context = await browser.newContext({viewport:{width:1440,height:1200},reducedMotion:'reduce'});
const page = await context.newPage();
const report = {started:new Date().toISOString(),checks:[],accessibility:[],errors:[],screenshots:[]};
page.on('pageerror', error => report.errors.push(error.message));
const check = name => {report.checks.push(name);console.log('PASS '+name);};
const nav = name => page.getByRole('navigation',{name:'Основное меню'}).getByRole('button',{name,exact:true}).click();
const shot = async name => {await page.screenshot({path:path.join(output,name),fullPage:true});report.screenshots.push(name);};
const a11y = async name => {
  const result = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
  const violations = result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));
  report.accessibility.push({name,violations});assert.deepEqual(violations,[],name);check('Axe '+name);
};
const noOverflow = async () => {
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth),true);
  const dialog=page.getByRole('dialog');
  if(await dialog.count()){
    assert.equal(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth),true);
    assert.equal(await dialog.evaluate(el=>{const rect=el.getBoundingClientRect();return rect.top>=0&&rect.bottom<=innerHeight;}),true,'Dialog header and footer must stay inside the viewport');
  }
};
const projectId = () => page.getByLabel('Текущий проект').inputValue();
const materials = async id => (await (await page.request.get(base+'/api/state/'+id)).json()).materials;
try {
  assert.equal((await (await page.request.get(base+'/api/health')).json()).model.available,false,'Run against an isolated server with models disabled');
  await page.goto(base);await page.getByText('На связи',{exact:true}).waitFor();
  await nav('Настройки');await page.getByRole('button',{name:'Создать другой проект'}).click();
  const modal=page.getByRole('dialog',{name:'Новый проект'});
  await noOverflow();
  assert.match(await modal.getByLabel('Название',{exact:true}).getAttribute('placeholder'),/сайт автосервиса/);
  assert.match(await modal.getByLabel('Контекст',{exact:true}).getAttribute('placeholder'),/Для кого/);
  assert.match(await modal.getByLabel('Название',{exact:true}).getAttribute('aria-describedby'),/name-hint/);
  await a11y('new project with persistent hints');
  await modal.getByLabel('Название',{exact:true}).fill('Сайт автосервиса «Гараж»');
  await modal.getByLabel('Контекст',{exact:true}).fill('Создать современный сайт автосервиса. Аудитория: автовладельцы Екатеринбурга. Нужны услуги, цены, запись на ремонт и контакты. Язык: русский.');
  await modal.getByLabel('Файлы проекта',{exact:true}).setInputFiles([
    upload('brief.pdf','application/pdf',await readFile(path.join(fixtures,'brief.pdf'))),
    upload('ТЗ.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',await readFile(path.join(fixtures,'ТЗ.docx'))),
    upload('photo.png','image/png',png),upload('reference.mp4','video/mp4',await readFile(path.join(fixtures,'reference.mp4'))),
    upload('source.bin','application/octet-stream',Buffer.from([0,255,1,254])),
  ]);
  await modal.getByLabel('Ссылка на ТЗ или материал').fill('https://example.com/design-reference');
  await modal.getByLabel('Название ссылки (необязательно)').fill('Примеры дизайна');
  await modal.getByRole('button',{name:'Добавить ссылку',exact:true}).click();
  assert.equal(await modal.getByRole('list',{name:'Добавляемые материалы'}).getByRole('listitem').count(),6);
  await modal.locator('.modal-body').evaluate(el=>{el.scrollTop=0;});
  await modal.getByLabel('Название',{exact:true}).focus();
  await noOverflow();
  await shot('12-new-project-materials.png');
  await modal.screenshot({path:path.join(output,'new-project-dialog.png')});
  await a11y('new project with files and reference');
  await modal.getByRole('button',{name:'Создать проект',exact:true}).click();
  await modal.waitFor({state:'hidden'});const id=await projectId();
  const saved=await materials(id);assert.equal(saved.filter(m=>m.attachment||m.source_url).length,6);
  assert.match(saved.find(m=>m.title==='ТЗ.docx').content,/запись онлайн/);
  assert.match(saved.find(m=>m.title==='brief.pdf').content,/booking and contacts/);
  assert.equal(saved.find(m=>m.title==='source.bin').attachment.extraction_status,'unsupported');
  check('New project stores PDF, Russian DOCX, photo, playable video, arbitrary binary and URL');

  await nav('База знаний');await page.getByRole('button',{name:/ТЗ.docx/}).click();
  const panel=page.getByRole('dialog',{name:'Материал проекта'});
  assert.match(await panel.locator('.markdown').innerText(),/Техническое задание/);
  assert.equal(await panel.getByRole('link',{name:'Скачать оригинал',exact:true}).count(),1);
  await a11y('document text and original download');
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:/photo.png/}).click();
  await panel.getByRole('img',{name:/Исходное изображение/}).waitFor();
  await page.waitForFunction(()=>{const img=document.querySelector('.material-image-preview');return img?.complete&&img.naturalWidth>0;});
  await a11y('image reference preview');await page.keyboard.press('Escape');
  await page.getByRole('button',{name:/reference.mp4/}).click();
  await page.waitForFunction(()=>{const video=document.querySelector('video');return video?.readyState>=1&&video.duration>0;});
  await panel.locator('video').evaluate(async video=>{await video.play();video.pause();});
  check('Original photo renders and MP4 is decoded by the actual browser');
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:/Примеры дизайна/}).click();
  assert.equal(await panel.getByRole('link',{name:/Открыть ссылку/}).getAttribute('rel'),'noopener noreferrer');
  assert.match(await panel.innerText(),/автоматически не загружено/);
  await page.keyboard.press('Escape');

  await nav('Настройки');
  await page.getByLabel('Файлы проекта',{exact:true}).setInputFiles(upload('later.txt','text/plain',Buffer.from('Дополнение: форма записи должна быть доступна с клавиатуры.')));
  await page.getByRole('button',{name:'Сохранить проект',exact:true}).click();
  await page.getByRole('list',{name:'Добавляемые материалы'}).getByText(/Сохранено/).waitFor();
  assert.ok((await materials(id)).some(m=>m.title==='later.txt'));
  await page.reload();await nav('Настройки');await page.getByRole('list',{name:'Сохранённые материалы'}).getByText('later.txt',{exact:true}).waitFor();
  await shot('13-project-settings-materials.png');await a11y('saved project settings');
  check('Files added later in settings persist across reload with the project context');

  await nav('База знаний');await page.getByRole('button',{name:'Добавить материал',exact:true}).click();
  const materialForm=page.getByRole('dialog',{name:'Добавить материал'});
  await materialForm.getByRole('button',{name:'Файлы и ссылки',exact:true}).click();
  await materialForm.getByLabel('Ссылка на ТЗ или материал').fill('https://example.com/final-brief');
  await materialForm.getByRole('button',{name:'Сохранить материалы',exact:true}).click();
  await materialForm.waitFor({state:'hidden'});
  assert.ok((await materials(id)).some(m=>m.source_url==='https://example.com/final-brief'));
  check('Knowledge upload form saves a typed URL even without a separate Add click');

  await page.getByRole('button',{name:'Добавить материал',exact:true}).click();
  await materialForm.getByLabel('Название',{exact:true}).fill('Несохранённая заметка');
  await materialForm.getByLabel('Содержание',{exact:true}).fill('Не потерять текст при сохранении файлов.');
  await materialForm.getByRole('button',{name:'Файлы и ссылки',exact:true}).click();
  await materialForm.getByLabel('Файлы проекта',{exact:true}).setInputFiles(upload('draft.txt','text/plain',Buffer.from('File saved before note')));
  await materialForm.getByRole('button',{name:'Сохранить материалы',exact:true}).click();
  await materialForm.getByText(/Текстовый черновик ещё не сохранён/).waitFor();
  assert.equal(await materialForm.getByLabel('Содержание').inputValue(),'Не потерять текст при сохранении файлов.');
  await materialForm.getByRole('button',{name:'Добавить материал',exact:true}).click();await materialForm.waitFor({state:'hidden'});
  assert.equal((await materials(id)).filter(m=>m.title==='Несохранённая заметка').length,1);
  assert.equal((await materials(id)).filter(m=>m.title==='draft.txt').length,1);
  check('Saving files preserves a pending text draft and completes both materials once');

  await page.getByRole('button',{name:'Добавить материал',exact:true}).click();
  await materialForm.getByLabel('Название',{exact:true}).fill('Заметка перед файлами');
  await materialForm.getByLabel('Содержание',{exact:true}).fill('Сначала сохранить заметку, затем файл.');
  await materialForm.getByRole('button',{name:'Файлы и ссылки',exact:true}).click();
  await materialForm.getByLabel('Файлы проекта',{exact:true}).setInputFiles(upload('after-note.txt','text/plain',Buffer.from('File retained after note')));
  await materialForm.getByRole('button',{name:'Текст',exact:true}).click();
  await materialForm.getByRole('button',{name:'Добавить материал',exact:true}).click();
  await materialForm.getByText(/Файлы и ссылки ещё не сохранены/).waitFor();
  await materialForm.getByRole('button',{name:'Сохранить материалы',exact:true}).click();await materialForm.waitFor({state:'hidden'});
  assert.equal((await materials(id)).filter(m=>m.title==='Заметка перед файлами').length,1);
  assert.equal((await materials(id)).filter(m=>m.title==='after-note.txt').length,1);
  check('Saving text preserves queued files and completes both materials once');
  await page.getByRole('button',{name:'Новая задача',exact:true}).click();
  const task=page.getByRole('dialog',{name:'Новая задача'});
  assert.equal(await task.getByRole('checkbox',{name:/ТЗ.docx/}).isChecked(),true);
  assert.equal(await task.getByRole('checkbox',{name:/brief.pdf/}).isChecked(),true);
  assert.match(await task.innerText(),/Текст извлечён/);
  check('Task creation exposes source attachment selection and extraction status');
  await page.keyboard.press('Escape');

  await nav('Настройки');await page.getByRole('button',{name:'Создать другой проект'}).click();
  await modal.getByLabel('Название',{exact:true}).fill('Проверка повторной загрузки');
  let creates=0;const countCreates=request=>{if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/projects')creates++;};
  page.on('request',countCreates);
  await modal.getByLabel('Файлы проекта',{exact:true}).setInputFiles([upload('kept.txt','text/plain',Buffer.from('Saved first')),upload('retry.txt','text/plain',Buffer.from('Saved after retry'))]);
  let injected=false;
  await page.route('**/api/projects/*/materials/upload?filename=retry.txt',async route=>{if(!injected){injected=true;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Проверка: временный сбой загрузки'})});}else await route.continue();});
  await modal.getByRole('button',{name:'Создать проект',exact:true}).click();
  await modal.getByRole('button',{name:'Повторить добавление',exact:true}).waitFor();
  await modal.getByText(/Не добавлено: 1/).waitFor();
  await a11y('partial upload with clear recovery');
  await modal.getByRole('button',{name:'Отмена',exact:true}).click();
  await modal.getByRole('button',{name:'Продолжить добавление',exact:true}).click();
  await modal.getByRole('button',{name:'Повторить добавление',exact:true}).click();
  await modal.waitFor({state:'hidden'});page.off('request',countCreates);
  const retryId=await projectId();assert.equal(creates,1);
  const retryMaterials=await materials(retryId);
  assert.equal(retryMaterials.filter(m=>m.title==='kept.txt').length,1);
  assert.equal(retryMaterials.filter(m=>m.title==='retry.txt').length,1);
  check('Partial upload recovers without duplicate project or already saved file; close warns');

  await nav('Настройки');await page.getByRole('button',{name:'Создать другой проект'}).click();
  await modal.getByLabel('Название',{exact:true}).fill('Проверка размера');
  const oversizedPath=path.join(fixtures,'oversized.bin');
  const oversized=await open(oversizedPath,'w');await oversized.truncate(50*1024*1024+1);await oversized.close();
  await modal.getByLabel('Файлы проекта',{exact:true}).setInputFiles(oversizedPath);
  assert.equal(await modal.getByRole('button',{name:'Создать проект',exact:true}).isDisabled(),true);
  assert.match(await modal.innerText(),/Файл больше 50 МБ/);
  await modal.getByRole('button',{name:'Убрать файл oversized.bin',exact:true}).click();
  assert.equal(await modal.getByRole('button',{name:'Создать проект',exact:true}).isEnabled(),true);
  check('Client limit explains oversize file and allows removal before project creation');
  await page.setViewportSize({width:320,height:740});await noOverflow();
  await a11y('new project at 320 pixels');
  await modal.getByLabel('Название',{exact:true}).focus();
  await page.screenshot({path:path.join(output,'14-new-project-mobile.png'),fullPage:false});
  await page.keyboard.press('Escape');await noOverflow();await a11y('settings at 320 pixels');
  check('Creation and settings fit 320px and retain keyboard-accessible controls');
  assert.deepEqual(report.errors,[]);report.status='passed';
} catch(error) {
  report.status='failed';report.failure=error.stack;
  await page.screenshot({path:path.join(output,'attachments-failure.png'),fullPage:true});
  console.error(error);process.exitCode=1;
} finally {
  await writeFile(path.join(output,'attachments-report.json'),JSON.stringify(report,null,2));
  await browser.close();console.log(JSON.stringify({status:report.status,checks:report.checks.length}));
}
