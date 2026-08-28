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
    files: ['src/LivingFactoryExperience.tsx', 'src/InteractiveCaseTheater.tsx'],
    rules: {
      // These read-only browser components deliberately clear stale detail
      // state when the selected persisted case changes. Keep the exception
      // local rather than weakening repo-wide hook linting.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
])