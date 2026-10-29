/* Hallmark · macrostructure: guided-workbench · theme: paper-ink · genre: modern-minimal
 * pre-emit critique: P4 H4 E4 S5 R5 V4 · slop test: rendered assertions below
 */
// QA-only dependencies: npm install --prefix ../browser-qa @sparticuz/chromium puppeteer-core
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),scratch=path.resolve(root,'..');
const qaRequire=require('node:module').createRequire(path.join(scratch,'browser-qa/package.json'));
const chromiumModule=qaRequire('@sparticuz/chromium');
const chromium=chromiumModule.default||chromiumModule;
let playwrightModule;try{playwrightModule=require('playwright')}catch{playwrightModule=qaRequire('playwright')}
const {chromium:playwright}=playwrightModule;
const out=path.join(scratch,'design-qa');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const server=spawn('python',['tests/serve_design_fixture.py'],{cwd:root,stdio:['ignore','pipe','pipe']});let stderr='';server.stderr.on('data',b=>stderr+=b);
 let browser;
 try{
  let ready=false;for(let i=0;i<80;i++){try{if((await fetch('http://127.0.0.1:8794')).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,100))}if(!ready)throw Error('Fixture failed: '+stderr);
  // Extract QA binaries without ownership changes (managed Linux namespaces).
  const bin=path.resolve(path.dirname(qaRequire.resolve('@sparticuz/chromium')),'../bin');
  const extracted=path.join(scratch,'browser-qa/extracted');fs.mkdirSync(extracted,{recursive:true});
  const {pipeline}=require('node:stream/promises'),{createBrotliDecompress}=require('node:zlib');
  const executablePath=path.join(extracted,'chromium');
  if(!fs.existsSync(path.join(extracted,'.ready'))){
   await pipeline(fs.createReadStream(path.join(bin,'chromium.br')),createBrotliDecompress(),fs.createWriteStream(executablePath,{mode:0o755}));
   for(const name of ['fonts','swiftshader','al2023']){
    const target=name==='swiftshader'?extracted:path.join(extracted,name);fs.mkdirSync(target,{recursive:true});
    await pipeline(fs.createReadStream(path.join(bin,name+'.tar.br')),createBrotliDecompress(),qaRequire('tar-fs').extract(target,{chown:false}));
   }
   fs.writeFileSync(path.join(extracted,'.ready'),'complete');
  }
  fs.writeFileSync(path.join(extracted,'fonts','fonts.conf'),`<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include><dir>${path.join(extracted,'fonts/fonts')}</dir><dir>/usr/share/fonts</dir><dir>/usr/local/share/fonts</dir><cachedir>${path.join(extracted,'font-cache')}</cachedir></fontconfig>`);
  process.env.FONTCONFIG_PATH=path.join(extracted,'fonts');
  process.env.LD_LIBRARY_PATH=extracted+':'+path.join(extracted,'al2023/lib')+':'+(process.env.LD_LIBRARY_PATH||'');
  browser=await playwright.launch({headless:true,executablePath,args:chromium.args});
  const findings=[],pageErrors=[];
  async function audit(page,label,width){
   const issues=await page.evaluate(()=>{
    const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
    const issues=[];
    if(document.documentElement.scrollWidth>innerWidth+1)issues.push('root horizontal overflow');
    for(const el of document.querySelectorAll('body *')){
     if(!visible(el)||el.closest('dialog:not([open])'))continue;
     const r=el.getBoundingClientRect();if(r.left< -1||r.right>innerWidth+1)issues.push('outside viewport: '+(el.id||el.tagName));
    }
    for(const el of document.querySelectorAll('button,a,summary')){
     if(!visible(el))continue;
     const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),rects=[];let node;
     while(node=walker.nextNode()){if(!node.textContent.trim())continue;const range=document.createRange();range.selectNodeContents(node);rects.push(...range.getClientRects())}
     const tops=rects.filter(r=>r.width>0).map(r=>r.top),line=parseFloat(getComputedStyle(el).lineHeight)||20;
     if(tops.length&&Math.max(...tops)-Math.min(...tops)>line*.55)issues.push('wrapped control: '+(el.id||el.textContent));
     const r=el.getBoundingClientRect();if(rects.some(t=>t.right>r.right+1||t.left<r.left-1))issues.push('clipped control: '+(el.id||el.textContent));
    }
    return [...new Set(issues)];
   });
   if(issues.length)findings.push({label,width,issues});
  }
  const page=await browser.newPage({viewport:{width:1280,height:900}});page.on('pageerror',e=>pageErrors.push(e.message));
  for(const language of ['ms','en'])for(const width of [320,375,414,768,1280]){
   console.log('Rendering',language,width);await page.setViewportSize({width,height:900});
   await page.goto('http://127.0.0.1:8794');await page.selectOption('#language',language);await page.waitForFunction(()=>document.getElementById('saved-case').value);
   await audit(page,language+'/connect',width);
   await page.fill('#api_id','1');await page.fill('#api_hash','a'.repeat(32));
   await page.click('#wizard-next');await page.fill('#phone','+10000000000');await page.fill('#target','@sample_fixture');await audit(page,language+'/source',width);
   await page.click('#wizard-next');await page.locator('input[name=media]').uncheck();await audit(page,language+'/content',width);
   await page.click('#wizard-next');await page.check('#authorized');await audit(page,language+'/review',width);
   await page.click('#start');await page.locator('#prompt').waitFor({state:'visible'});await audit(page,language+'/login',width);
   await page.fill('#answer','12345');await page.locator('#prompt button').click();await page.waitForFunction(()=>document.getElementById('promptlabel').textContent.includes('password')||document.getElementById('promptlabel').textContent.includes('dua faktor'));
   await page.fill('#answer','fixture-password');await page.locator('#prompt button').click();await page.waitForFunction(()=>!document.getElementById('completion').hidden);await audit(page,language+'/complete',width);
   if(width===1280||width===375)await page.screenshot({path:path.join(out,`${language}-${width}-workspace.png`),fullPage:true});
   await page.click('#view-messages');await page.locator('#message-list .message').waitFor();await audit(page,language+'/viewer',width);await page.click('#viewer-close');
   await page.click('#guide-open');for(let step=0;step<6;step++){await page.waitForFunction(()=>{const i=document.getElementById('guide-image');return i.complete&&i.naturalWidth>0});await audit(page,language+'/guide'+(step+1),width);const title=await page.locator('#guide-title').boundingBox(),dialog=await page.locator('#guide-dialog').boundingBox();assert(title.y>=dialog.y,'Guide heading scrolled out of view');if(step<5)await page.click('#guide-next')}
   if(width===375)await page.screenshot({path:path.join(out,`${language}-${width}-guide.png`),fullPage:true});
   await page.click('#guide-next');
   // Language changes are not a navigation action and must not move the page.
   await page.evaluate(()=>window.scrollTo(0,200));const before=await page.evaluate(()=>scrollY);
   await page.evaluate(()=>{const el=document.getElementById('language');el.value=el.value==='en'?'ms':'en';el.dispatchEvent(new Event('change'))});await page.waitForTimeout(100);
   const after=await page.evaluate(()=>scrollY);if(Math.abs(before-after)>2)findings.push({label:'language-scroll',language,width,before,after});

  }
  fs.writeFileSync(path.join(out,'responsive-report.json'),JSON.stringify({widths:[320,375,414,768,1280],languages:['ms','en'],findings,pageErrors},null,2));
  console.log(JSON.stringify({findings,pageErrors}));
  assert.deepEqual(findings,[]);assert.deepEqual(pageErrors,[]);
  // Run the upstream mechanical checker too; its HTML-only source scan is separate
  // from these application-state assertions.
  const skill=path.resolve(root,'../../hallmark-design-reference/skills/hallmark/scripts/sloplint.mjs');
  if(fs.existsSync(skill)){
   const wrapper=path.join(out,'chrome-wrapper.sh');fs.writeFileSync(wrapper,'#!/bin/sh\nexec "$EVIDEX_QA_CHROME" --no-sandbox --disable-setuid-sandbox "$@"\n',{mode:0o755});
   const lint=spawnSync('node',[skill,'evidex_next.html','evidex_next.css','--scope','app','--genre','modern-minimal','--tier','floor'],{cwd:root,env:{...process.env,CHROME_PATH:wrapper,EVIDEX_QA_CHROME:executablePath,NODE_PATH:path.join(scratch,'browser-qa/node_modules'),HALLMARK_PUPPETEER:path.join(scratch,'browser-qa')},encoding:'utf8',timeout:120000});
   const rendered=spawnSync('node',[skill,'--scope','app','--genre','modern-minimal','--tier','floor','--render','--url','http://127.0.0.1:8794'],{cwd:root,env:{...process.env,CHROME_PATH:wrapper,EVIDEX_QA_CHROME:executablePath,HALLMARK_PUPPETEER:path.join(scratch,'browser-qa')},encoding:'utf8',timeout:120000});
   fs.writeFileSync(path.join(out,'sloplint.log'),(lint.stdout||'')+(lint.stderr||'')+(rendered.stdout||'')+(rendered.stderr||''));console.log('Upstream sloplint exits:',lint.status,rendered.status);
   assert.equal(lint.status,0);assert.equal(rendered.status,0);
  }
 }finally{if(browser)await browser.close();server.kill('SIGINT')}
})().catch(error=>{console.error(error);process.exitCode=1});
