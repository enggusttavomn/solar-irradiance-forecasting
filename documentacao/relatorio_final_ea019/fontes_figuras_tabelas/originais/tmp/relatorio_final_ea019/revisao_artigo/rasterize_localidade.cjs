const path=require('path');
const sharp=require('C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
(async()=>{
  const file=path.join(__dirname,'11_mae_localidades.svg');
  await sharp(file,{density:160}).png().toFile(path.join(__dirname,'11_mae_localidades.png'));
  console.log('11_mae_localidades.png');
})().catch(e=>{console.error(e);process.exit(1)});
