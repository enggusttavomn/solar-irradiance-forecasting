const fs=require('fs');
const path=require('path');
const sharp=require('C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
(async()=>{
  const dir=path.join(__dirname,'figuras');
  for(const name of fs.readdirSync(dir).filter(s=>s.endsWith('.svg')))
    await sharp(path.join(dir,name),{density:180}).png().toFile(path.join(dir,name.replace('.svg','.png')));
  console.log('Figuras metodológicas e séries de referência renderizadas.');
})().catch(e=>{console.error(e);process.exit(1)});
