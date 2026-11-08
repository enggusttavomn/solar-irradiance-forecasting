/* New reproduction helper; this is not presented as a preserved historical command.
   Rasterizes existing SVG files without running any report builder or model. */
'use strict';
const fs = require('fs');
const path = require('path');

async function main() {
  const args = process.argv.slice(2);
  if (!args.length || args.includes('--help')) {
    console.log('node rasterizar_svg_relatorio.cjs --input FILE_OR_DIR --out-dir DIR [--width 3000] [--density 180] [--sharp-module PATH] [--overwrite]');
    return;
  }
  const options = {};
  for (let i=0; i<args.length; i++) {
    if (args[i] === '--overwrite') { options.overwrite = true; continue; }
    if (!args[i].startsWith('--') || i+1 >= args.length) throw new Error('Invalid argument: '+args[i]);
    options[args[i].slice(2)] = args[++i];
  }
  if (!options.input || !options['out-dir']) throw new Error('--input and --out-dir are required.');
  const width = Number(options.width || 3000), density = Number(options.density || 180);
  if (!Number.isInteger(width) || width<1 || !Number.isFinite(density) || density<1) throw new Error('Invalid width/density.');
  const sharp = require(options['sharp-module'] || 'sharp');
  const source = path.resolve(options.input), output = path.resolve(options['out-dir']);
  const files = fs.statSync(source).isDirectory()
    ? fs.readdirSync(source).filter(n=>n.toLowerCase().endsWith('.svg')).sort().map(n=>path.join(source,n))
    : [source];
  if (!files.length || files.some(f=>!f.toLowerCase().endsWith('.svg'))) throw new Error('Input must contain SVG files.');
  fs.mkdirSync(output,{recursive:true});
  const results = [];
  for (const file of files) {
    const target = path.join(output,path.basename(file).replace(/\.svg$/i,'.png'));
    if (fs.existsSync(target) && !options.overwrite) throw new Error('Output exists; choose another directory or --overwrite: '+target);
    await sharp(file,{density}).resize({width}).png().toFile(target);
    const info = await sharp(target).metadata();
    results.push({source:file,output:target,width:info.width,height:info.height,density});
  }
  console.log(JSON.stringify({helper:'new_reproduction_utility',sharp:sharp.versions.sharp,results},null,2));
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
