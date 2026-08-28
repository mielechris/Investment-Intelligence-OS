import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    files: ['src/LivingFactoryExperience.tsx'],
    rules: {
      // 9L deliberately clears stale case-detail state synchronously when the
      // selected persisted case changes. Keep the exception local to this
      // read-only experience component rather than weakening repo-wide lint.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
])
