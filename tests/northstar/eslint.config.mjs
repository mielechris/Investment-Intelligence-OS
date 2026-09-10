import js from '../../FRONT END/node_modules/@eslint/js/src/index.js';
import globals from '../../FRONT END/node_modules/globals/index.js';
export default [{ ignores: ['node_modules/**', '.build/**', 'artifacts/**', 'snapshots/**'] },
  { files: ['*.mjs'], ...js.configs.recommended, languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: { ...globals.node, ...globals.browser } } }];
