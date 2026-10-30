// Execute the actual UI script with a minimal DOM; no runtime app dependency.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element{
  constructor(){this.children=[];this.value='';this.dataset={};this.style={};this.listeners={};this.textContent='';this.hidden=false;this.disabled=false;this.open=false;this.checked=false;}
  addEventListener(name,callback){this.listeners[name]=callback}
  replaceChildren(){this.children=[];this.value='';this.textContent=''}
  append(...items){for(const child of items){this.children.push(child);if(this.children.length===1)this.value=child.value}}
  get selectedOptions(){return this.children.filter(child=>child.value===this.value)}
  focus(){}showModal(){this.open=true}close(){this.open=false}scrollIntoView(){}click(){return this.listeners.click?.()}
}
(async()=>{
  const root=path.join(__dirname,'..'),html=fs.readFileSync(path.join(root,'evidex_next.html'),'utf8'),copy=JSON.parse(fs.readFileSync(path.join(root,'evidex_next_content.json'),'utf8'));
  assert.deepEqual(Object.keys(copy.en).sort(),Object.keys(copy.ms).sort());
  assert.equal(copy.guide.length,6);
  for(const page of copy.guide){assert.equal(page.en.steps.length,page.ms.steps.length);assert(fs.statSync(path.join(root,'guide_assets',page.image)).size>1000)}
  const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
  get('i18n').textContent=JSON.stringify(copy);
  const panels=[1,2,3,4,5].map(n=>{const e=new Element();e.dataset.step=String(n);return e});
  const translations=[...html.matchAll(/data-i18n="([^"]+)"/g)].map(match=>{assert(copy.en[match[1]]);const e=new Element();e.dataset.i18n=match[1];return e});
  const document={title:'',documentElement:{lang:'en'},getElementById:get,createElement(){return new Element()},querySelector(){return get('media-checkbox')},querySelectorAll(selector){return selector==='.wizard-step'?panels:selector==='[data-i18n]'?translations:[]}};
  const stored=new Map([['evidex-language','en']]);
  const base={stage:'idle',busy:false,prompt:null,messages:0,media:0,output:null,error:null,logs:[]};
  const cases=[{name:'EVIDEX_existing',path:'/home/user/evidence_exports/EVIDEX_existing',status:'complete'}];
  let lastRequest;
  const context=vm.createContext({document,console,setInterval(){},localStorage:{getItem:key=>stored.get(key),setItem:(key,value)=>stored.set(key,value)},fetch:async(url,options)=>{
    lastRequest={url,options};return{ok:true,json:async()=>url.startsWith('/api/results')?{cases}:url.startsWith('/api/messages')?{messages:[{message_id:1,text:'<script>not executable</script>',sender_id:7}],more:false}:url.endsWith('state')?base:{path:cases[0].path}};
  }});
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  await new Promise(resolve=>setImmediate(resolve));
  const render=state=>vm.runInContext(`renderState(${JSON.stringify({...base,...state})})`,context);
  render({stage:'complete',messages:4174,media:578,output:cases[0].path});
  assert.equal(get('completion').hidden,false);assert.match(get('completion-summary').textContent,/4,174 messages and 578 media files/);assert.match(document.title,/Finished/);
  for(const stage of ['transport_passed','failed','cancelled','acquiring']){render({stage});assert.equal(get('completion').hidden,true)}
  render({stage:'complete',busy:true});assert.equal(get('completion').hidden,true);assert.equal(get('open-folder').disabled,true);
  render({stage:'idle'});await vm.runInContext('refreshResults()',context);assert.equal(get('saved-case').value,'EVIDEX_existing');
  await get('open-folder').listeners.click();assert.equal(lastRequest.url,'/api/open-folder');assert.deepEqual(JSON.parse(lastRequest.options.body),{case:'EVIDEX_existing'});
  assert.match(get('folder-notice').textContent,/Folder open request sent/);
  await get('guide-open').listeners.click();assert.equal(get('guide-dialog').open,true);assert.match(get('guide-title').textContent,/developer portal/);
  for(let n=1;n<6;n++)get('guide-next').listeners.click();assert.match(get('guide-title').textContent,/Read and preserve/);get('guide-next').listeners.click();assert.equal(get('guide-dialog').open,false);
  get('language').value='ms';get('language').listeners.change();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(document.documentElement.lang,'ms');assert.match(get('step-name').textContent,/Sambungkan Telegram/);
  render({stage:'complete',messages:4174,media:578});assert.match(get('completion-summary').textContent,/mesej dan/);assert.match(get('stage').textContent,/Selesai/);
  assert.equal(stored.size,1);assert.equal(stored.get('evidex-language'),'ms');
  // Invalid data cannot advance the wizard. Switching languages preserves fields.
  get('wizard-next').listeners.click();assert.match(get('notice').textContent,/Semak/);
  get('api_id').value='123';get('api_hash').value='a'.repeat(32);get('wizard-next').listeners.click();assert.match(get('step-name').textContent,/Pilih sumber/);
  get('phone').value='+60123456789';get('target').value='@example';get('wizard-next').listeners.click();assert.match(get('step-name').textContent,/Pilih kandungan/);
  get('wizard-next').listeners.click();assert.match(get('step-name').textContent,/Semak dan mulakan/);assert(!get('review').textContent.includes('a'.repeat(32)));
  get('language').value='en';get('language').listeners.change();await new Promise(resolve=>setImmediate(resolve));assert.equal(get('api_hash').value,'a'.repeat(32));
  await get('view-messages').listeners.click();await new Promise(resolve=>setImmediate(resolve));assert.equal(get('viewer-dialog').open,true);
  assert.equal(get('message-list').children[0].children[1].textContent,'<script>not executable</script>');
  assert.equal(get('agency-contacts').children.length,4);
  assert.equal(get('bank-contacts').children.length,17);
  const directory=JSON.stringify(copy.contacts);
  assert(directory.includes('aduanskmm@mcmc.gov.my'));
  assert(directory.includes('cyber999@cybersecurity.my'));
  assert(!directory.includes('mailto:')&&!directory.includes('?body='));
  assert(!html.includes('window.confirm'));
  let confirmation=vm.runInContext("confirmAction('delete','<case-name>')",context);
  assert.equal(get('confirm-dialog').open,true);
  assert.equal(get('confirm-case').textContent,'<case-name>');
  get('confirm-cancel').listeners.click();assert.equal(await confirmation,false);
  confirmation=vm.runInContext("confirmAction('history')",context);
  assert.equal(get('confirm-case').hidden,true);
  get('confirm-accept').listeners.click();assert.equal(await confirmation,true);
  confirmation=vm.runInContext("confirmAction('delete','case')",context);
  get('confirm-dialog').listeners.cancel({preventDefault(){}});assert.equal(await confirmation,false);
  console.log('PASS: completion, folder action, both languages, six illustrated guide pages, wizard validation, credential preservation and text-only message viewer');
})().catch(error=>{console.error(error);process.exitCode=1});
