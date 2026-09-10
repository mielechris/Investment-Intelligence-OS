// Fixed, offline build boundary. Called only inside a fresh disposable copy.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { relative, resolve } from 'node:path';
import { writeFileSync } from 'node:fs';

const require = createRequire(resolve('package.json'));
const { build } = await import(pathToFileURL(require.resolve('vite')));
const modules = new Set();
let configuration;
await build({
  configLoader: 'runner',
  mode: 'production',
  logLevel: 'error',
  build: { write: true, emptyOutDir: true, sourcemap: false },
  plugins: [{
    name: 'iios-build-provenance-observer',
    configResolved(config) {
      configuration = { target: config.build.target, minify: config.build.minify,
        cssMinify: config.build.cssMinify, base: config.base, mode: config.mode,
        sourcemap: config.build.sourcemap };
    },
    generateBundle(_options, bundle) {
      for (const entry of Object.values(bundle)) if (entry.type === 'chunk') {
        for (const id of Object.keys(entry.modules)) {
          if (id.startsWith('\0')) modules.add('virtual:' + id.slice(1));
          else {
            const name = relative(process.cwd(), id);
            if (name.startsWith('..') || name.startsWith('/')) throw Error('MODULE_OUTSIDE_BUILD_ROOT');
            modules.add(name);
          }
        }
      }
    },
  }],
});
writeFileSync('build-observation.json', JSON.stringify({ configuration, modules: [...modules].sort() }) + '\n', { flag: 'wx', mode: 0o600 });
