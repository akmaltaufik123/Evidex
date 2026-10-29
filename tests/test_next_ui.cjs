// Exercise the actual browser script without third-party DOM dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
  constructor(){this.children=[];this.value='';this.dataset={};this.listeners={};this.textContent='';this.hidden=false;this.disabled=false;}
  addEventListener(name, callback){this.listeners[name]=callback;}
  replaceChildren(){this.children=[];this.value='';}
  append(child){this.children.push(child);if(this.children.length===1)this.value=child.value;}
  get selectedOptions(){return this.children.filter(child=>child.value===this.value);}
  focus(){}
}
(async()=>{
  const elements=new Map();
  const document={title:'',getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id)},createElement(){return new Element()}};
  const base={stage:'idle',busy:false,prompt:null,messages:0,media:0,output:null,error:null,logs:[]};
  const cases=[{name:'EVIDEX_existing',path:'/home/user/evidence_exports/EVIDEX_existing',status:'complete'}];
  let lastRequest;
  const context=vm.createContext({document,console,setInterval(){},fetch:async(url,options)=>{
    lastRequest={url,options};
    return {ok:true,json:async()=>url.endsWith('results')?{cases}:url.endsWith('state')?base:{path:cases[0].path}};
  }});
  const html=fs.readFileSync(path.join(__dirname,'../evidex_next.html'),'utf8');
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  await new Promise(resolve=>setImmediate(resolve));
  const render=state=>vm.runInContext(`renderState(${JSON.stringify({...base,...state})})`,context);
  render({stage:'complete',messages:4174,media:578,output:cases[0].path});
  assert.equal(elements.get('completion').hidden,false);
  assert.match(elements.get('completion-summary').textContent,/4,174 messages and 578 media files/);
  assert.match(document.title,/Extraction complete/);
  for(const stage of ['transport_passed','failed','cancelled','acquiring']){
    render({stage});assert.equal(elements.get('completion').hidden,true);
  }
  render({stage:'complete',busy:true});
  assert.equal(elements.get('completion').hidden,true);
  assert.equal(elements.get('open-folder').disabled,true);
  render({stage:'idle'});
  await vm.runInContext('refreshResults()',context);
  assert.equal(elements.get('saved-case').value,'EVIDEX_existing');
  assert.equal(elements.get('open-folder').disabled,false);
  await elements.get('open-folder').listeners.click();
  assert.equal(lastRequest.url,'/api/open-folder');
  assert.deepEqual(JSON.parse(lastRequest.options.body),{case:'EVIDEX_existing'});
  assert.match(elements.get('folder-notice').textContent,/Folder open request sent/);
  console.log('PASS: completion notice, counts, title, saved cases, folder click and busy-state controls');
})().catch(error=>{console.error(error);process.exitCode=1;});
