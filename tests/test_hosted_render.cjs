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
const out=path.join(scratch,'hosted-qa');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const server=spawn('python',['tests/serve_hosted_fixture.py'],{cwd:root,stdio:['ignore','pipe','pipe']});let stderr='';server.stderr.on('data',b=>stderr+=b);
 let browser;
 try{
  let ready=false;for(let i=0;i<80;i++){try{if((await fetch('http://127.0.0.1:8795')).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,100))}if(!ready)throw Error('Fixture failed: '+stderr);
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
  const failures=[],errors=[];const context=await browser.newContext();const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  for(const lang of ['ms','en'])for(const width of [320,375,414,768,1280]){
    await context.clearCookies();
    await page.setViewportSize({width,height:1000});await page.goto('http://127.0.0.1:8795');await page.selectOption('#language',lang);
    await page.locator('#server-consent').waitFor();await page.check('#server-consent');
    await page.fill('#api_id','1');await page.fill('#api_hash','a'.repeat(32));
    await page.click('#wizard-next');await page.fill('#phone','+10000000000');await page.fill('#target','@sample_fixture');
    await page.click('#wizard-next');await page.locator('input[name=media]').uncheck();await page.click('#wizard-next');await page.check('#authorized');await page.click('#start');
    await page.waitForFunction(()=>!document.getElementById('completion').hidden);
    await page.waitForFunction(()=>document.getElementById('saved-case').value);
    for(const selector of ['#open-folder','#download-excel']){
      const pending=page.waitForEvent('download');await page.click(selector);const download=await pending;
      if(!download.suggestedFilename().endsWith(selector==='#open-folder'?'.zip':'.xlsx'))failures.push('bad download filename');
    }
    if(await page.locator('#session').count())failures.push('server session path exposed');
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)failures.push(lang+width+' overflow');
    if(lang==='ms'&&width===1280)await page.screenshot({path:path.join(out,'hosted-workspace.png'),fullPage:true});
    console.log('Hosted OK',lang,width);
  }
  await context.clearCookies();await page.goto('http://127.0.0.1:8795');await page.waitForFunction(()=>document.getElementById('saved-case').options.length>0);assert.equal(await page.locator('#saved-case').inputValue(),'');
  console.log(JSON.stringify({failures,errors}));assert.equal(failures.length+errors.length,0);
 }finally{if(browser)await browser.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
