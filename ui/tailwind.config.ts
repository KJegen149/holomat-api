import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        j: {
          bg:     'rgb(5 5 8 / <alpha-value>)',
          surf:   'rgb(10 13 18 / <alpha-value>)',
          border: 'rgb(14 42 53 / <alpha-value>)',
          cyan:   'rgb(0 200 232 / <alpha-value>)',
          cdim:   'rgb(0 104 120 / <alpha-value>)',
          text:   'rgb(200 240 248 / <alpha-value>)',
          muted:  'rgb(58 122 138 / <alpha-value>)',
          green:  'rgb(0 255 136 / <alpha-value>)',
          amber:  'rgb(232 160 32 / <alpha-value>)',
          red:    'rgb(232 48 64 / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Rajdhani', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'spin-slow':    'spin 20s linear infinite',
        'spin-rslw':    'spin 14s linear infinite reverse',
        'spin-med':     'spin 8s linear infinite',
        'spin-rmed':    'spin 4s linear infinite reverse',
        'radar-sweep':  'spin 4s linear infinite',
        'pulse-green':  'pulse-green 2s ease-in-out infinite',
        'cur-blink':    'cur-blink 1s step-end infinite',
        'tick-blink':   'tick-blink 4s ease-in-out infinite',
      },
      keyframes: {
        'pulse-green': {
          '0%, 100%': { opacity: '1' },
          '50%':       { opacity: '0.4' },
        },
        'cur-blink': {
          '0%, 100%': { opacity: '1' },
          '50%':       { opacity: '0' },
        },
        'tick-blink': {
          '0%, 45%, 100%': { opacity: '0' },
          '50%, 55%':      { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
