const path=require('path');
const sharp=require('C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
(async()=>{await sharp(path.join(__dirname,'perfis_sete_dias_artigo_referencia.svg'),{density:180}).png().toFile(path.join(__dirname,'perfis_sete_dias_artigo_referencia.png'));console.log('reference profiles rendered');})().catch(e=>{console.error(e);process.exit(1)});
