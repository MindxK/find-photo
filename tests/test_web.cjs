const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web/app.js','utf8').split("document.addEventListener('change'")[0];
function app(){
  const context=vm.createContext({URLSearchParams,URL,console,setTimeout,document:{querySelector:()=>null,addEventListener:(name,handler)=>{context.click=handler;}}});
  vm.runInContext(source,context);
  vm.runInContext(`state.selectedProfile='p';state.results={total:49,offset:0,limit:24,items:[]};state.resultQuery={profile_id:'p',threshold:'0.65',mode:'confirmed',source_id:'album'};`,context);
  return context;
}
test('first and last page buttons navigate directly and disable at boundaries',async()=>{
  const c=app();
  vm.runInContext('runSearch=async()=>{state.results.offset=state.offset;};',c);
  assert.match(vm.runInContext('resultsContent()',c),/data-action="first-page" disabled/);
  async function click(action){const button={dataset:{action},disabled:false,innerHTML:'',closest:()=>null};await c.click({target:{closest:()=>button},preventDefault(){}});}
  await click('last-page');
  assert.equal(vm.runInContext('state.offset',c),48);
  assert.match(vm.runInContext('resultsContent()',c),/data-action="last-page" disabled/);
  await click('first-page');
  assert.equal(vm.runInContext('state.offset',c),0);
});
test('download ZIP link preserves displayed filters even if controls change',()=>{
  const c=app();vm.runInContext("state.threshold=0.3;state.mode='all';",c);
  const html=vm.runInContext('resultsContent()',c);
  const href=html.match(/href="([^"]+search\/download[^"]+)"/)[1].replaceAll('&amp;','&');
  const url=new URL(href,'http://localhost');
  assert.equal(url.searchParams.get('threshold'),'0.65');
  assert.equal(url.searchParams.get('mode'),'confirmed');
  assert.equal(url.searchParams.get('source_id'),'album');
  assert.equal(url.searchParams.has('offset'),false);
});
test('search adopts server-clamped offset and hides controls for empty results',async()=>{
  const c=app();
  vm.runInContext("api=async()=>({total:25,offset:24,limit:24,items:[]});state.offset=48;",c);
  await vm.runInContext('runSearch(false)',c);
  assert.equal(vm.runInContext('state.offset',c),24);
  vm.runInContext('state.results={total:0,offset:0,limit:24,items:[]};',c);
  assert.doesNotMatch(vm.runInContext('resultsContent()',c),/search\/download|last-page/);
});
