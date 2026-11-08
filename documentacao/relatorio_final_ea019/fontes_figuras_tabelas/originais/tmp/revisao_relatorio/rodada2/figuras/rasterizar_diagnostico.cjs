const sharp = require("C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp");
const fs = require('fs');
const svg = fs.readFileSync(process.argv[2], 'utf8').replace('width="17cm" height="10.3cm"', 'width="3012" height="1825"');
sharp(Buffer.from(svg), {density:72}).resize({width:3012,height:1825}).flatten({background:'#ffffff'}).png().withMetadata({density:450}).toFile(process.argv[3]).then(info => console.log(JSON.stringify(info))).catch(error => { console.error(error); process.exit(1); });
