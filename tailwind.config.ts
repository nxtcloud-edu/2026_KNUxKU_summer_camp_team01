import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}', './messages/**/*.json'],
  theme: { extend: {} },
  plugins: [],
};

export default config;
