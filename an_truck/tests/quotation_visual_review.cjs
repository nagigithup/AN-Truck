// Inspect generated reference-preview HTML; no site records are written.
const {chromium}=require(process.env.PORTAL_PLAYWRIGHT_PATH || 'playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const root=process.argv[2] || '/tmp/anyuan-quotation-review';
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1000,height:1200}});
 const reports=[];
 try{
  await page.goto('http://dev.localhost:8000/login');
  await page.emulateMedia({media:'print'});
  for(const model of ['h7-pro','dongfeng']){
   await page.setContent(fs.readFileSync(`${root}/${model}.html`,'utf8'),{waitUntil:'networkidle'});
   await page.evaluate(()=>document.fonts.ready);
   await page.waitForFunction(()=>Array.from(document.images).every(img=>img.complete));
   const result=await page.evaluate(()=>{
    const bounds=el=>{const r=el.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height};};
    const pages=Array.from(document.querySelectorAll('.anyuan-quotation .qpage'));
    const errors=[];
    for(const [index,p] of pages.entries()){
     const box=bounds(p), footer=p.querySelector('.footer,.foot2'), foot=bounds(footer);
     for(const el of p.querySelectorAll('.hero,.info,.product,.cab,.lower,.sign,.specgrid,.badges,.cabshow')){
      const r=bounds(el);
      if(r.left<box.left-1||r.right>box.right+1||r.bottom>foot.top+1)errors.push(`page ${index+1}: ${el.className} exceeds page content`);
     }
     for(const el of p.querySelectorAll('.print-value,.warrcol,.specbox td,.q-badge b')){
      if(el.scrollHeight>el.clientHeight+2||el.scrollWidth>el.clientWidth+2)errors.push(`page ${index+1}: clipped text in ${el.className}`);
     }
     for(const el of p.querySelectorAll('.specbox')){
      if(bounds(el.querySelector('table')).bottom>bounds(el).bottom+2)errors.push(`page ${index+1}: table exceeds specification card`);
     }
     for(const el of p.querySelectorAll('.terms .body > *')){
      if(bounds(el).bottom>bounds(p.querySelector('.terms')).bottom+1)errors.push(`page ${index+1}: terms exceed card`);
     }
    }
    return {pages:pages.length,errors,brokenImages:Array.from(document.querySelectorAll('.anyuan-quotation img')).filter(img=>!img.naturalWidth).length,
     sections:pages.map(p=>Array.from(p.querySelectorAll(':scope>.header,:scope>.hero,:scope>.info,:scope>.product,:scope>.cab,:scope>.lower,:scope>.sign,:scope>.headspec,:scope>.specgrid,:scope>.footer,:scope>.foot2')).map(el=>({name:el.className,...bounds(el),top:bounds(el).top-bounds(p).top}))) };
   });
   for(const [i,sheet] of (await page.locator('.anyuan-quotation .qpage').all()).entries())await sheet.screenshot({path:`${root}/${model}-browser-${i+1}.png`});
   reports.push({model,...result});
   assert.equal(result.pages,2,`${model}: two original sheets expected`);
   assert.equal(result.brokenImages,0);
   assert.deepEqual(result.errors,[],model);
  }
 }finally{fs.writeFileSync(`${root}/visual-checks.json`,JSON.stringify(reports,null,2));await browser.close();}
 console.log(JSON.stringify(reports.map(({sections,...result})=>result)));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
