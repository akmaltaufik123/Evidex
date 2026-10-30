/* Hallmark · macrostructure: guided-workbench · theme: paper-ink · genre: modern-minimal
 * pre-emit critique: P4 H4 E4 S5 R5 V4 · slop test: pass (hosted UI sweep)
 */
'use strict';
// Keep the existing form and job flow; server filesystem actions become downloads.
async function hostedDownload(kind){
  const name=$('saved-case').value;
  if(!name||jobBusy)return;
  const response=await fetch('/api/download?case='+encodeURIComponent(name)+'&kind='+kind,{headers:{'X-Evidex-Token':token}});
  if(!response.ok)throw new Error(t('requestError'));
  const object=URL.createObjectURL(await response.blob()),link=document.createElement('a');
  link.href=object;link.download=name+(kind==='excel'?'.xlsx':'.zip');link.click();setTimeout(()=>URL.revokeObjectURL(object),5000);
}
const oldFolder=$('open-folder'),downloadButton=oldFolder.cloneNode(true);
oldFolder.replaceWith(downloadButton); // Remove the localhost opener listener.
downloadButton.addEventListener('click',()=>hostedDownload('zip').catch(error=>showError(error,'folder-notice')));
const excelButton=document.createElement('button');excelButton.type='button';excelButton.className='secondary';excelButton.id='download-excel';excelButton.textContent='Excel';
downloadButton.insertAdjacentElement('afterend',excelButton);
excelButton.addEventListener('click',()=>hostedDownload('excel').catch(error=>showError(error,'folder-notice')));
const localSelection=selectedResult;
selectedResult=function(){localSelection();excelButton.disabled=jobBusy||!$('saved-case').value};
selectedResult();
// The public instance explains server processing and storage before starting.
const consent=document.createElement('label');consent.className='check';
const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.id='server-consent';
const consentText=document.createElement('span');consentText.id='server-consent-text';
consent.append(checkbox,consentText);$('authorized').closest('label').insertAdjacentElement('afterend',consent);
const originalStart=start;
start=async function(mode){
  if(!checkbox.checked){$('notice').textContent=language==='ms'?'Tandakan persetujuan pemprosesan server pada langkah semakan.':'Confirm server processing consent in the review step.';return}
  return originalStart(mode);
};
// Transport checks send API details too: consent must be available on step 1.
$('fields').prepend(consent);
const originalProfile=profile;
profile=function(mode){return {...originalProfile(mode),server_consent:checkbox.checked}};
const limitNote=document.createElement('p');limitNote.className='hint';consent.insertAdjacentElement('afterend',limitNote);
function hostedLanguage(){limitNote.textContent=language==='ms'?'Had web beta: 5000 mesej, 16 MiB setiap media, 64 MiB media setiap kerja. Kerja dihentikan selepas 15 minit; semak laporan untuk hasil separa.':'Web beta limits: 5000 messages, 16 MiB per media file, 64 MiB media per job. Jobs stop after 15 minutes; check the report for partial results.';consentText.textContent=language==='ms'?'Saya faham API, sesi Telegram dan bukti diproses serta disimpan pada server ATE. Saya akan muat turun salinan sendiri.':'I understand that API details, Telegram sessions and evidence are processed and stored on the ATE server. I will download my own copy.'}
$('language').addEventListener('change',hostedLanguage);hostedLanguage();
