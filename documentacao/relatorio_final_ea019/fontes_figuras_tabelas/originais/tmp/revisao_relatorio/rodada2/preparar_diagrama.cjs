const fs = require('fs');
const path = require('path');
const sharp = require('C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
(async () => {
  const source = path.resolve(__dirname, '../../relatorio_final_ea019/revisao_artigo/figuras/03_arquiteturas.svg');
  // The SVG is a code-native asset; only the spelling is standardized.
  const target = path.join(__dirname, 'figuras/arquiteturas_corrigidas.svg');
  const svg = fs.readFileSync(source, 'utf8').replace(/Distilação/g, 'Destilação').replace(/distilação/g, 'destilação');
  fs.writeFileSync(target, svg);
  await sharp(Buffer.from(svg), {density: 180}).png().toFile(target.replace(/\.svg$/, '.png'));
  process.stdout.write('Diagrama das três arquiteturas atualizado.\n');
})().catch(error => { process.stderr.write(String(error)); process.exit(1); });
